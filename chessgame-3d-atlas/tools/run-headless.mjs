// esbuild wrapper: bundle tools/headless-analyze.ts into one ESM file so the
// analyzer modules resolve their bare imports (web-tree-sitter, ignore, …) from
// node_modules without needing a tsx loader.
import { build } from 'esbuild'
import { mkdirSync } from 'node:fs'

mkdirSync(new URL('./.build/', import.meta.url), { recursive: true })
await build({
  entryPoints: ['tools/headless-analyze.ts'],
  outfile: 'tools/.build/headless-analyze.mjs',
  bundle: true,
  platform: 'node',
  format: 'esm',
  target: 'node20',
  packages: 'external',
  logLevel: 'info'
})
