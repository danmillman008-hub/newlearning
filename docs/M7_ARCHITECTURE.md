# Gramophone M7 — System Architecture: ship it

## 1. Patch inventory (only these files change)
- NEW `gramophone_m1/cassettes/mock_default.json` + `mock_story.json`:
  byte-identical copies of the repo-root cassettes.
- EDIT `gramophone_m1/pipeline.py`: `default_cassette_path()` only —
  env override -> bundled (`<package>/cassettes/mock_default.json`) ->
  legacy sibling (`<repo>/cassettes/mock_default.json`). Nothing else
  in the file changes.
- EDIT `gramophone_m5/cli.py`: `from gramophone_m6.cli import main as
  _m6`, `_STAGES["m6"]`, USAGE word. Nothing else changes.
- NEW `TUTORIAL.md` (repo root): §5 sections with quoted goldens.
- NEW `tests/test_packaging.py`, `tests/test_tutorial.py` (§6).
- EDIT `pyproject.toml`: version 0.7.0 + `[tool.setuptools.package-data]
  gramophone_m1 = ["cassettes/*.json"]`. Scripts unchanged.

## 2. File tree (new/changed only)
```
gramophone_m1/cassettes/mock_default.json   (new, bundled)
gramophone_m1/cassettes/mock_story.json     (new, bundled)
gramophone_m1/pipeline.py                   (edit: path fn only)
gramophone_m5/cli.py                        (edit: m6 route only)
TUTORIAL.md                                 (new)
tests/test_packaging.py                     (new)
tests/test_tutorial.py                      (new)
pyproject.toml                              (edit: 0.7.0 + package-data)
docs/M7_PRD.md, docs/M7_ARCHITECTURE.md (this file)
M7-REPORT.md                                (generated ship-check log)
```

## 3. Path-resolution algorithm
```
default_cassette_path():
    if GRAMOPHONE_CASSETTE set: return it          # explicit wins
    bundled = <gramophone_m1 dir>/cassettes/mock_default.json
    if exists(bundled): return bundled             # installed + repo
    return <repo root>/cassettes/mock_default.json # legacy dev layout
```
Repo-root behavior is unchanged (same bytes); installs resolve the
bundled file; a bogus override still yields default_llm() -> None ->
M6's loud ValueError.

## 4. Unified routing (after)
`gramophone {m1|m2|m3|m4|m6|quest}`. (There is deliberately no `m5`
word: `quest` IS the M5 entry.) `m6` routes trailing args to
`gramophone_m6.cli.main` unchanged; exit codes propagate.

## 5. Tutorial sections (TUTORIAL.md)
1. Install (`pip install -e ".[test]"`). 2. Break the sample chapter
   (`gramophone-m1 break ...`, expect `ITEMS=22 EDGES=17 STATES=36000`).
   3. Quest it (`gramophone m6 ... --responses ...`, expect the BOOK +
   SESSION goldens). 4. Save/resume split. 5. Reading `session.json` /
   `M6-REPORT.md`. 6. Unified tour. 7. Next steps (own chapter, Gemini).

## 6. Test plan
- `tests/test_packaging.py`: bundled path preferred with no env set;
  override honored when set; legacy-hidden simulation (run with cwd in
  a bare tmp dir — bundled still resolves, cassette loads, tokens>0);
  bogus override -> M6 ValueError (existing M6 test keeps passing).
- `tests/test_tutorial.py`: executes the tutorial's exact commands (m1
  break, m6 quest via unified, split resume) in tmp_path; asserts the
  quoted goldens + artifact existence + resume==whole.
- Full suite (M1–M6 + 4–5 new tests) green; no other file may differ
  (verified with diff before push).
