"""Unit tests: itemize schema, atomicity gate, split-or-drop, caps."""

import json
from pathlib import Path

from gramophone_m1.itemize import (
    BLOOM_LEVELS,
    KNOWLEDGE_TYPES,
    atomicity_gate,
    items_from_kg,
    try_split,
)
from gramophone_m1.llm_client import MockLLM
from gramophone_m1.pdf_input import read_blocks

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "fixtures" / "sample_chapter.md"

BLOCKS = [
    {"chunk_id": "c001", "page": 0, "span": [0, 10], "text": "0123456789"},
    {"chunk_id": "c002", "page": 0, "span": [10, 20], "text": "0123456789"},
]

REQUIRED_KEYS = {
    "id", "label", "description", "bloom", "knowledge_type", "dok",
    "assessment_criteria", "required_competences", "tags", "provenance",
}


def _good_item(**over):
    item = {
        "id": "mean",
        "label": "Mean",
        "description": "Define the Mean and calculate it for a dataset.",
    }
    item.update(over)
    return item


def test_gate_accepts_good_item():
    ok, reason = atomicity_gate(_good_item())
    assert ok and reason == "pass"


def test_gate_rejects_short_label_and_missing_verb():
    ok, reason = atomicity_gate(_good_item(label="Qx"))
    assert not ok and "label" in reason
    ok, reason = atomicity_gate(
        _good_item(description="Qzx wobble plugh xyzzy foobar.")
    )
    assert not ok and "verb" in reason


def test_gate_honors_oracle_flags():
    item = _good_item(atomicity={"atomic": True, "assessable": False, "meaningful": True})
    ok, reason = atomicity_gate(item)
    assert not ok and "assessable" in reason


def test_try_split_needs_two_sentences():
    kids = try_split(_good_item(description="First claim here. Second claim here."))
    assert [k["id"] for k in kids] == ["mean-a", "mean-b"]
    assert try_split(_good_item(description="Only one sentence here.")) == []


def test_rule_path_builds_valid_schema_from_entities():
    kg = {
        "entities": [
            {"id": "mean", "label": "Mean", "type": "measure", "chunk_ids": ["c001"]},
            {"id": "qx", "label": "Qx", "type": "concept", "chunk_ids": ["c002"]},
        ],
        "relations": [],
    }
    pack = items_from_kg(kg, llm=None, blocks=BLOCKS)
    assert [i["id"] for i in pack["items"]] == ["mean"]
    item = pack["items"][0]
    assert REQUIRED_KEYS <= set(item)
    assert item["bloom"] in BLOOM_LEVELS
    assert item["knowledge_type"] in KNOWLEDGE_TYPES
    assert item["dok"] in (1, 2, 3, 4)
    assert item["provenance"] == {"chunk_id": "c001", "page": 0, "span": [0, 10]}
    decisions = {e["id"]: e["decision"] for e in pack["log"]}
    assert decisions == {"mean": "accepted", "qx": "dropped"}


def test_llm_path_coerces_enums_and_splits_oracle_failures():
    payload = {
        "items": [
            {
                "label": "Median",
                "description": "Define the Median. Explain its resistance to extremes.",
                "bloom": "memorize",
                "knowledge_type": "vibes",
                "dok": 99,
                "assessment_criteria": "Learner defines Median.",
                "required_competences": [],
                "tags": ["measure"],
                "provenance": {"chunk_id": "c002"},
                "atomicity": {"atomic": False, "assessable": True, "meaningful": True},
            }
        ],
        "competences": [{"label": "Summarize data", "type": "cognitive"}],
    }
    llm = MockLLM({"ANALYZE": [{"text": json.dumps(payload), "tokens": 7}]})
    pack = items_from_kg({"entities": [], "relations": []}, llm=llm, blocks=BLOCKS)
    assert [i["id"] for i in pack["items"]] == ["median-a", "median-b"]
    assert all(i["bloom"] == "understand" for i in pack["items"])
    assert all(i["knowledge_type"] == "conceptual" for i in pack["items"])
    assert all(i["dok"] == 1 for i in pack["items"])
    assert pack["competences"] == [
        {"id": "summarize-data", "label": "Summarize data", "type": "cognitive"}
    ]
    assert pack["log"][0]["decision"] == "split"


def test_invalid_llm_json_falls_back_to_rules():
    kg = {
        "entities": [
            {"id": "mean", "label": "Mean", "type": "measure", "chunk_ids": ["c001"]}
        ],
        "relations": [],
    }
    llm = MockLLM({"ANALYZE": [{"text": "garbage{{{", "tokens": 2}]})
    pack = items_from_kg(kg, llm=llm, blocks=BLOCKS)
    assert [i["id"] for i in pack["items"]] == ["mean"]


def test_max_items_caps_with_deterministic_order_and_log():
    kg = {
        "entities": [
            {
                "id": f"ent-{i:02d}",
                "label": f"Concept number {i}",
                "type": "concept",
                "chunk_ids": ["c001"],
            }
            for i in range(5)
        ],
        "relations": [],
    }
    pack = items_from_kg(kg, llm=None, blocks=BLOCKS, max_items=2)
    assert [i["id"] for i in pack["items"]] == ["ent-00", "ent-01"]
    assert sum(1 for e in pack["log"] if e["decision"] == "dropped") == 3


def test_fixture_rule_path_end_to_end_schema():
    from gramophone_m1.kg_extract import extract_kg

    blocks = read_blocks(str(FIXTURE))
    pack = items_from_kg(extract_kg(blocks, llm=None), llm=None, blocks=blocks)
    assert pack["items"]
    for item in pack["items"]:
        assert REQUIRED_KEYS <= set(item)
        assert atomicity_gate(item)[0]
