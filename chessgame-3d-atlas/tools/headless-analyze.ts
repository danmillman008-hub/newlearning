// Headless runner for the Code Atlas analysis pipeline.
//
// The desktop app drives analyze() from the Electron main process (Piscina
// worker pool + app.getPath for the grammar dir). This entry point runs the
// *same* pipeline modules — scanner, parse-worker, import-resolver, git churn,
// symbol-graph — directly inside plain Node, so a repository can be analyzed on
// a machine with no display server and no Electron binary, and the resulting
// RepoSnapshot (+ the symbol extractions the molecule view needs) can be
// serialized to JSON for the web export.
//
//   node tools/.build/headless-analyze.mjs <repoPath> <outFile>
//
// Emits one JSON document: { meta, snapshot, extractions, importNeighbors, sources }
import { promises as fs, existsSync } from 'node:fs'
import { join, resolve, basename } from 'node:path'
import os from 'node:os'
import { scan, MAX_PARSE_BYTES } from '../src/main/analyzer/scanner'
import parseFile, { GRAMMAR_LOADED } from './parse-esm'
import type { ParseResult } from '../src/main/analyzer/parse-worker'
import { ImportResolver } from '../src/main/analyzer/import-resolver'
import { readGitHistory } from '../src/main/git/churn'
import { buildModuleGraph } from '../src/main/analyzer/symbol-graph'
import type { FileExtraction } from '../src/main/analyzer/symbol-graph'
import { grammarFor, languageForPath } from '../src/shared/languages'
import type { DirNode, FileId, FileNode, RepoSnapshot } from '../src/shared/model'

/**
 * code-atlas ships its grammars in resources/grammars (copied there by the
 * `grammars` npm script). Mirrors analyzer.ts: env override, then next-to-source,
 * then relative to the working directory.
 */
export function grammarDir(): string {
  if (process.env.ATLAS_GRAMMARS) return resolve(process.env.ATLAS_GRAMMARS)
  const candidates = [
    resolve(import.meta.dirname ?? process.cwd(), '..', '..', '..', 'resources', 'grammars'),
    resolve(process.cwd(), 'resources', 'grammars')
  ]
  for (const c of candidates) {
    if (existsSync(c)) return c
  }
  return candidates[1]
}

export interface HeadlessResult {
  meta: {
    repoName: string
    rootPath: string
    generatedAt: string
    analyzer: string
    host: { platform: string; arch: string; cpus: number; node: string }
    commits: number
    grammarDir: string
  }
  snapshot: RepoSnapshot & { importEdges: Uint32Array }
  extractions: Map<FileId, FileExtraction>
  importNeighbors: Map<FileId, Set<FileId>>
  /** edges from wildcard imports: in the graph, not in the call-matching neighbourhood */
  weakEdges: [FileId, FileId][]
  sources: Map<FileId, string>
}

export async function analyzeHeadless(
  rootPath: string,
  opts: { maxFiles?: number; maxCommits?: number; concurrency?: number; keepSources?: boolean } = {},
  onProgress?: (phase: string, done: number, total: number, current?: string) => void
): Promise<HeadlessResult> {
  const maxFiles = opts.maxFiles ?? 30000
  const maxCommits = opts.maxCommits ?? 5000
  const gDir = grammarDir()

  // ---- scan (git ls-files preferred, filtered walk otherwise) ----
  onProgress?.('scan', 0, 0)
  const scanned = await scan(rootPath, maxFiles)

  // ---- dir tree + file nodes (identical construction to analyzer.ts) ----
  const dirs: DirNode[] = [{ path: '', name: '/', parent: -1, children: [], fileIds: [] }]
  const dirIdByPath = new Map<string, number>([['', 0]])
  const ensureDir = (path: string): number => {
    const known = dirIdByPath.get(path)
    if (known !== undefined) return known
    const slash = path.lastIndexOf('/')
    const parentPath = slash < 0 ? '' : path.slice(0, slash)
    const parent = ensureDir(parentPath)
    const id = dirs.length
    dirs.push({
      path,
      name: slash < 0 ? path : path.slice(slash + 1),
      parent,
      children: [],
      fileIds: []
    })
    dirs[parent].children.push(id)
    dirIdByPath.set(path, id)
    return id
  }

  const files: FileNode[] = []
  const byPath = new Map<string, FileId>()
  const filesInDir = new Map<string, FileId[]>()
  for (const sf of scanned.files) {
    const slash = sf.relPath.lastIndexOf('/')
    const dirPath = slash < 0 ? '' : sf.relPath.slice(0, slash)
    const dirId = ensureDir(dirPath)
    const id = files.length
    files.push({
      path: sf.relPath,
      name: slash < 0 ? sf.relPath : sf.relPath.slice(slash + 1),
      dir: dirId,
      language: languageForPath(sf.relPath),
      loc: 0,
      sizeBytes: sf.sizeBytes,
      complexity: 0,
      todoCount: 0,
      churn: { commits: 0, lastTouched: 0, authors: 0, heat: 0, topAuthor: '', topShare: 0 },
      analyzed: false,
      symbolCount: 0
    })
    dirs[dirId].fileIds.push(id)
    byPath.set(sf.relPath, id)
    const arr = filesInDir.get(dirPath) ?? []
    arr.push(id)
    filesInDir.set(dirPath, arr)
  }
  onProgress?.('scan', files.length, files.length)

  // ---- parse (in-process instead of the Piscina pool) ----
  const extractions = new Map<FileId, FileExtraction>()
  const sources = new Map<FileId, string>()
  const rawImports: string[][] = new Array(files.length)
  const concurrency = opts.concurrency ?? Math.max(4, Math.min(16, os.cpus().length))
  let parsed = 0
  let cursor = 0
  const worker = async (): Promise<void> => {
    while (cursor < files.length) {
      const id = cursor++
      const file = files[id]
      const abs = join(rootPath, file.path)
      const tooBig = file.sizeBytes > MAX_PARSE_BYTES
      const task = {
        absPath: abs,
        language: file.language,
        grammar: tooBig ? null : grammarFor(file.language),
        grammarDir: gDir
      }
      const result: ParseResult = await parseFile(task)
      file.loc = result.loc
      file.analyzed = result.analyzed
      file.complexity = result.cx
      file.todoCount = result.todoCount
      file.symbolCount = result.defs.length
      rawImports[id] = result.imports
      if (result.analyzed) extractions.set(id, { defs: result.defs, refs: result.refs })
      if (opts.keepSources !== false && result.loc > 0) {
        try {
          const text = await fs.readFile(abs, 'utf8')
          // same 512 KB cap the desktop readFile IPC handler applies
          sources.set(id, text.length > 512 * 1024 ? text.slice(0, 512 * 1024) + '\n… (truncated)' : text)
        } catch {
          /* unreadable → editor shows "no file" */
        }
      }
      parsed++
      onProgress?.('parse', parsed, files.length, file.path)
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, files.length) }, worker))

  // ---- import resolution ----
  onProgress?.('link', 0, files.length)
  const resolver = new ImportResolver({
    byPath,
    filesInDir,
    filePaths: files.map((f) => f.path)
  })
  const importNeighbors = new Map<FileId, Set<FileId>>()
  // wildcard imports (`import pkg.*`) still create graph edges but are left out
  // of importNeighbors, which the molecule call-matching walks by file name —
  // a package-wide match would attribute calls to a sibling of the real target
  const weakEdges: [FileId, FileId][] = []
  const edgeSet = new Set<number>()
  const edgePairs: number[] = []
  for (let id = 0; id < files.length; id++) {
    const specs = rawImports[id]
    const lang = files[id].language
    if (!specs?.length || !lang) continue
    for (const spec of specs) {
      const targets = resolver.resolve(files[id].path, lang, spec)
      const weak = resolver.weak
      for (const target of targets) {
        if (target === id) continue
        const key = id * 1_000_000 + target
        if (edgeSet.has(key)) continue
        edgeSet.add(key)
        edgePairs.push(id, target)
        if (weak) {
          weakEdges.push([id, target])
          continue
        }
        let n = importNeighbors.get(id)
        if (!n) importNeighbors.set(id, (n = new Set()))
        n.add(target)
      }
    }
  }
  onProgress?.('link', files.length, files.length)

  // ---- git history (churn heat + time-scrub timeline) ----
  let timeline: RepoSnapshot['timeline'] = { commits: [], events: [] }
  if (scanned.usedGit) {
    try {
      onProgress?.('git', 0, maxCommits)
      const history = await readGitHistory(rootPath, byPath, maxCommits, (n) =>
        onProgress?.('git', n, maxCommits)
      )
      timeline = history.timeline
      for (const [fileId, info] of history.churn) files[fileId].churn = info
    } catch (e) {
      console.warn('[headless] git history failed:', e)
    }
  }

  // ---- snapshot ----
  const languages: Record<string, number> = {}
  let totalLoc = 0
  for (const f of files) {
    totalLoc += f.loc
    const key = f.language ?? 'other'
    languages[key] = (languages[key] ?? 0) + 1
  }
  const snapshot: RepoSnapshot = {
    rootPath,
    dirs,
    files,
    importEdges: Uint32Array.from(edgePairs),
    timeline,
    stats: { totalLoc, totalFiles: files.length, languages, skipped: scanned.skipped }
  }
  onProgress?.('done', files.length, files.length)

  return {
    meta: {
      repoName: basename(rootPath.replace(/\/+$/, '')),
      rootPath,
      generatedAt: new Date().toISOString(),
      analyzer: 'code-atlas headless pipeline (scanner → tree-sitter parse → import resolver → git history)',
      host: { platform: process.platform, arch: process.arch, cpus: os.cpus().length, node: process.version },
      commits: timeline.commits.length,
      grammarDir: gDir
    },
    snapshot,
    extractions,
    importNeighbors,
    weakEdges,
    sources
  }
}

/** JSON form of the result — typed arrays and Maps become plain arrays/objects */
export function serialize(result: HeadlessResult): Record<string, unknown> {
  const { snapshot } = result
  return {
    meta: result.meta,
    snapshot: {
      rootPath: snapshot.rootPath,
      dirs: snapshot.dirs,
      files: snapshot.files,
      importEdges: Array.from(snapshot.importEdges),
      timeline: snapshot.timeline,
      stats: snapshot.stats
    },
    extractions: Object.fromEntries(result.extractions),
    importNeighbors: Object.fromEntries(
      [...result.importNeighbors].map(([k, v]) => [k, [...v]])
    ),
    weakEdges: result.weakEdges,
    sources: Object.fromEntries(result.sources)
  }
}

/** sanity helper used by the exporter: build the molecule graph for one file */
export function moduleGraphFor(result: HeadlessResult, fileId: FileId): unknown {
  const names = result.snapshot.files.map((f) => f.name)
  return buildModuleGraph([fileId], names, result.extractions, result.importNeighbors)
}

// ---- CLI ----
const isMain = process.argv[1] && resolve(process.argv[1]) === resolve(import.meta.filename ?? '')
if (isMain) {
  const [repo, outFile] = process.argv.slice(2)
  if (!repo) {
    console.error('usage: headless-analyze.mjs <repoPath> [outFile.json]')
    process.exit(2)
  }
  const t0 = Date.now()
  let lastPhase = ''
  analyzeHeadless(resolve(repo), {}, (phase, done, total, current) => {
    if (phase !== lastPhase) {
      console.log(`[headless] ${phase}: ${done}/${total} ${current ?? ''}`)
      lastPhase = phase
    }
  })
    .then(async (result) => {
      const json = JSON.stringify(serialize(result))
      if (outFile) {
        await fs.mkdir(resolve(outFile, '..'), { recursive: true })
        await fs.writeFile(outFile, json)
        console.log(`[headless] wrote ${outFile} (${(json.length / 1024).toFixed(1)} KB)`)
      } else {
        process.stdout.write(json)
      }
      const s = result.snapshot
      console.log(
        `[headless] ${s.stats.totalFiles} files · ${s.stats.totalLoc} loc · ` +
          `${s.importEdges.length / 2} import edges · ${s.timeline.commits.length} commits · ` +
          `${result.extractions.size} parsed · ${((Date.now() - t0) / 1000).toFixed(1)}s`
      )
      console.log('[headless] languages:', JSON.stringify(s.stats.languages))
      console.log('[headless] grammars loaded:', GRAMMAR_LOADED().join(', '))
    })
    .catch((e) => {
      console.error('[headless] failed:', e)
      process.exit(1)
    })
}
