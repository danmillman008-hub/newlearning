# Gramophone M7 — Product Requirements: ship it

## 1. Goal
Close the three known shippability gaps so Gramophone is a real
product, not a repo-root demo: (a) the Mock cassette must survive `pip
install` (today only the repo-root sibling exists, so installed copies
silently degrade); (b) the unified `gramophone` CLI must route `m6`
(today frozen at m1–m4+quest); (c) a verified end-to-end tutorial must
take a new user from install to finished quest.

## 2. Packaging
`gramophone_m1/cassettes/{mock_default,mock_story}.json`, byte-identical
to the repo-root files. `default_cassette_path()`: env override first,
then bundled (package dir), then legacy sibling. pyproject
`package-data` ships the bundled files. Behavior from the repo root is
unchanged (same bytes either way); installed copies now resolve the
cassette instead of degrading. The repo-root `cassettes/` directory and
all M1 tests stay as-is.

## 3. Unified m6 route
One import + one dict entry + USAGE word in `gramophone_m5/cli.py`.
`gramophone m6 ...` behaves exactly like `gramophone-m6 ...` (same
parser, same codes). No import cycle: m6 imports `m5.bookquest` only.

## 4. Tutorial
`TUTORIAL.md`: install, break the sample chapter, quest it with the
golden stream (expected BOOK/SESSION lines quoted), split save/resume,
reading session.json/M6-REPORT.md, unified-CLI tour, and next steps
(your own chapter; Gemini key later). `tests/test_tutorial.py` executes
the tutorial's exact commands in a tmp dir and asserts outputs + goldens
— the tutorial cannot rot without breaking the suite.

## 5. Non-goals
No engine changes (path fn + route only); no new packages; no Gemini
wiring (lands with the key, zero-change); no HTML reports.

## 6. Acceptance
- Bundled cassette resolves with the legacy path hidden (test-proven).
- `gramophone m6 --help` exits 0; `gramophone m6` == `gramophone-m6`.
- Tutorial sequence green with quoted goldens.
- Full suite green; pyproject 0.7.0; M7-REPORT.md written.
