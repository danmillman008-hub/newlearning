// Builds a single self-contained HTML file that runs Code Atlas's real renderer
// against a headless analysis snapshot.
//
//   node tools/export-html.mjs <snapshot.json> <out.html>
//
// The desktop app ships the renderer as a bundle loaded by Electron with a
// `window.atlas` preload bridge. Here the same bundle + CSS are inlined, the one
// Worker URL is remapped to a Blob, and `window.atlas` is a plain JS object that
// answers from the embedded snapshot instead of IPC. No Electron, no server, no
// network: one file you can open from disk.
import { readFileSync, writeFileSync, readdirSync, mkdirSync } from 'node:fs'
import { join, dirname, resolve } from 'node:path'

const [, , snapArg, outArg] = process.argv
if (!snapArg || !outArg) {
  console.error('usage: export-html.mjs <snapshot.json> <out.html>')
  process.exit(2)
}

const ROOT = resolve(import.meta.dirname, '..')
const ASSETS = join(ROOT, 'out/renderer/assets')
const asset = (re) => {
  const hit = readdirSync(ASSETS).find((f) => re.test(f))
  if (!hit) throw new Error(`missing build asset ${re} — run: npx electron-vite build`)
  return join(ASSETS, hit)
}

const data = JSON.parse(readFileSync(snapArg, 'utf8'))
const rendererJs = readFileSync(asset(/^index-.*\.js$/), 'utf8')
const rendererCss = readFileSync(asset(/^index-.*\.css$/), 'utf8')
const workerJs = readFileSync(asset(/^force-worker-.*\.js$/), 'utf8')

// --- 1. renderer bundle: one Worker reference to remap ---
const workerRef = /new URL\("(force-worker-[^"]+\.js)",\s*import\.meta\.url\)\.href/
if (!workerRef.test(rendererJs)) throw new Error('force-worker reference not found in renderer bundle')
let patched = rendererJs.replace(
  workerRef,
  'window.__atlasWorkerUrl'
)
// the bundle is a module (so import.meta is legal) but has no base URL worth
// resolving chunks against; the only other reader is __vitePreload's error path
patched = patched.replace(/import\.meta\.url/g, '""')
if (patched.includes('import.meta')) throw new Error('unexpected leftover import.meta in renderer bundle')

// --- 2. embedded payload: the snapshot plus the lazily-fetched symbol graphs ---
const payload = {
  meta: data.meta,
  snapshot: data.snapshot,
  extractions: data.extractions ?? {},
  importNeighbors: data.importNeighbors ?? {},
  sources: data.sources ?? {},
  moduleGraphs: data.moduleGraphs ?? {}
}
const json = JSON.stringify(payload)
// JSON inside a <script> must not be able to close the tag
const safeJson = json.replace(/</g, '\\u003c').replace(/\u2028/g, '\\u2028').replace(/\u2029/g, '\\u2029')

const html = `<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Code Atlas · ${escapeHtml(data.meta?.repoName ?? 'repository')}</title>
    <style>${rendererCss}</style>
    <style>
      /* web-export chrome: the app fills the viewport, plus a small provenance card */
      html, body, #root { height: 100%; margin: 0; background: #0a0e17; }
      #atlas-origin {
        position: fixed; right: 12px; bottom: 10px; z-index: 60;
        font: 11px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace;
        color: #7d8ea8; text-align: right; pointer-events: none;
        text-shadow: 0 1px 4px #000;
      }
      #atlas-origin b { color: #c9d6e8; font-weight: 600; }
      #atlas-origin .warn { color: #d9a05b; }
    </style>
  </head>
  <body>
    <div id="root"></div>
    <div id="atlas-origin">
      <b>${escapeHtml(data.meta?.repoName ?? '')}</b> · analyzed ${escapeHtml(shortDate(data.meta?.generatedAt))} by Code Atlas (headless)
      <br /><span class="warn">static export</span> · editing, AI chat &amp; coverage need the desktop app
    </div>
    <script id="atlas-data" type="application/json">${safeJson}</script>
    <script>
      (function () {
        var RAW = document.getElementById('atlas-data').textContent;
        var DATA = JSON.parse(RAW);
        // free the raw string early — the parsed copy is what the app holds
        document.getElementById('atlas-data').textContent = '';

        // ---- snapshot: rebuild the typed arrays the IPC boundary uses ----
        var snap = DATA.snapshot;
        snap.importEdges = Uint32Array.from(snap.importEdges);

        // ---- force layout worker: same chunk the desktop build loads ----
        var WORKER_SRC = __WORKER_SRC__;
        window.__atlasWorkerUrl = URL.createObjectURL(
          new Blob([WORKER_SRC], { type: 'text/javascript' })
        );

        var listeners = {
          progress: [], snapshot: [], gl: [], llmChunk: [], llmDone: [], llmError: [],
          llmToolCall: [], llmToolDone: [], llmRetry: [], summaries: []
        };
        function on(name) {
          return function (cb) {
            listeners[name].push(cb);
            // the desktop app pushes the snapshot after analysis finishes; here
            // the analysis is already done, so hand it over on subscription
            if (name === 'snapshot') {
              setTimeout(function () {
                try { cb(snap); } catch (e) { console.error('[atlas] snapshot sink', e); }
              }, 0);
            }
            return function () {
              var i = listeners[name].indexOf(cb);
              if (i >= 0) listeners[name].splice(i, 1);
            };
          };
        }
        function emit(name, arg) {
          listeners[name].slice().forEach(function (cb) {
            try { cb(arg); } catch (e) { console.error('[atlas] listener', name, e); }
          });
        }

        // ---- offline symbol graph ----
        // faithful port of src/main/analyzer/symbol-graph.ts: containment by
        // smallest enclosing range, call edges by name (same file first, then
        // resolved import neighbours)
        function moduleGraph(fileIds) {
          var symbols = [], edges = [];
          var moduleSymbol = {}, defsByFile = {}, included = {};
          fileIds.forEach(function (f) { included[f] = true; });

          fileIds.forEach(function (fileId) {
            var ex = DATA.extractions[fileId];
            var modIdx = symbols.length;
            moduleSymbol[fileId] = modIdx;
            symbols.push({ name: snap.files[fileId].name, kind: 'module', file: fileId, range: [0, 0], parent: -1 });
            if (!ex) return;
            var ordered = (ex.defs || [])
              .map(function (d) { return { def: d, span: d.endLine - d.startLine }; })
              .sort(function (a, b) { return a.span - b.span; })
              .slice(0, 300);
            var local = [];
            ordered.forEach(function (o) {
              var idx = symbols.length;
              symbols.push({
                name: o.def.name, kind: o.def.kind, file: fileId,
                range: [o.def.startLine, o.def.endLine], parent: modIdx
              });
              local.push({ idx: idx, def: o.def });
            });
            defsByFile[fileId] = local;
            local.forEach(function (a) {
              var best = null;
              local.forEach(function (b) {
                if (a === b) return;
                if (b.def.startLine <= a.def.startLine && b.def.endLine >= a.def.endLine &&
                    (b.def.endLine - b.def.startLine > a.def.endLine - a.def.startLine ||
                     (b.def.endLine - b.def.startLine === a.def.endLine - a.def.startLine && b.idx < a.idx))) {
                  if (!best || b.def.endLine - b.def.startLine < best.def.endLine - best.def.startLine) best = b;
                }
              });
              if (best) symbols[a.idx].parent = best.idx;
              edges.push({ src: symbols[a.idx].parent, dst: a.idx, kind: 'contains' });
            });
          });

          var byName = {};
          Object.keys(defsByFile).forEach(function (fileId) {
            var m = {};
            defsByFile[fileId].forEach(function (e) {
              (m[e.def.name] = m[e.def.name] || []).push(e.idx);
            });
            byName[fileId] = m;
          });

          var seen = {};
          function addCall(src, dst) {
            if (src === dst) return;
            var key = src * 1e6 + dst;
            if (seen[key]) return;
            seen[key] = 1;
            edges.push({ src: src, dst: dst, kind: 'call' });
          }

          fileIds.forEach(function (fileId) {
            var ex = DATA.extractions[fileId];
            if (!ex) return;
            var local = defsByFile[fileId] || [];
            function containerOf(line) {
              var best = moduleSymbol[fileId], bestSpan = Infinity;
              local.forEach(function (e) {
                if (e.def.startLine <= line && e.def.endLine >= line) {
                  var span = e.def.endLine - e.def.startLine;
                  if (span < bestSpan) { bestSpan = span; best = e.idx; }
                }
              });
              return best;
            }
            var neighborFiles = (DATA.importNeighbors[fileId] || []).filter(function (f) { return included[f]; });
            (ex.refs || []).forEach(function (ref) {
              var src = containerOf(ref.line);
              var same = byName[fileId] && byName[fileId][ref.name];
              if (same && same.length) { addCall(src, same[0]); return; }
              for (var i = 0; i < neighborFiles.length; i++) {
                var hit = byName[neighborFiles[i]] && byName[neighborFiles[i]][ref.name];
                if (hit && hit.length) { addCall(src, hit[0]); break; }
              }
            });
          });
          return { symbols: symbols, edges: edges };
        }

        var settings = {
          recentRepos: [snap.rootPath],
          maxFiles: DATA.meta && DATA.meta.maxFiles,
          maxCommits: DATA.meta && DATA.meta.maxCommits,
          bookmarks: {}
        };

        window.atlas = {
          // ---- analysis: already done, replay it ----
          analyze: function () {
            emit('progress', { phase: 'done', done: snap.files.length, total: snap.files.length });
            emit('snapshot', snap);
            return Promise.resolve();
          },
          cancelAnalysis: function () { return Promise.resolve(); },
          openFolderDialog: function () {
            return Promise.resolve(null).then(function () {
              window.alert('This is a static Code Atlas export of one repository — analysis of other folders needs the desktop app.');
              return null;
            });
          },
          // ---- source access (read-only) ----
          readFile: function (fileId) {
            var src = DATA.sources[fileId];
            return Promise.resolve(typeof src === 'string' ? src : null);
          },
          writeFile: function () {
            return Promise.resolve({ ok: false, error: 'Read-only export: run the desktop app to edit files.' });
          },
          getModuleGraph: function (fileIds) {
            return Promise.resolve(moduleGraph(fileIds));
          },
          // ---- AI + coverage: not available offline ----
          llmProbe: function () {
            return Promise.resolve({ ok: false, tried: [], error: 'AI endpoints are disabled in a static export.' });
          },
          llmChat: function () { return Promise.resolve(''); },
          llmAbort: function () { return Promise.resolve(); },
          llmToolResult: function () { return Promise.resolve(); },
          getSettings: function () { return Promise.resolve(settings); },
          saveSettings: function (patch) {
            Object.assign(settings, patch || {});
            return Promise.resolve(settings);
          },
          loadLcov: function () {
            return Promise.resolve(null).then(function () {
              window.alert('Coverage import needs the desktop app.');
              return null;
            });
          },
          buildSummaries: function () { return Promise.resolve({ error: 'AI summaries are disabled in a static export.' }); },
          cancelSummaries: function () { return Promise.resolve(); },
          getSummaries: function () { return Promise.resolve({}); },
          saveScreenshot: function (dataUrl) {
            // no native dialog offline — hand the PNG to the browser instead
            var a = document.createElement('a');
            a.href = dataUrl;
            a.download = (DATA.meta && DATA.meta.repoName || 'atlas') + '-atlas.png';
            a.click();
            return Promise.resolve(true);
          },
          setGlMode: function () { return Promise.resolve(); },
          onSummariesProgress: on('summaries'),
          onGlInfo: on('gl'),
          onProgress: on('progress'),
          onSnapshot: on('snapshot'),
          onLlmChunk: on('llmChunk'),
          onLlmDone: on('llmDone'),
          onLlmError: on('llmError'),
          onLlmToolCall: on('llmToolCall'),
          onLlmToolDone: on('llmToolDone'),
          onLlmRetry: on('llmRetry')
        };

        // the main process reports which GL backend it picked; offline it is just the browser
        setTimeout(function () { emit('gl', { mode: 'browser', renderer: 'webgl2', software: false }); }, 0);
        window.__atlasSnapshot = snap;
      })();
    </script>
    <script type="module">
${patched}
    </script>
  </body>
</html>
`

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c])
}
function shortDate(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? String(iso) : d.toISOString().slice(0, 16).replace('T', ' ')
}

// worker source goes in as a JS string literal
mkdirSync(dirname(resolve(outArg)), { recursive: true })
writeFileSync(
  resolve(outArg),
  html.replace('__WORKER_SRC__', JSON.stringify(workerJs))
)
console.log(`[export] ${outArg} — ${(Buffer.byteLength(readFileSync(resolve(outArg))) / 1024 / 1024).toFixed(2)} MB`)
