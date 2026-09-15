# Gramophone M2 — Product Requirement Document

## 1. Goal
Turn an M1 `knowledge-graph.json` v1 (items + surmise DAG + states + fringe)
into a playable adaptive quest through a local-first Python engine: v1 graph
to authored beat graph to validator-gated beats to BKT-adapted sequencing
with SRS scheduling and xAPI telemetry. M2 never rebuilds M1; it consumes v1
and mirrors M1's engineering shape (MockLLM default, deterministic, pytest
green, CLI golden).

## 2. Users
The same solo learner-developer validating the gramophone concept; later,
external learners playing quests generated from their own textbooks.

## 3. Functional requirements
- FR1 story_model: beat graph JSON (beats with text/choices/requires/teaches/
  checks), load/save, structural validation (unknown ids, dangling choices,
  unreachable beats reported, never silently dropped).
- FR2 author: v1 items+edges to beat-graph draft via LLM role STORY; rule
  fallback (one quest chain per tag-cluster, one beat per item, checks from
  assessment_criteria); provenance {item_id, chunk_id} per beat/check.
- FR3 validators: local deterministic checks (choice/ordering/numeric kinds),
  attempt scoring with partial credit rules, no LLM needed.
- FR4 adapt: per-item BKT mastery (learn/slip/guess/update), fringe-aware
  next-beat selection (ready beats first), flow controller holding success in
  the 70-85% band by adjusting difficulty/order.
- FR5 srs: FSRS-inspired DSR scheduler: per-item stability, due(review)
  scheduling, review() updates from graded attempts.
- FR6 xapi: xAPI actor-verb-object statements (attempted/passed/failed,
  experienced/mastered) to a local append-only JSONL store + export.
- FR7 CLI: gramophone-m2 author GRAPH --out OUTDIR; learn BEATS --script
  SCRIPT --out OUTDIR (scripted attempts, deterministic); export-xapi STORE
  --out FILE. Exit 0/2/1 like M1; stdout SESSION lines with counts.
- FR8 Fixtures plus tests: bundled sample_beats.json (>=8 beats, >=4 checks),
  sample_script.json (passes and fails), mock STORY cassette; pytest suite
  covers model/author/validators/BKT/flow/SRS/session/determinism/budget/
  no-network, plus the full M1 suite stays green.

## 4. Data schemas
- beat: {id, title, text, choices[{label, to}], requires[item-ids],
  teaches[item-ids], checks[check-ids], provenance{item_id, chunk_id}}.
- check: {id, kind, prompt, payload, item_id, max_score}.
- session report: {beats_visited, attempts, passed, xp, level, streak,
  mastery{item-id: p}, flow_in_band_ratio}.
- xAPI: {actor, verb, object, result{score, success}, timestamp}.

## 5. Non-functional requirements
- NFR1 LOCAL-FIRST: JSON/JSONL/markdown only; no servers, vector DB, or cloud.
- NFR2 NO API KEYS: reuse gramophone_m1.llm_client (MockLLM default,
  GeminiFlashLLM optional via GEMINI_API_KEY, lazy, never required).
- NFR3 Provenance: every beat/check cites {item_id, chunk_id} traceable to v1.
- NFR4 Graceful degrade: budget exhaustion yields fewer beats/checks, never
  wrong ones; exit nonzero only on invalid input or internal error.
- NFR5 Reproducibility: same inputs + MockLLM = byte-identical outputs
  (modulo timestamps); seeded documented order for all selections.

## 6. Out of scope (M3+)
Graphics/UI clients, multiplayer/co-op, voice/dialogue tutors, dashboards and
analytics frontends, live (non-scripted) interactive sessions.

## 7. Acceptance criteria
AC1: author on M1's golden v1 exits 0 and writes beats JSON. AC2: sample quest
meets FR8 minimums (>=8 beats, >=4 checks). AC3: pytest fully green (M1+M2).
AC4: M2-REPORT.md present with session counts plus budgets. AC5: no network
calls during default runs (MockLLM). AC6: scripted learn session is
deterministic (two runs identical modulo timestamps).
