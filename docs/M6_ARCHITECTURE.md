# Gramophone M6 — System Architecture: full chain

## 1. Module layout
- `gramophone_m6/fullchain.py`: `run_full_chain(chapter_inputs, outdir,
  responses_path=None, response_lines=None, names=None, save=None,
  resume=None, actor="learner", max_retries=1, max_steps=1000,
  max_items=300, token_budget=None)` — stage 1 (M1 per chapter) + stage 2
  (M5 over the v1s). Returns `{"m1": [counts...], "session": session}`.
- `gramophone_m6/cli.py`: `main(argv)` — the `gramophone-m6` entry;
  returns int exit codes (0 ok, 2 bad input, 1 internal).

## 2. File structure
```
gramophone_m6/__init__.py        # __version__ = "0.6.0"
gramophone_m6/fullchain.py
gramophone_m6/cli.py
fixtures/m6_responses.txt        # golden stream for the sample-chapter beats
tests/test_fullchain.py
pyproject.toml                   # 0.6.0; + gramophone-m6 script
docs/M6_PRD.md, docs/M6_ARCHITECTURE.md (this file)
M6-REPORT.md                     # generated
```
Golden input = existing `fixtures/sample_chapter.md` (M1 ITEMS=22).

## 3. Reuse imports (exact; nothing else from M1–M5)
```python
from gramophone_m1.pipeline import break_file, default_llm
from gramophone_m5.bookquest import run_book_quest
```
Forbidden: any write under `gramophone_m1/`–`gramophone_m5/` (incl. the
frozen unified dispatcher); any local break/merge/author/quest logic.

## 4. I/O schemas
- `outdir/m1_<name>/knowledge-graph.json` (+ v0.1 + M1-REPORT.md): M1
  outputs verbatim, kept as provenance.
- `outdir/book-graph.json`, `beats.json`, `session.json`, `xapi.jsonl`:
  M5 outputs verbatim.
- `outdir/M5-REPORT.md`: left in place (detailed M5 stage report).
- `M6-REPORT.md`: M6's own file — `# Gramophone M6 — Run Report` header
  + `## Chapters` (one reused M1 stdout line per chapter) + `## Quest`
  (M5-shaped quest summary line built from the returned session).
  Resume runs append fresh Chapters + Quest sections.

## 5. CLI spec
`gramophone-m6 CHAPTER [CHAPTER...] --out OUTDIR [--responses FILE]`
(`--responses` XOR stdin lines) `[--names N ...]` (default: file stems)
`[--max-items 300] [--token-budget N] [--save/--resume/--actor]`
`[--max-retries 1] [--max-steps 1000]`.
stdout: one M1 line per chapter, then `BOOK ...` + `SESSION ...` lines
(same shapes as M5). Exits 0/2/1.

## 6. Orchestration algorithm
1. Validate first (ValueError, no writes): inputs is a non-empty
   list/tuple; every input exists; names (given: list, len match — else
   stems); max_items/token_budget sanity is M1's (propagates);
   responses presence is M5's (propagates). Resume state loads in M5.
2. Stage 1: fail fast with ValueError if `default_llm()` is None
   (missing cassette must be loud, never a silent fallback graph);
   for each (input, name): `break_file(input, outdir/m1_<name>,
   max_items, token_budget, llm=default_llm())` (fresh cassette per
   chapter, matching standalone CLI counts); collect `v1_path` +
   counts + stdout lines. Caveat: M1-internal failures may leave
   earlier `m1_*` dirs behind (intermediates, documented).
3. Stage 2: `run_book_quest(v1_paths, outdir, responses_path,
   response_lines, names, save, resume, actor, max_retries, max_steps)`.
4. Report: write/append M6's own `M6-REPORT.md` (header on create,
   then `## Chapters` with the reused M1 stdout lines, then `## Quest`
   with the M5-shaped summary from the returned session). M5's
   `M5-REPORT.md` is left untouched beside it.
   Determinism: fixed stage order; outputs identical modulo the
   inherited M1/M3 wall clocks.

## 7. Test plan (tests/test_fullchain.py)
Full golden on sample_chapter.md (M1 ITEMS=22 EDGES=17 + BOOK counts +
quest completion/transcript == hand values); CLI golden (M1 + BOOK +
SESSION lines) + exits; save/resume full-chain == whole (session +
xapi bytes); determinism (two runs: parsed outputs equal modulo
`*_at`/`generated_at` wall clocks); bad inputs (zero inputs, missing
file, names mismatch, responses+lines -> ValueError/exit 2);
no-network. M1–M5 suites stay green.
