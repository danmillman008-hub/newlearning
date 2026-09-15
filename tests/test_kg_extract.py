"""Unit tests: kg_extract LLM path, regex fallback, coercion, determinism."""

import json
from pathlib import Path

from gramophone_m1.kg_extract import extract_kg, slugify
from gramophone_m1.llm_client import MockLLM
from gramophone_m1.pdf_input import read_blocks

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "fixtures" / "sample_chapter.md"

BLOCKS = [
    {"chunk_id": "c001", "page": 0, "span": [0, 20], "text": "The Mean summarizes data."},
    {"chunk_id": "c002", "page": 0, "span": [22, 45], "text": "Variance measures spread."},
]


def test_slugify_is_kebab_case():
    assert slugify("Standard Deviation") == "standard-deviation"
    assert slugify("P-Value!") == "p-value"


def test_llm_path_parses_entities_and_relations():
    text = json.dumps(
        {
            "entities": [
                {"label": "Mean", "type": "measure", "chunk_ids": ["c001"]},
                {"label": "Mean", "type": "measure", "chunk_ids": ["c002"]},
                {"label": "Variance", "type": "measure", "chunk_ids": ["c002"]},
            ],
            "relations": [
                {"src": "Mean", "rel": "precedes", "dst": "Variance", "chunk_ids": ["c001"]},
            ],
        }
    )
    llm = MockLLM({"EXTRACT": [{"text": text, "tokens": 10}]})
    kg = extract_kg(BLOCKS, llm=llm)
    assert [e["id"] for e in kg["entities"]] == ["mean", "mean-2", "variance"]
    # Duplicate labels dedupe with -2 suffix; endpoints resolve first-wins.
    assert kg["relations"] == [
        {"src": "mean", "rel": "precedes", "dst": "variance", "chunk_ids": ["c001"]}
    ]
    assert llm.total_tokens == 10


def test_llm_path_coerces_unknown_chunks_and_endpoints():
    text = json.dumps(
        {
            "entities": [
                {"label": "Ghost", "type": "concept", "chunk_ids": ["c999"]},
                {"label": "", "type": "concept", "chunk_ids": []},
            ],
            "relations": [
                {"src": "Ghost", "rel": "haunts", "dst": "Nobody", "chunk_ids": []},
                {"src": "Ghost", "rel": "loops", "dst": "Ghost", "chunk_ids": []},
            ],
        }
    )
    llm = MockLLM({"EXTRACT": [{"text": text, "tokens": 3}]})
    kg = extract_kg(BLOCKS, llm=llm)
    assert kg["entities"] == [
        {"id": "ghost", "label": "Ghost", "type": "concept", "chunk_ids": ["c001"]}
    ]
    assert kg["relations"] == []


def test_invalid_llm_json_falls_back_to_regex():
    llm = MockLLM({"EXTRACT": [{"text": "not json {{{", "tokens": 5}]})
    assert extract_kg(BLOCKS, llm=llm) == extract_kg(BLOCKS, llm=None)


def test_fallback_is_deterministic_and_sorted():
    blocks = read_blocks(str(FIXTURE))
    first = extract_kg(blocks, llm=None)
    second = extract_kg(blocks, llm=None)
    assert first == second
    labels = [e["label"] for e in first["entities"]]
    assert labels == sorted(labels, key=str.lower)
    assert first["entities"]


def test_fallback_provenance_references_known_chunks_only():
    blocks = read_blocks(str(FIXTURE))
    known = {b["chunk_id"] for b in blocks}
    kg = extract_kg(blocks, llm=None)
    for ent in kg["entities"]:
        assert ent["chunk_ids"] and set(ent["chunk_ids"]) <= known
    for rel in kg["relations"]:
        assert rel["chunk_ids"] and set(rel["chunk_ids"]) <= known
        assert {rel["src"], rel["dst"]} <= {e["id"] for e in kg["entities"]}


def test_empty_blocks_yield_empty_kg():
    assert extract_kg([], llm=None) == {"entities": [], "relations": []}
    llm = MockLLM({"EXTRACT": [{"text": "{}", "tokens": 1}]})
    assert extract_kg([], llm=llm) == {"entities": [], "relations": []}
