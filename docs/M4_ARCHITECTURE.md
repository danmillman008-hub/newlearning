# Gramophone M4 — System Architecture

## 1. Module layout
- gramophone_m4/adaptive.py: run_quest(beats_data, v1_graph, responses,
  actor="learner", max_retries=1, max_steps=1000, restore=None,
  store=None) -> (session, state, transcript). Policy loop per pick:
  mastered = {i: p >= adapt.MASTERED_THRESHOLD}; fringe =
  set(spacing.fringe(sorted(mastered), item_ids, edges)); flow rebuilt by
  replaying state's flow_results; beat = adapt.next_beat(beats, visited,
  mastery, fringe, flow); None -> classify completion. The picked beat's
  checks bind the next responses (missing -> responses_exhausted);
  check-less beats emit experienced + visited with no attempts. Each
  step grades through gramophone_m3.live.play_session with restore
  chaining (retry/skip/xapi/step inherited); cumulative skipped via
  attempt offsets, retries summed; transcript appended per graded attempt
  {beat, check, response, score, max_score, success}.
- gramophone_m4/pipeline.py: run_quest_file(beats_path, graph_path,
  outdir, responses_path=None, response_lines=None, save=None,
  resume=None, actor="learner", max_retries=1, max_steps=1000): M2
  beats validation + v1 shape check (items/surmise lists); response
  lines are bare responses (json.loads, raw string on failure; blank
  lines ignored); exactly one of responses_path/response_lines required
  (CLI feeds stdin as lines); session.json + xapi.jsonl (fresh unless
  resume) + save + M4-REPORT.md quest section (append if present).
- gramophone_m4/cli.py: gramophone-m4 play BEATS --graph V1 --out
  OUTDIR [--responses FILE] [--save F] [--resume F] [--actor A]
  [--max-retries N] [--max-steps N]; stdin lines when no --responses
  (prompts to stderr on tty); exits 0/2/1; SESSION + COMPLETION lines.
- Reuse imports: gramophone_m1.spacing; gramophone_m2.story_model,
  gramophone_m2.adapt; gramophone_m3.live (play_session, save_state,
  load_state); gramophone_m2.xapi (store). No M1/M2/M3 modifications.

## 2. File structure
gramophone_m4/__init__.py, adaptive.py, pipeline.py, cli.py;
fixtures/fringe_graph.json (8 items chaining central-tendency->mean->
median->mode->dispersion->variance->standard-deviation->correlation);
fixtures/m4_responses.txt (6 golden responses incl. one fail+retry);
tests/test_adaptive.py; docs/M4_PRD.md, docs/M4_ARCHITECTURE.md;
M4-REPORT.md (generated); pyproject.toml (adds gramophone-m4 script).

## 3. Data schemas
- transcript entry: {beat, check, response, score, max_score, success}.
- completion: {reason, picks, visited}.
- session: M2 session shape plus transcript, completion, skipped,
  retries_used.

## 4. CLI spec
gramophone-m4 play BEATS --graph V1 --out OUTDIR [--responses FILE]
[--save FILE] [--resume FILE] [--actor NAME] [--max-retries N]
[--max-steps N]. stdout: SESSION VISITED=v ATTEMPTS=a PASSED=p XP=x
LEVEL=l STREAK_MAX=s SKIPPED=k RETRIES=r COMPLETION=reason.

## 5. Data flow
beats + v1 + responses -> pick loop (M3-graded steps, M3-chained state)
-> session.json + xapi.jsonl + M4-REPORT.md. No network, no wall time.

## 6. Key algorithms
- Pick loop: mastered->fringe->flow-replay->next_beat; bind checks in
  beat.checks order; exhaustion mid-beat ends the quest (picked beat is
  NOT visited unless at least its experienced event fired — precisely:
  experienced fires inside the M3 step on first grading, so an unattempted
  beat stays unvisited).
- Chaining: per-step restore = running state; attempt_offset +=
  len(step_attempts); global skipped = [i+offset]; retries summed;
  transcript rows carry global order. Final session = last step session
  + transcript + completion + global skipped/retries (zero-step quest
  builds the empty session from the initial state).
- Completion classification at next_beat None: all beats visited ->
  quest_complete else gated; responses run out -> responses_exhausted;
  picks > max_steps -> max_steps (checked before picking).
- Bare-response parsing: json.loads per line, raw string fallback.

## 7. Test plan
test_adaptive: golden transcript/order/completion + counts on M2 sample
beats + fringe graph + response stream; fringe-pick policy on a branched
2-beat fixture (fringe item wins); gated stop (unready remainder);
responses_exhausted mid-quest; check-less beats visited; mid-quest
save/resume == whole run (session + xapi bytes); CLI golden + exits
(bad graph, bad responses); determinism (two runs identical); no-network.
Full M1+M2+M3 suites stay green.
