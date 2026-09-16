# Gramophone Tutorial — your first quest in 5 minutes

You need: Python 3.11+, a terminal, the repo checked out. No API keys,
no network: everything below runs on the deterministic Mock backend.

## 0. Install

```bash
pip install -e ".[test]"   # or: pip install pypdf pytest
```

## 1. Break a chapter into a knowledge graph

```bash
gramophone-m1 break fixtures/sample_chapter.md --out out/m1
```

Expect:

```
ITEMS=22 EDGES=17 STATES=36000 FRINGE0=8 TOKENS=5100
```

Outputs in `out/m1/`: `knowledge-graph.json` (the v1: 22 items, 17
prerequisite edges, 36000 knowledge states), plus the v0.1 graph and
`M1-REPORT.md`.

## 2. Quest it — raw chapter to finished quest in one command

```bash
gramophone m6 fixtures/sample_chapter.md --names chap \
  --responses fixtures/m6_responses.txt --out out/quest
```

Expect the M1 line again, then:

```
BOOK CHAPTERS=1 ITEMS=22 EDGES=17 BEATS=22 CHECKS=22
SESSION VISITED=22 ATTEMPTS=23 PASSED=22 XP=220 LEVEL=3 STREAK_MAX=20 SKIPPED=0 RETRIES=1 COMPLETION=quest_complete
```

The quest visited all 22 authored beats; one check failed once and was
retried (`RETRIES=1`), hence 23 attempts. Same inputs always give these
exact numbers.

## 3. Save and resume mid-quest

Quests resume exactly. Split the stream after 2 lines and play it in two
parts (the first part ends with `responses_exhausted` — that is normal):

```bash
head -2 fixtures/m6_responses.txt > /tmp/first.txt
tail -n +3 fixtures/m6_responses.txt > /tmp/rest.txt
gramophone-m6 fixtures/sample_chapter.md --names chap \
  --responses /tmp/first.txt --save /tmp/quest.json --out out/part
gramophone-m6 fixtures/sample_chapter.md --names chap \
  --responses /tmp/rest.txt --resume /tmp/quest.json --out out/part
```

The resumed run ends `COMPLETION=quest_complete` with a `session.json`
identical to step 2's.

## 4. Read the quest

- `out/quest/session.json`: counts, BKT mastery per item, and the full
  `transcript` (23 rows: beat, check, response, score, success).
- `out/quest/M6-REPORT.md`: the chapters + quest summary.
- `out/quest/xapi.jsonl`: 68 telemetry statements (experienced /
  attempted / passed / failed).
- `out/quest/m1_chap/`: the kept M1 provenance for the chapter.

## 5. Tour the unified CLI

```bash
gramophone m1 --help      # chapter -> knowledge graph
gramophone m2 --help      # graph -> beats -> scripted session
gramophone m3 --help      # merge chapters, live play
gramophone m4 --help      # adaptive quest over a beat graph
gramophone m6 --help      # raw chapters -> quest (this tutorial)
gramophone quest --help   # book quest over v1 graphs
```

## 6. Next steps

- Point step 1–2 at your own chapter (`.md` or `.pdf`): the response
  stream must answer the authored checks — start from the `beats.json`
  answers the way `fixtures/m6_responses.txt` does.
- Cap cost/scale with `--max-items` / `--token-budget`.
- When your Gemini key arrives, set `GEMINI_API_KEY`: the Flash backend
  activates with zero architecture change (same CLI, same goldens
  modulo LLM wording).
