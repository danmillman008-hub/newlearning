# Gramophone M1 — Product Requirement Document

## 1. Goal
Turn ONE textbook chapter (PDF or Markdown) into an inspectable knowledge graph plus knowledge space through a local-first Python pipeline: PDF to text blocks to entity-relation KG to atomic knowledge items (Bloom/DOK tagged) to prerequisite (surmise) relations to enumerated knowledge states plus outer fringes.

## 2. Users
A solo learner-developer validating the gramophone concept; later, the M2 story engine consuming knowledge-graph.json v1.

## 3. Functional requirements
- FR1 pdf_input: read PDF (pypdf) or Markdown; emit text blocks with chunk_id, page, span offsets.
- FR2 kg_extract: blocks to entities plus typed relations (LightRAG-style) via LLM role EXTRACT.
- FR3 itemize: KG to atomic items: id (kebab-case), label, description, bloom (6 levels), knowledge_type (4), dok (1-4), assessment_criteria (ECD), required_competences (CbKST), tags, provenance per item. Enforce atomicity gate: accept only Atomic plus Assessable plus Meaningful; else split or drop and log why.
- FR4 surmise: items to prerequisite edges via LLM role ANALYZE plus deterministic cycle check; output DAG only.
- FR5 spacing: edges to knowledge states (Birkhoff enumeration), fringe(state), Hasse cover listing; cap 50k states, partition by tag-cluster if exceeded.
- FR6 CLI: gramophone-m1 break INPUT --out OUTDIR [--max-items 300] [--token-budget N]; exit 0; print item/edge/state/fringe counts.
- FR7 Fixture plus tests: bundled sample_chapter.md (realistic 2-page statistics excerpt) yields >=15 items, >=10 surmise edges, non-empty fringe from empty state; pytest suite covers gate, DAG, fringe, budgets.
- FR8 Report: M1-REPORT.md records counts plus budgets consumed per run.

## 4. Data schemas
- knowledge-graph.json v0.1: metadata{chapter, version, provenance{source_materials, change_log}}, items[], competences[], surmise_relations[], competence_relations[].
- v1 adds: surmise[[prereq-id, item-id]], states[[item-id...]], fringe computable.

## 5. Non-functional requirements
- NFR1 LOCAL-FIRST: sqlite/JSON/markdown only; no servers, vector DB, or cloud.
- NFR2 NO API KEYS: ONE LLMClient interface; backends: MockLLM (deterministic cassette responses for tests) and GeminiFlashLLM (Google Gemini Flash REST, key from env GEMINI_API_KEY; must activate with zero architecture change).
- NFR3 Provenance: every item cites source chunks {chunk_id, page, span}.
- NFR4 Graceful degrade: on token budget exhaustion produce FEWER outputs, never wrong ones; exit nonzero only on invalid input or internal error.
- NFR5 Reproducibility: same input plus MockLLM yields byte-identical graph (modulo timestamps).

## 6. Out of scope (M2+)
Story beats, story engine, validators, dialogue tutors, FSRS scheduling, dashboards.

## 7. Acceptance criteria
AC1: break sample_chapter.md exits 0 and writes v1 graph. AC2: counts meet FR7 minimums. AC3: pytest fully green. AC4: M1-REPORT.md present with counts plus budgets. AC5: no network calls during default run (MockLLM). AC6: GeminiFlashLLM backend present with client-construction test (no key needed).
