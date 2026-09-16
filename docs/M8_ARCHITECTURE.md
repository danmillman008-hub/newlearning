# Gramophone M8 — System Architecture: Flash live

## 1. Patch inventory (only these files change)
- EDIT `gramophone_m1/llm_client.py`: `DEFAULT_MODEL =
  "gemini-3.5-flash-lite"`; new module fn `flash_llm_or_raise()` (key
  present -> `GeminiFlashLLM()`, else `ValueError("--llm flash needs
  GEMINI_API_KEY ...")`); `complete()` retries transient failures (HTTP
  429/5xx + URLError, 3 tries, 2/4/8s backoff) with tokens spent only on
  success. Nothing else in the file changes.
- EDIT `tests/test_pipeline.py`: default-model assertion ->
  gemini-3.5-flash-lite; + retry tests (monkeypatched urlopen).
- EDIT `gramophone_m2/cli.py`: author `--llm` choices mock/none/flash;
  flash branch calls `flash_llm_or_raise()` (import from M1).
- EDIT `gramophone_m5/bookquest.py`: `run_book_quest(..., llm=None)` ->
  `author_beats(book, llm=llm)`.
- EDIT `gramophone_m5/cli.py`: quest `--llm {mock,flash}` (default
  mock); flash branch calls `flash_llm_or_raise()`.
- EDIT `gramophone_m6/fullchain.py`: `run_full_chain(..., llm=None)`:
  None = current per-chapter `default_llm()` Mock path incl. loud
  cassette check; given llm used for every `break_file` + forwarded to
  `run_book_quest`.
- EDIT `gramophone_m6/cli.py`: `--llm {mock,flash}` (default mock).
- NEW `tests/test_llm_backend.py` (§6).
- EDIT `pyproject.toml`: version 0.8.0 (no new deps).
- docs/M8_PRD.md, docs/M8_ARCHITECTURE.md (this file); M8-REPORT.md.

## 2. File tree (changed/new only)
```
gramophone_m1/llm_client.py   (edit: model + helper + retry)
tests/test_pipeline.py        (edit: assertion + retry tests)
gramophone_m2/cli.py          (edit: flash choice)
gramophone_m5/bookquest.py    (edit: llm param)
gramophone_m5/cli.py          (edit: --llm flag)
gramophone_m6/fullchain.py    (edit: llm param)
gramophone_m6/cli.py          (edit: --llm flag)
tests/test_llm_backend.py     (new)
pyproject.toml                (edit: 0.8.0)
```

## 3. Backend-resolution semantics
- `m2 author`: mock = STORY MockLLM (today); none = rule fallback
  (today); flash = `flash_llm_or_raise()`.
- `m5 quest` / `m6`: mock = `llm=None` down the stack (today's Mock /
  fallback behavior bit-for-bit); flash = one shared
  `flash_llm_or_raise()` instance threaded through.
- Keyless flash anywhere: ValueError -> CLI exit 2 with the flag + env
  var named. Keys never logged, never in files.

## 4. Retry algorithm
In `GeminiFlashLLM.complete()`, around the urlopen: try up to 3 times;
retry on `HTTPError` with code in {429, 500, 502, 503, 504} and on
`URLError`; sleep 2s/4s/8s between tries (skipped when a test patches
it); re-raise the last error after 3 failures. Budget pre-check stays
first (no paid call on a dead budget); `_spent` grows only from the
successful response's usageMetadata.

## 5. CLI flag table
| entry | flag | choices | default | keyless flash |
|---|---|---|---|---|
| m2 author | --llm | mock/none/flash | mock | exit 2 |
| m5 quest / gramophone-m5 | --llm | mock/flash | mock | exit 2 |
| m6 / gramophone m6 | --llm | mock/flash | mock | exit 2 |

## 6. Test plan (tests/test_llm_backend.py + M1 retry tests)
- Helper: keyless -> ValueError mentioning GEMINI_API_KEY (monkeypatch
  delenv); fake key -> returns GeminiFlashLLM, zero calls made.
- Threading (Mock only): `run_book_quest(..., llm=MockLLM(STORY))` on
  chapter_a+b takes the story path (TOKENS>0 in the Author line, quest
  completes); `run_full_chain(..., llm=MockLLM(default))` on the sample
  chapter completes with m1 tokens>0.
- CLIs: m2/m5/m6 `--llm flash` keyless -> exit 2; `--llm mock` e2e on
  chapter_a+b == default outputs.
- Retry: 429/429/ok -> success with one token charge; persistent 500
  -> raises; attempts counted (3).
- Full suite green with no key, no network (socket-blocked meta test
  stays; new tests add no transport beyond monkeypatched urlopen).
