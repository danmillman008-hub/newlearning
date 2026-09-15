# Gramophone M1 — System Architecture

## 1. Module layout
- gramophone_m1/pdf_input.py: PDF (pypdf) or Markdown to blocks [{chunk_id, page, span, text}]. Markdown: page=0, span=char offsets.
- gramophone_m1/kg_extract.py: blocks to KG {entities[{id,label,type,chunk_ids}], relations[{src,rel,dst,chunk_ids}]} via LLMClient role EXTRACT; deterministic regex fallback for tests.
- gramophone_m1/itemize.py: KG to items[] plus competences[] via LLM role ANALYZE; atomicity gate (Atomic plus Assessable plus Meaningful) with split-or-drop plus reason log; provenance attached per item.
- gramophone_m1/surmise.py: items to edges [[prereq,item]] via LLM role ANALYZE; deterministic DFS cycle check; on cycle, drop lowest-confidence edge, log, re-check until DAG.
- gramophone_m1/spacing.py: pure-python KST core: enumerate_states (Birkhoff ideal enumeration over surmise DAG, cap 50000, partition by tag-cluster on overflow), fringe(state), hasse_covers, validate_space.
- gramophone_m1/llm_client.py: LLMClient ABC (complete(role,prompt,budget)->{text,tokens}); MockLLM (cassette dict role->responses, deterministic, token counter); GeminiFlashLLM (REST generateContent, key GEMINI_API_KEY, model gemini-3-flash-preview or configured FLASH_MODEL; lazy import, constructible without key).
- gramophone_m1/pipeline.py: break_file(input, outdir, max_items, token_budget): orchestrates stages, enforces budgets (fewer-never-wrong), writes knowledge-graph.json v0.1 then v1, prints counts, writes M1-REPORT.md.
- gramophone_m1/cli.py: argparse entry gramophone-m1 break INPUT --out OUTDIR [--max-items 300] [--token-budget N].

## 2. File structure
gramophone_m1/__init__.py, pdf_input.py, kg_extract.py, itemize.py, surmise.py, spacing.py, llm_client.py, pipeline.py, cli.py; fixtures/sample_chapter.md; cassettes/mock_default.json; tests/test_pdf_input.py, test_kg_extract.py, test_itemize.py, test_surmise.py, test_spacing.py, test_pipeline.py; docs/PRD.md, docs/ARCHITECTURE.md; M1-REPORT.md (generated); pyproject.toml (pypdf, pytest).

## 3. Data schemas
- v0.1: metadata{chapter,version,provenance{source_materials[],change_log[]}}, items[{id,label,description,bloom,knowledge_type,dok,assessment_criteria,required_competences[],tags[],provenance{chunk_id,page,span}}], competences[{id,label,type}], surmise_relations[], competence_relations[].
- v1 adds: surmise[[prereq,item]], states[[item...]], fringe_cache{state_key:[items]} (optional).

## 4. CLI spec
gramophone-m1 break INPUT --out OUTDIR [--max-items 300] [--token-budget 200000]; exit codes: 0 ok, 2 bad input, 3 budget exhausted (partial outputs kept), 1 internal error. stdout: ITEMS=n EDGES=m STATES=k FRINGE0=f TOKENS=t.

## 5. Data flow
INPUT -> blocks -> KG -> items(v0.1) -> edges -> states+fringe(v1) -> report. Budgets checked before each LLM call; overflow degrades stage output size, never correctness.

## 6. Key algorithms
- Atomicity gate: three boolean LLM-oracle checks per item (atomic? assessable? meaningful?) with rule pre-filters (length bounds, verb presence); failures routed to split prompt once, then drop-plus-log.
- DAG enforcement: iterative DFS; remove argmin-confidence edge per cycle; deterministic tie-break by id order.
- State enumeration: ideals of the surmise poset via recursive frontier expansion; cap 50000 with tag-cluster partitioning fallback; fringe(S) = items whose prereqs subset-of S minus S.

## 7. Test plan
Unit per module with MockLLM cassettes; golden pipeline test on sample_chapter.md (>=15 items, >=10 edges, fringe nonempty); DAG property test (random graphs); determinism test (two runs byte-identical modulo timestamps); budget test (tiny budget still exits 0 with fewer items); no-network test (socket blocked, MockLLM only).
