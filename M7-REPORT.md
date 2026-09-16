# Gramophone M7 — Run Report

## Ship checks
CASSETTE_BUNDLED=gramophone_m1/cassettes/mock_default.json (byte-identical to repo copy)
CASSETTE_RESOLUTION=override -> bundled -> legacy (bare-cwd proven, override honored)
UNIFIED_ROUTES=m1 m2 m3 m4 m6 quest (m6 --help exits 0; gramophone m6 == gramophone-m6)
TUTORIAL=steps 1-3 green (ITEMS=22 EDGES=17; BOOK 22/17/22/22; SESSION quest_complete; resume == whole)
SUITE=144 passed (138 + 6 new)
