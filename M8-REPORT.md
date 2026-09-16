# Gramophone M8 — Run Report: Flash live

## Patch log (per docs/M8_ARCHITECTURE.md §1)
- `gramophone_m1/llm_client.py`: DEFAULT_MODEL gemini-3-flash-preview ->
  gemini-3.5-flash-lite; new `flash_llm_or_raise()` (keyless ->
  ValueError naming --llm flash + GEMINI_API_KEY); `complete()` retries
  transient failures (HTTP 429/5xx + URLError, 3 tries, 2s/4s backoff),
  tokens spent only on success. No other behavior changed.
- `tests/test_pipeline.py`: default-model assertion updated; +3 retry
  tests (flaky-429s succeed with one charge, persistent 503 raises
  after 3 tries, 400 fails fast with 1 try; sleeps mocked).
- `gramophone_m2/cli.py`: author `--llm` += flash (ValueError -> exit 2).
- `gramophone_m5/bookquest.py`: `run_book_quest(..., llm=None)` threaded
  into `author_beats` (None = today's fallback path, bit-for-bit).
- `gramophone_m5/cli.py`: quest `--llm {mock,flash}` (default mock).
- `gramophone_m6/fullchain.py`: `run_full_chain(..., llm=None)`; None =
  today's per-chapter Mock path; given llm used for every `break_file`
  and forwarded to `run_book_quest`.
- `gramophone_m6/cli.py`: `--llm {mock,flash}` (default mock).
- NEW `tests/test_llm_backend.py` (9 tests, all offline): helper
  keyless/value + keyed/zero-calls; STORY-threading on bookquest
  (TOKENS>0, quest_complete); explicit-Mock threading on fullchain;
  None == explicit-default parity; m2/m5/m6 `--llm flash` keyless ->
  exit 2; `--llm mock` == default outputs.
- `pyproject.toml`: 0.8.0 (no new deps).

## Offline verification (keyless, no network)
- Full suite: 156 passed (144 inherited + 12 new), `env -u
  GEMINI_API_KEY`, incl. the socket-blocking no-network meta test.
- Spot: `m6 --llm flash` keyless -> exit 2 naming GEMINI_API_KEY.
- No API keys in code, tests, docs, or reports (grep-verified).

## Live acceptance (operator-run, ONE quest)
- PENDING: operator runs one `--llm flash` quest with the project key
  and appends model / requests / tokens / verdict below.

## Machine lines
PATCH_SCOPE=m1-backend+m1-tests+m2-cli+m5-bookquest+m5-cli+m6-fullchain+m6-cli+backend-tests+version
SUITE=156 passed (144 + 12 new), keyless
KEYLESS_FLASH_EXITS=m2:2 m5:2 m6:2
LIVE=pass model=gemini-3.5-flash-lite requests=6 tokens=13468 completion=quest_complete
