# Gramophone M5 — System Architecture: book quest

## 1. Module layout
- `gramophone_m5/bookquest.py`: `run_book_quest(chapter_paths, outdir,
  responses_path=None, response_lines=None, names=None, save=None,
  resume=None, actor="learner", max_retries=1, max_steps=1000)` — the
  4-stage orchestration (load+merge -> author -> quest -> write). All
  inputs validated before anything is written; returns the session dict.
- `gramophone_m5/cli.py`: `quest_main(argv)` (direct quest entry) and
  `main(argv)` (unified `gramophone` dispatcher). Both return int exit
  codes (0 ok, 2 bad input, 1 internal).

## 2. File structure
```
gramophone_m5/__init__.py        # __version__ = "0.5.0"
gramophone_m5/bookquest.py
gramophone_m5/cli.py
fixtures/m5_responses.txt        # golden stream for the authored beats
tests/test_bookquest.py
pyproject.toml                   # 0.5.0; + gramophone, gramophone-m5
docs/M5_PRD.md, docs/M5_ARCHITECTURE.md (this file)
M5-REPORT.md                     # generated
```
Golden book = existing `fixtures/chapter_a.json` + `fixtures/chapter_b.json`
(merged CHAPTERS=2 ITEMS=5 EDGES=3). No new chapter fixtures.

## 3. Reuse imports (exact; nothing else from M1–M4)
```python
from gramophone_m3.merge import merge_graphs
from gramophone_m3.live import load_state, save_state
from gramophone_m2.author import author_beats          # llm=None: deterministic
from gramophone_m2.story_model import validate, save_beats
from gramophone_m2.xapi import XAPIStore
from gramophone_m4.adaptive import run_quest
from gramophone_m4.pipeline import parse_response_line
from gramophone_m1.cli import main as _m1 ... (unified dispatcher only,
  same for m2/m3/m4: `from gramophone_mN.cli import main as _mN`)
```
Forbidden: any write under `gramophone_m1/`–`gramophone_m4/`; any local
grading/BKT/DSR/policy/state/xAPI logic; inventing cross-chapter edges.

## 4. I/O schemas
- `book-graph.json`: `merge_graphs` output verbatim (indent=1, sort_keys).
- `beats.json`: `author_beats(book)` output via `save_beats`.
- `session.json`: `run_quest` session verbatim (indent=1, sort_keys).
- `xapi.jsonl`: fresh unless `resume` (then append).
- `M5-REPORT.md`: `# Gramophone M5 — Run Report` + `## Merge` line
  (`CHAPTERS=.. ITEMS=.. EDGES=.. STATES=..`), `## Author` line
  (`BEATS=.. CHECKS=.. CLUSTERS=.. VIA_FALLBACK=.. TOKENS=0`), `## Quest`
  line (M4 shape + `COMPLETION=.. PICKS=..`).

## 5. CLI spec
`gramophone-m5 CHAPTER [CHAPTER...] --out OUTDIR [--responses FILE]`
(`--responses` XOR stdin lines) `[--names N ...]` (len must match
chapters; default: file stems) `[--save/--resume/--actor]`
`[--max-retries 1] [--max-steps 1000]`.
stdout: `BOOK CHAPTERS=.. ITEMS=.. EDGES=.. BEATS=.. CHECKS=..` then the
M4-style `SESSION ... COMPLETION=..` line.
`gramophone {m1|m2|m3|m4|quest} ARGS...`: route trailing args to that
stage's `cli.main` (`quest` -> `quest_main`); return its code unchanged.
No/unknown subcommand: usage to stderr, exit 2.

## 6. Orchestration algorithm
1. Validate everything first (ValueError, no writes): >=1 chapter; every
   path exists; every file parses as a JSON object with `items[]` +
   `surmise[]`; names (given: len match, else stems; merge raises on
   dup/empty); exactly one of responses_path/response_lines (missing
   responses file -> ValueError); resume loads via `load_state`
   (re-attach `quest_transcript`/`quest_picks` from the raw JSON, as M4).
2. `book = merge_graphs(v1s, names)`; makedirs; write `book-graph.json`.
3. `beats, info = author_beats(book)`; `validate(beats)` non-empty ->
   RuntimeError (internal: the author broke its contract); save beats.
4. Parse lines (skip blanks) -> `run_quest(beats, book, responses, actor,
   max_retries, max_steps, restore, XAPIStore(...))`; write session;
   save state; append-or-create report. Determinism: fixed stage order,
   sorted JSON, logical-step telemetry, `llm=None` (zero tokens).

## 7. Test plan (tests/test_bookquest.py)
E2E golden on chapter_a+b (book counts + authored BEATS/CHECKS + quest
completion/transcript == hand values); unified dispatch (quest via
`gramophone` == via m5 byte-for-byte; `m1 --help` exits 0; unknown
subcommand exits 2); save/resume e2e == whole; determinism (two runs,
all four outputs byte-identical); bad inputs (zero chapters, dup names,
chapter-not-JSON, chapter-bad-shape, responses+lines, missing files ->
ValueError/exit 2); no-network (socket blocked). M1–M4 suites stay green.
