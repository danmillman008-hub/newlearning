# Gramophone M6 — Product Requirements: full chain

## 1. Goal
One command proves the product: raw chapter files (Markdown or PDF) go
in, a finished adaptive quest comes out. M6 orchestrates M1 (chapter ->
knowledge graph) and M5 (graphs -> quest) with no new learning logic.
It locks the M1->M5 contract with a golden test, so any drift between
the graph producer and the quest consumer breaks the suite, not users.

## 2. Pipeline: chapters -> graphs -> quest
`run_full_chain(chapter_inputs, outdir, ...)`: (1) validate inputs
(non-empty list; every file exists; names default to stems, len match);
(2) per chapter `break_file(input, outdir/m1_<name>, max_items,
token_budget)` with a fresh `default_llm()` Mock cassette per chapter
(the CLI-canonical M1 run; a missing cassette raises ValueError loudly
instead of silently degrading to the no-cassette fallback graph); the
`m1_*` dirs are kept as provenance artifacts; (3)
`run_book_quest(v1_paths, outdir, ...)` with the caller's quest options;
(4) return `{"m1": [counts...], "session": session}`. Response sourcing,
resume, determinism, and exits follow M5; M1 counts lines are reused
verbatim for stdout.

## 3. CLI
`gramophone-m6 CHAPTER [CHAPTER...] --out OUTDIR` with M5's quest flags
plus `--max-items` / `--token-budget`. Prints each chapter's M1 stdout
line, then the BOOK and SESSION lines. Exits 0/2/1. Standalone script:
the unified `gramophone` dispatcher stays frozen (M5 file) until a
dedicated M5 patch release adds the `m6` route.

## 4. Non-goals
No new stages (no LLM authoring, no HTML reports); no changes under
`gramophone_m1/` through `gramophone_m5/`; no invented determinism
(inherited wall clocks compared modulo timestamps, M1 precedent).

## 5. Acceptance
- Golden: `fixtures/sample_chapter.md` -> M1 ITEMS=22 -> authored beats
  -> quest completes on the golden stream; transcript/order/completion
  equal hand values.
- Save/resume through the full chain == whole run.
- Same inputs twice = identical outputs modulo wall clocks.
- Full suite (M1–M6) green; M6-REPORT.md written.
