# Gramophone M3 — Product Requirement Document

## 1. Goal
Lift M1 single-chapter graphs to merged book graphs and M2 scripted
sessions to live interactive play through one small package reusing M1+M2:
chapter graphs to namespaced book graph; beats to live attempts (stdin or
scripted) with retry plus save/resume. M3 adds no new learning science —
it scales and plays what M1+M2 built. Local-first, deterministic.

## 2. Users
The same solo learner-developer; later, learners playing full-book quests
live from their own textbooks.

## 3. Functional requirements
- FR1 merge: N chapter v1 graphs to one book v1: item ids namespaced
  {chapter}:{id} (input order, sorted within); surmise edges remapped;
  competences unioned (namespaced); states+fringe recomputed via M1
  spacing; duplicate chapter names and empty input rejected (ValueError).
- FR2 live play: attempt iterator (stdin lines or scripted list) over a
  beat graph: grade/BKT/SRS/flow/xAPI all reused from M2; max_retries
  (default 1 retry after a fail); output shapes identical to M2
  session.json/xapi.jsonl.
- FR3 save/resume: session state JSON {mastery, srs, visited, xp, streak,
  step} roundtrips byte-identical; resume continues (attempts append,
  xAPI store reopens, counts continue).
- FR4 CLI: gramophone-m3 merge V1 [V1...] --out OUTDIR [--names ...];
  gramophone-m3 play BEATS --out OUTDIR [--script SCRIPT | stdin]
  [--save F] [--resume F]. Exits 0/2/1; MERGED + SESSION stdout lines.
- FR5 Fixtures plus tests: chapter_a/b.json tiny v1s (3+2 items, shared
  label case); scripted play golden equals M2 learn counts; suite covers
  merge golden/rejections/determinism, play scripted/interactive/retry/
  save-resume/CLI/no-network; M1+M2 suites stay green.

## 4. Data schemas
- book graph: v1 shape with namespaced item ids, remapped surmise,
  recomputed states, metadata{chapters[], version}.
- session state: {mastery{item: p}, srs{stability, last_review},
  visited[beat-ids], xp, streak, streak_max, step}.
- play session: identical to M2 session report + xAPI shapes.

## 5. Non-functional requirements
- NFR1 LOCAL-FIRST: JSON/JSONL/stdin-stdout only; no servers or cloud.
- NFR2 REUSE-ONLY: M1/M2 modules imported, never modified; no duplicated
  grading/BKT/DSR/xAPI logic.
- NFR3 Determinism: same chapters + same attempts = byte-identical book
  graph and session outputs (modulo timestamps).
- NFR4 Graceful degrade: bad chapter input fails merge with exit 2 and
  writes no partial book; bad beats/script fail play likewise.

## 6. Out of scope (M4+)
Multiplayer/co-op, voice/dialogue tutors, graphics/UI clients, analytics
frontends, live LLM-driven (non-scripted-check) dialogue.

## 7. Acceptance criteria
AC1: merge golden on chapter_a/b exits 0 with exact counts. AC2: scripted
play golden equals M2 learn counts (VISITED=5 ... XAPI=19). AC3: pytest
fully green (M1+M2+M3). AC4: M3-REPORT.md with merge+play sections.
AC5: no network calls on default paths.
