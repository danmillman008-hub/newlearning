# Gramophone M3 — System Architecture

## 1. Module layout
- gramophone_m3/merge.py: merge_graphs(v1_list, chapter_names) -> book v1.
  Namespaces every item id as {chapter}:{id} (chapters in input order,
  items sorted by id within); remaps surmise edges to namespaced ids;
  unions competences namespaced; recomputes states via
  gramophone_m1.spacing.enumerate_states(ids, edges) and fringe_cache via
  spacing.fringe([], ids, edges) (same {"": [...]} shape as M1);
  metadata{chapters[], version, provenance}. Empty list or duplicate
  chapter names -> ValueError. Chapters missing items/surmise keys ->
  ValueError (fail before writing anything).
- gramophone_m3/live.py: play_session(beats_data, attempts, ...) where
  attempts is any iterable of {beat_id, check_id, response} (script list
  or parsed stdin lines). Reuses gramophone_m2.validators.grade,
  adapt.bkt_update/is_mastered/FlowTracker, srs.DSR, xapi.XAPIStore —
  no duplicated logic. max_retries (default 1): a failed attempt may be
  immediately retried by consuming the next matching attempt for the same
  check. save_state(path)/load_state(path): JSON {mastery, srs
  {stability, last_review}, visited, xp, streak, streak_max, step};
  resume reopens the xAPI store (append) and continues step counts.
  Returns the M2-identical session dict.
- gramophone_m3/pipeline.py: run_merge(paths, outdir, names=None) loads
  each v1 (FileNotFound/JSON/shape -> ValueError), merges, writes
  book-graph.json + M3-REPORT.md merge section; run_play(beats_path,
  outdir, script=None, input_lines=None, save=None, resume=None):
  script xor input_lines xor resume-new... precisely: attempts come from
  script JSON, or input_lines (one "beat_id|check_id|response" per line,
  response parsed as JSON literal, fallback raw string), or stdin when
  neither is given (CLI only); writes session.json + xapi.jsonl, appends
  the play section to M3-REPORT.md.
- gramophone_m3/cli.py: gramophone-m3 merge V1 [V1...] --out OUTDIR
  [--names A B...]; gramophone-m3 play BEATS --out OUTDIR [--script S]
  [--save F] [--resume F]; exits 0/2/1; MERGED CHAPTERS=n ITEMS=i EDGES=e
  STATES=s + M2-style SESSION lines.
- Reuse imports (only these cross-package deps): gramophone_m1.spacing;
  gramophone_m2.story_model, validators, adapt, srs, xapi. M1/M2 never
  modified.

## 2. File structure
gramophone_m3/__init__.py, merge.py, live.py, pipeline.py, cli.py;
fixtures/chapter_a.json, fixtures/chapter_b.json (tiny synthetic v1s:
3+2 items, one shared label across chapters to prove namespacing);
tests/test_merge.py, tests/test_play.py; docs/M3_PRD.md,
docs/M3_ARCHITECTURE.md; M3-REPORT.md (generated); pyproject.toml (adds
gramophone-m3 script).

## 3. Data schemas
- book graph: v1 shape (metadata/items/competences/surmise_relations/
  competence_relations/surmise/states/fringe_cache) with namespaced ids
  and recomputed states/fringe_cache.
- session state: {mastery, srs{stability, last_review}, visited, xp,
  streak, streak_max, step}.
- play session: identical to M2 session.json + xAPI statement shapes.

## 4. CLI spec
gramophone-m3 merge V1 [V1...] --out OUTDIR [--names A B...]
(names default to file stems; count must match file count).
gramophone-m3 play BEATS --out OUTDIR [--script SCRIPT] [--save FILE]
[--resume FILE] (no script + no resume + tty stdin = live prompts;
piped stdin lines work too). stdout MERGED ... / SESSION ... lines.

## 5. Data flow
chapter v1s -> merge_graphs -> book-graph.json (+author it with M2 later);
beats + attempts -> play_session (M2 loop, M2 shapes) -> session.json +
xapi.jsonl + report. No network, no wall time.

## 6. Key algorithms
- Namespacing: new_id = f"{chapter}:{old_id}" for items; competences
  likewise; surmise pairs remapped; requires dedupe by (src, dst).
- Retry: on fail with retries left, peek the next attempt; if it targets
  the same check, consume it as the retry, else the fail stands and the
  attempt is processed normally.
- Resume: load state (validate keys, ValueError otherwise); step counter
  continues from state; xAPI store opened in append mode (statement
  timestamps continue); visited/mastery/srs/xp/streak restored.
- Attempt-line parsing: split on first two "|"; response parsed with
  json.loads, raw string on failure (numbers/bools/lists work).

## 7. Test plan
test_merge: golden counts on chapter_a/b (items/edges/states exact),
namespacing proof (shared label -> two ids), dup-name + empty + bad-shape
rejections, determinism (two merges byte-identical). test_play: scripted
golden equals M2 learn counts exactly; input_lines interactive incl. retry
consumes-next-matching; save/resume roundtrip byte-identical state +
resume-continues counts; CLI merge/play goldens + exit codes; no-network
(socket blocked). Full M1+M2 suites stay green.
