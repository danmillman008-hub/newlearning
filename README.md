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
- **M3** (`gramophone_m3/`): chapter v1s → namespaced book graph, plus
  live play (stdin or scripted attempts) with retry cap and save/resume.
  Reuses M1+M2 only. See `docs/M3_PRD.md`, `docs/M3_ARCHITECTURE.md`,
  `M3-REPORT.md`.
- **M4** (`gramophone_m4/`): adaptive quest play — next-beat policy loop
  (mastered → fringe → `next_beat`) grading each step through M3 with
  transcript + completion reasons + save/resume. Reuses M1+M2+M3 only
  (zero modification). See `docs/M4_PRD.md`,
  `docs/M4_ARCHITECTURE.md`, `M4-REPORT.md`.
- **M5** (`gramophone_m5/`): book quest — chapters → merged book graph →
  authored beats → adaptive quest in one command, plus the unified
  `gramophone` CLI (`gramophone {m1|m2|m3|m4|quest}`). Pure orchestration
  over M2+M3+M4 (zero modification). See `docs/M5_PRD.md`,
  `docs/M5_ARCHITECTURE.md`, `M5-REPORT.md`.

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

# M3: merge chapters, then play live (or scripted)
gramophone-m3 merge out/ch1/knowledge-graph.json out/ch2/knowledge-graph.json --out out/book --names ch1 ch2
gramophone-m3 play out/m2/beats.json --script fixtures/sample_script.json --out out/play
echo "q1|q1-check|Mean" | gramophone-m3 play out/m2/beats.json --out out/live

# M4: adaptive quest (golden: VISITED=8 COMPLETION=quest_complete)
gramophone-m4 play fixtures/sample_beats.json --graph fixtures/fringe_graph.json --responses fixtures/m4_responses.txt --out out/quest

# M5: book quest end-to-end (chapters -> quest) + unified CLI
gramophone-m5 fixtures/chapter_a.json fixtures/chapter_b.json --responses fixtures/m5_responses.txt --out out/quest
gramophone quest fixtures/chapter_a.json fixtures/chapter_b.json --responses fixtures/m5_responses.txt --out out/quest2

# Full suite (132 tests, M1+M2+M3+M4+M5)
python3 -m pytest tests/ -q -o addopts=''
```

Built through MetaGPT (product → architecture → implementation agents)
with the assistant wired in as the model. MIT licensed.
