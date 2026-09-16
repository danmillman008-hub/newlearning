# Gramophone M5 — Product Requirements: book quest

## 1. Goal
One command turns chapter knowledge graphs into a finished, playable
adaptive quest, and one binary (`gramophone`) exposes every milestone.
M5 is pure orchestration: it wires the M3 merger, the M2 author, and the
M4 quest loop into a single deterministic pipeline. No new learning
science, no new grading, no new policy.

## 2. Pipeline: chapters -> book -> beats -> quest
`run_book_quest(chapter_paths, outdir, ...)`: (1) load + shape-check each
chapter v1 (object with `items[]`/`surmise[]`); (2) `merge_graphs` with
names (default: file stems) -> `book-graph.json`; (3) `author_beats(book)`
with `llm=None` (deterministic fallback chain, zero tokens) -> validated
-> `beats.json`; (4) response stream from `--responses` or stdin lines
(bare responses, JSON literal or raw string; shared M4 parser); (5)
`adaptive.run_quest(beats, book, responses, ...)` with xAPI store
(`xapi.jsonl`, fresh unless `--resume`) -> `session.json` (+ `--save`
end-state); (6) `M5-REPORT.md` with merge + author + quest sections.
Returns the session dict.

## 3. Unified CLI
`gramophone {m1|m2|m3|m4|quest} ...` routes trailing args to that stage's
`cli.main` (`quest` -> M5 `quest_main`). Unknown subcommand (or none)
prints usage to stderr and exits 2; stage exit codes propagate unchanged
(0 ok, 2 bad input, 1 internal). `gramophone-m5` stays as the direct
quest entry (same flags, no subcommand word).

## 4. Non-goals
No LLM authoring (Mock/Gemini path activates later with zero change —
`author_beats` already takes `llm`); no cross-chapter edge invention
(merge only remaps); no new session semantics (M4 owns them); no changes
to any file under `gramophone_m1/` through `gramophone_m4/`.

## 5. Acceptance
- Golden book (chapter_a + chapter_b): merged counts CHAPTERS=2 ITEMS=5
  EDGES=3; authored beats/checks deterministic; quest completes with the
  golden stream; transcript/order/completion equal hand values.
- `gramophone quest` output == `gramophone-m5` output for same inputs.
- Save/resume mid-quest through the e2e pipeline == whole run.
- Same inputs twice = byte-identical book-graph/beats/session/xapi.
- Full suite (M1+M2+M3+M4+M5) green; M5-REPORT.md written.
