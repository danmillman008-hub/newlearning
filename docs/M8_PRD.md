# Gramophone M8 — Product Requirements: Flash live

## 1. Goal
Flip the Gemini backend live the way the architecture always promised:
one flag, no redesign. Every LLM-calling stage (`m2 author`, `m5 quest`
authoring, `m6` full chain) gains `--llm flash`; the default stays the
free deterministic Mock. The suite never touches the network or a key;
one operator-run live quest proves the product, with requests/tokens
logged.

## 2. Backend selection
`--llm mock` (default) = today's behavior exactly. `--llm flash` =
`GeminiFlashLLM` (model `gemini-3.5-flash-lite`, `FLASH_MODEL` still
overrides); without `GEMINI_API_KEY` it fails fast with a ValueError
naming the flag and the variable (CLI: exit 2). Keys live only in the
environment or the constructor arg — never in code, tests, fixtures,
docs, or reports.

## 3. Quota discipline (hard requirements)
- Transient failures (HTTP 429/5xx, network errors) retry max 3 times
  with 2s/4s backoff between the three tries inside `complete()`;
  tokens are spent only on
  successful calls; budgets keep their fail-fast behavior.
- The shipped suite performs ZERO live calls (Mock + monkeypatched
  transport only).
- Live acceptance is exactly one full-chain quest plus the tiny
  bring-up probe already spent; its request/token counts go in
  M8-REPORT.md.

## 4. Threading
`llm` passes `m6 -> break_file` (every chapter) and `m6 -> m5 ->
author_beats`; `m2 author` resolves it directly. `None` everywhere
preserves current Mock/fallback behavior bit-for-bit.

## 5. Non-goals
No new stages or packages; no prompt redesign; no streaming; no key
management features; no M4 grading changes (validators stay local).

## 6. Acceptance
- Full suite green with no key and no network.
- `--llm mock` outputs == pre-M8 outputs for the same inputs.
- `--llm flash` without a key exits 2 on m2/m5/m6 with a clear message.
- One live `--llm flash` quest completes; model/requests/tokens/verdict
  recorded in M8-REPORT.md.
