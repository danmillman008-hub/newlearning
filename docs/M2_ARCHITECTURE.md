# Gramophone M2 — System Architecture

## 1. Module layout
- gramophone_m2/story_model.py: beat graph load/save/validate.
  load_beats(path)->BeatGraph; validate(beats)->[issue] (unknown beat ids in
  choices/requires/teaches/checks, dangling choice targets, unreachable
  beats); all issues reported, nothing silently dropped.
- gramophone_m2/author.py: author_beats(v1_graph, llm, budget)->beats dict.
  LLM role STORY drafts beats/checks with provenance {item_id, chunk_id};
  deterministic rule fallback (one quest chain per tag-cluster, one beat per
  item in topo order, checks synthesized from assessment_criteria) when the
  LLM is unavailable or the budget is exhausted (fewer beats, never wrong).
- gramophone_m2/validators.py: grade(check, response)->{score, max_score,
  success}. Kinds: choice (exact label match), ordering (normalized
  Kendall-tau distance -> partial credit), numeric (tolerance band, default
  relative 1e-6). Pure local, no LLM.
- gramophone_m2/adapt.py: BKT per item: p_init/p_learn/p_slip/p_guess,
  update(mastery, correct)->mastery; next_beat(beats, state, mastery,
  fringe)->beat (ready beats = requires subset-of mastered-or-visited;
  prefer fringe items, then lowest mastery); flow controller: track rolling
  success rate, hold 70-85% by reordering (easier/harder ready beat) or
  inserting review beats; report flow_in_band_ratio.
- gramophone_m2/srs.py: DSR scheduler per item: stability S, due() boolean
  from elapsed-vs-interval; review(item, grade)->updates S (correct: S grows,
  wrong: S shrinks), schedules next due; session clock is logical (step
  counter), no wall time, deterministic.
- gramophone_m2/xapi.py: XAPIStore(path): append(actor, verb, object,
  result, timestamp-step); verbs attempted/passed/failed/experienced/
  mastered; local append-only JSONL; export_xapi(store, path) copies +
  validates each line.
- gramophone_m2/pipeline.py: run_author(graph_path, outdir, llm, budget):
  load v1 -> author -> validate -> write beats.json + M2-REPORT.md section;
  run_learn(beats_path, script_path, outdir): scripted attempts ->
  grade -> BKT/SRS/flow updates -> xAPI append -> session.json + report.
  Budgets checked before each LLM call (M1 pattern).
- gramophone_m2/cli.py: argparse entry gramophone-m2 with subcommands
  author/learn/export-xapi; exit 0 ok, 2 bad input, 1 internal error.
- Reuse: from gramophone_m1.llm_client import LLMClient, MockLLM,
  GeminiFlashLLM. No duplication; M1 stays importable standalone.

## 2. File structure
gramophone_m2/__init__.py, story_model.py, author.py, validators.py,
adapt.py, srs.py, xapi.py, pipeline.py, cli.py;
fixtures/sample_beats.json (>=8 beats), fixtures/sample_script.json
(scripted attempts incl. passes and fails); cassettes/mock_story.json
(STORY role cassette for MockLLM); tests/test_story_model.py,
test_author.py, test_validators.py, test_adapt.py, test_srs.py,
test_session.py; docs/M2_PRD.md, docs/M2_ARCHITECTURE.md; M2-REPORT.md
(generated); pyproject.toml (adds gramophone-m2 script, keeps pypdf/pytest).

## 3. Data schemas
- beat: {id, title, text, choices[{label, to}], requires[item-ids],
  teaches[item-ids], checks[check-ids], provenance{item_id, chunk_id}}.
- check: {id, kind, prompt, payload, item_id, max_score}.
  payload: choice{options[], answer}, ordering{items[], answer[]},
  numeric{answer, tolerance}.
- session report: {beats_visited, attempts, passed, xp, level, streak,
  mastery{item-id: p}, flow_in_band_ratio}.
- xAPI: {actor, verb, object, result{score, success}, timestamp}.

## 4. CLI spec
gramophone-m2 author GRAPH --out OUTDIR [--token-budget N];
gramophone-m2 learn BEATS --script SCRIPT --out OUTDIR;
gramophone-m2 export-xapi STORE --out FILE.
stdout SESSION lines: BEATS=n CHECKS=m (author); VISITED=v ATTEMPTS=a
PASSED=p XP=x LEVEL=l STREAK=s (learn). Exits: 0 ok, 2 bad input,
1 internal error.

## 5. Data flow
v1 knowledge-graph.json -> author_beats (STORY or fallback) -> beats.json
(validated) -> run_learn scripted session (validators -> BKT/SRS/flow ->
xAPI JSONL) -> session.json + M2-REPORT.md. No network on default path.

## 6. Key algorithms
- BKT update: p_lo = p + (1-p)*p_learn; given correct:
  p' = p_lo*(1-p_slip)/(p_lo*(1-p_slip)+(1-p_lo)*p_guess); given wrong:
  p' = p_lo*p_slip/(p_lo*p_slip+(1-p_lo)*(1-p_guess)).
- next_beat: candidates = beats with requires mastered-or-visited and not
  yet visited; score = fringe_bonus + (1-mastery) + flow_adjust; pick max,
  tie-break by beat id order (deterministic).
- Flow: rolling success over last 10 attempts; in-band 0.70-0.85; above ->
  prefer harder (higher dok teaches); below -> prefer easier/review due.
- DSR: interval = S steps; due when steps_since_review >= interval;
  review correct: S *= (1 + grade); wrong: S = max(1, S*grade).
- Validator scoring: choice exact (1/0); ordering 1 - 2*inversions/(n*(n-1))
  floored at 0; numeric |r-a| <= tol -> 1 else 0.

## 7. Test plan
Unit per module with MockLLM/cassette fixtures (model load/validate incl.
dangling/unreachable; author fallback beats+provenance; validator kinds +
partial credit; BKT math; next_beat determinism; flow band; SRS due/review;
xAPI append/export); golden learn session on sample fixtures (counts
asserted); determinism (two runs identical modulo timestamps); budget
(tiny budget -> fewer beats, exit 0); no-network (socket blocked);
full M1 suite stays green.
