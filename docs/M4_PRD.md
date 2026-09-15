# Gramophone M4 — Product Requirement Document

## 1. Goal
Sequence sessions by the fringe-aware next_beat policy over live outcomes
instead of fixed scripts: mastered items to fringe to next pick to bound
checks to M3-graded attempts, repeating to completion. M4 is pure policy
over reused M1/M2/M3 engines — no new learning science, no duplicated
logic. Local-first, deterministic.

## 2. Users
The same solo learner-developer; later, learners on adaptive quests that
respond to every answer.

## 3. Functional requirements
- FR1 adaptive stepper: each pick computes mastered set (p>=0.95),
  fringe via M1 spacing over the v1 graph, next via M2 next_beat with the
  live flow tracker; the picked beat's checks bind the next responses and
  grade through the M3 engine with restore chaining; check-less beats are
  visited with no attempts.
- FR2 completion: quest_complete (all beats visited), gated (beats remain
  but none ready), responses_exhausted, max_steps; every run returns an
  exact transcript [{beat, check, response, score, success}].
- FR3 save/resume: M3 state save/load reused; policy is stateless (each
  pick recomputed), so resume continues identically.
- FR4 CLI: gramophone-m4 play BEATS --graph V1 --out OUTDIR
  [--responses FILE | stdin] [--save/--resume] [--actor] [--max-retries]
  [--max-steps]; exits 0/2/1; SESSION lines plus COMPLETION=reason.
- FR5 Fixtures plus tests: fringe_graph.json (8-item chain over the M2
  sample beats' items); m4_responses.txt golden stream (one fail+retry);
  suite covers golden transcript/order/completion, fringe-pick policy on
  branched beats, gated stop, exhaustion, check-less visits, mid-quest
  resume, CLI, determinism, no-network; M1+M2+M3 suites stay green.

## 4. Data schemas
- transcript entry: {beat, check, response, score, max_score, success}.
- completion: {reason, picks, visited}.
- session: M2 session shape plus transcript, completion, skipped,
  retries_used.

## 5. Non-functional requirements
- NFR1 LOCAL-FIRST: JSON/JSONL/stdin-stdout only; no servers or cloud.
- NFR2 REUSE-ONLY: M1/M2/M3 imported, never modified; grading, BKT, DSR,
  retry, xAPI, and state logic all inherited, none reimplemented.
- NFR3 Determinism: same beats + graph + responses = byte-identical
  session and transcript (modulo timestamps).
- NFR4 Graceful completion: every ending is a named reason with full
  outputs; never a crash, never a partial write.

## 6. Out of scope (M5+)
LLM-driven dialogue, multiplayer/co-op, voice tutors, graphics/UI clients,
analytics frontends.

## 7. Acceptance criteria
AC1: CLI golden transcript/order/completion match hand values. AC2: policy
tests prove fringe preference + gated stop on branched fixtures. AC3:
pytest fully green (M1+M2+M3+M4). AC4: M4-REPORT.md with quest counts.
