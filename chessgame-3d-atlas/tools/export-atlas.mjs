// One command, repo → standalone HTML atlas.
//
//   node tools/export-atlas.mjs <repoPath> <out.html> [snapshot.json]
//
// 1. tool/.build/headless-analyze.mjs runs the real Code Atlas pipeline
//    (scanner → tree-sitter parse → import resolver → git churn → snapshot)
//    with no Electron and no display server.
// 2. export-html.mjs inlines the production renderer bundle + CSS + force
//    worker and the snapshot into a single file you can open from disk.
import { execFileSync } from 'node:child_process'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'

const [, , repo, out, snapOut] = process.argv
if (!repo || !out) {
  console.error('usage: export-atlas.mjs <repoPath> <out.html> [snapshot.json]')
  process.exit(2)
}

const here = import.meta.dirname
const bundle = join(here, '.build/headless-analyze.mjs')

console.log('[1/3] bundling analyzer …')
execFileSync(process.execPath, [join(here, 'run-headless.mjs')], { stdio: 'inherit' })

const work = mkdtempSync(join(tmpdir(), 'atlas-'))
const snapshotJson = snapOut ? resolve(snapOut) : join(work, 'snapshot.json')

console.log('[2/3] analyzing', resolve(repo))
execFileSync(process.execPath, [bundle, resolve(repo), snapshotJson], { stdio: 'inherit' })

console.log('[3/3] writing', resolve(out))
execFileSync(process.execPath, [join(here, 'export-html.mjs'), snapshotJson, resolve(out)], {
  stdio: 'inherit'
})

if (!snapOut) rmSync(work, { recursive: true, force: true })
