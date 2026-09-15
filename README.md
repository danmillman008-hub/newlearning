# Gramophone — local-first textbook-to-quest engine

Turn a textbook chapter into a playable adaptive quest. No servers, no API
keys by default, deterministic (same input = byte-identical output).

- **M1** (`gramophone_m1/`): chapter (PDF/Markdown) → knowledge graph
  (entities/relations → atomic Bloom/DOK-tagged items → prerequisite DAG →
  knowledge states + fringes). See `docs/PRD.md`, `docs/ARCHITECTURE.md`,
  `M1-REPORT.md`.
- **M2** (`gramophone_m2/`): v1 graph → authored beat graph → scripted
  learn session with local validators, BKT mastery, DSR scheduling, flow
  control, and xAPI telemetry. See `docs/M2_PRD.md`,
  `docs/M2_ARCHITECTURE.md`, `M2-REPORT.md`.

LLM access goes through one interface (`gramophone_m1.llm_client`):
`MockLLM` (deterministic cassettes, default, offline) and `GeminiFlashLLM`
(key from `GEMINI_API_KEY`, activates with zero architecture change).

## Quickstart

```bash
pip install -e ".[test]"   # or: pip install pypdf pytest

# M1: chapter -> knowledge graph (golden: ITEMS=22 EDGES=17 STATES=36000)
gramophone-m1 break fixtures/sample_chapter.md --out out/m1

# M2: graph -> beats -> session
gramophone-m2 author out/m1/knowledge-graph.json --out out/m2
gramophone-m2 learn fixtures/sample_beats.json --script fixtures/sample_script.json --out out/m2
gramophone-m2 export-xapi out/m2/xapi.jsonl --out out/m2/export.jsonl

# Full suite (96 tests, M1+M2)
python3 -m pytest tests/ -q -o addopts=''
```

Built through MetaGPT (product → architecture → implementation agents)
with the assistant wired in as the model. MIT licensed.
