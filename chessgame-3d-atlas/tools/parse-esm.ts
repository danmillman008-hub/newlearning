// ESM twin of src/main/analyzer/parse-worker.ts for plain-Node runs.
//
// parse-worker.ts is written for the Piscina pool (CommonJS worker context); its
// header pulls web-tree-sitter through a `require` interop, which an ESM entry
// point cannot do. Same queries, same capture handling, same skip rules — only
// the module wiring differs. Keep this in sync if the worker's extraction logic
// changes.
import { promises as fs } from 'node:fs'
import { join } from 'node:path'
import { Parser, Language, Query } from 'web-tree-sitter'
import { QUERIES } from '../src/main/analyzer/queries'
import type { ParseResult, RawDef, RawRef } from '../src/main/analyzer/parse-worker'
import type { SymbolKind } from '../src/shared/model'

export interface EmesParseTask {
  absPath: string
  language: string | null
  grammar: string | null
  grammarDir: string
}

const TODO_RE = /\b(TODO|FIXME|HACK|XXX)\b/g

let initialized = false
const languages = new Map<string, Language>()
const queries = new Map<string, Query>()
let parser: Parser | null = null

async function ensureLanguage(grammar: string, grammarDir: string): Promise<Language | null> {
  if (!initialized) {
    await Parser.init({
      locateFile: (name: string) => join(grammarDir, name)
    })
    parser = new Parser()
    initialized = true
  }
  if (languages.has(grammar)) return languages.get(grammar)!
  try {
    const lang = await Language.load(join(grammarDir, `tree-sitter-${grammar}.wasm`))
    languages.set(grammar, lang)
    const src = QUERIES[grammar]
    if (src) queries.set(grammar, new Query(lang, src))
    return lang
  } catch (e) {
    console.warn(`[headless] grammar ${grammar} failed to load:`, (e as Error).message)
    return null
  }
}

function countLoc(source: string): number {
  let loc = 0
  let sawChar = false
  for (let i = 0; i < source.length; i++) {
    const c = source.charCodeAt(i)
    if (c === 10) {
      if (sawChar) loc++
      sawChar = false
    } else if (c !== 32 && c !== 9 && c !== 13) {
      sawChar = true
    }
  }
  if (sawChar) loc++
  return loc
}

const KIND_BY_CAPTURE: Record<string, SymbolKind> = {
  'def.function': 'function',
  'def.class': 'class',
  'def.method': 'method',
  'def.variable': 'variable',
  'def.type': 'type'
}

function cleanImport(text: string): string {
  return text.replace(/^["'<]|["'>]$/g, '').trim()
}

export const GRAMMAR_LOADED = (): string[] => [...queries.keys()]

export default async function parseFile(task: EmesParseTask): Promise<ParseResult> {
  const empty: ParseResult = {
    loc: 0,
    analyzed: false,
    cx: 0,
    todoCount: 0,
    imports: [],
    defs: [],
    refs: []
  }
  let source: string
  try {
    source = await fs.readFile(task.absPath, 'utf8')
  } catch {
    return empty
  }
  const loc = countLoc(source)
  const todoCount = (source.match(TODO_RE) ?? []).length
  const base: ParseResult = { ...empty, loc, todoCount }
  if (!task.grammar) return base
  if (/\.(min|bundle)\./.test(task.absPath) || source.length / Math.max(1, loc) > 250) {
    return base
  }

  const lang = await ensureLanguage(task.grammar, task.grammarDir)
  const query = queries.get(task.grammar)
  if (!lang || !query || !parser) return base

  try {
    parser.setLanguage(lang)
    const tree = parser.parse(source)
    if (!tree) return base
    const imports: string[] = []
    const defs: RawDef[] = []
    const refs: RawRef[] = []
    let cx = 0
    for (const capture of query.captures(tree.rootNode)) {
      const name = capture.name
      const node = capture.node
      if (name === 'cx') {
        cx++
      } else if (name.startsWith('import.')) {
        imports.push(cleanImport(node.text))
      } else if (name.startsWith('def.')) {
        const kind = KIND_BY_CAPTURE[name]
        if (!kind) continue
        const scope = node.parent ?? node
        defs.push({
          name: node.text,
          kind,
          startLine: scope.startPosition.row,
          endLine: scope.endPosition.row
        })
      } else if (name.startsWith('ref.')) {
        refs.push({ name: node.text, line: node.startPosition.row })
      }
    }
    tree.delete()
    return { loc, analyzed: true, cx, todoCount, imports, defs, refs }
  } catch (e) {
    console.warn('[headless] parse failed', task.absPath, (e as Error).message)
    return base
  }
}
