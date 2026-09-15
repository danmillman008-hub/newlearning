"""Tests for gramophone_m2.author."""

import json

from gramophone_m1.llm_client import MockLLM

from gramophone_m2 import author


def _item(iid, tags=("t",), dok=1):
    return {
        "id": iid,
        "label": iid.title(),
        "description": f"About {iid}.",
        "dok": dok,
        "tags": list(tags),
        "assessment_criteria": f"Learner can explain {iid}.",
        "provenance": {"chunk_id": f"chunk-{iid}", "page": 0, "span": [0, 1]},
    }


def _v1():
    return {
        "metadata": {"chapter": "tiny"},
        "items": [_item("alpha", ("a",)), _item("beta", ("a",)), _item("gamma", ("b",))],
        "surmise": [["alpha", "beta"]],
    }


def _story_cassette():
    draft_a = {
        "beats": [
            {
                "id": "a1",
                "title": "A one",
                "text": "First.",
                "choices": [{"label": "go", "to": "a2"}],
                "requires": [],
                "teaches": ["alpha"],
                "checks": ["a1c"],
                "provenance": {"item_id": "alpha", "chunk_id": "WRONG"},
            },
            {
                "id": "a2",
                "title": "A two",
                "text": "Second.",
                "choices": [{"label": "go", "to": "ghost"}],
                "requires": ["alpha"],
                "teaches": ["beta"],
                "checks": ["ghost-check"],
                "provenance": {"item_id": "beta", "chunk_id": "c"},
            },
            {
                "id": "a-doomed",
                "title": "?",
                "text": "?",
                "choices": [],
                "requires": [],
                "teaches": ["nope"],
                "checks": [],
                "provenance": {"item_id": "nope", "chunk_id": "c"},
            },
        ],
        "checks": [
            {
                "id": "a1c",
                "kind": "choice",
                "prompt": "Q?",
                "payload": {"options": ["y"], "answer": "y"},
                "item_id": "alpha",
                "max_score": 1,
            },
            {
                "id": "a-ghost",
                "kind": "choice",
                "prompt": "Q?",
                "payload": {},
                "item_id": "nope",
                "max_score": 1,
            },
        ],
    }
    draft_b = {
        "beats": [
            {
                "id": "b1",
                "title": "B one",
                "text": "Only.",
                "choices": [],
                "requires": [],
                "teaches": ["gamma"],
                "checks": [],
                "provenance": {"item_id": "gamma", "chunk_id": "c"},
            }
        ],
        "checks": [],
    }
    return {"STORY": [{"text": json.dumps(draft_a), "tokens": 100},
                      {"text": json.dumps(draft_b), "tokens": 50}]}


def test_story_path_grounds_and_prunes():
    data, info = author.author_beats(_v1(), MockLLM(_story_cassette()))
    assert info["tokens"] == 150
    assert info["clusters_story"] == 2
    assert info["stopped_on_budget"] is False
    # a-doomed dropped (unknown item); ghost choice + ghost check-ref pruned
    assert [b["id"] for b in data["beats"]] == ["a1", "a2", "b1"]
    assert [c["id"] for c in data["checks"]] == ["a1c"]
    assert info["pruned"]["beats_unknown_item"] == 1
    assert info["pruned"]["checks_unknown_item"] == 1
    assert info["pruned"]["dangling_choices"] == 1
    assert info["pruned"]["unknown_check_refs"] == 1
    # provenance comes from v1 truth, never from the draft
    assert data["beats"][0]["provenance"] == {
        "item_id": "alpha",
        "chunk_id": "chunk-alpha",
    }


def test_fallback_path_full_chain():
    data, info = author.author_beats(_v1(), llm=None)
    assert info["clusters_fallback"] == 2
    assert info["tokens"] == 0
    assert [b["id"] for b in data["beats"]] == ["alpha-beat", "beta-beat", "gamma-beat"]
    assert len(data["checks"]) == 3
    # topo order: alpha before beta; chain linked within cluster a
    assert data["beats"][0]["choices"][0]["to"] == "beta-beat"
    assert data["beats"][1]["choices"] == []
    for beat in data["beats"]:
        assert beat["provenance"]["chunk_id"].startswith("chunk-")


def test_budget_exhaustion_stops_with_fewer_beats():
    full, _ = author.author_beats(_v1(), MockLLM(_story_cassette()))
    tiny = MockLLM(_story_cassette())
    data, info = author.author_beats(_v1(), tiny, budget=10)
    assert info["stopped_on_budget"] is True
    assert len(data["beats"]) < len(full["beats"])
    assert info["tokens"] == 0  # nothing spent


def test_missing_story_role_falls_back():
    data, info = author.author_beats(_v1(), MockLLM({"OTHER": []}))
    assert info["clusters_fallback"] == 2
    assert len(data["beats"]) == 3


def test_bad_draft_falls_back_for_cluster():
    cassette = {"STORY": [{"text": "not json {{{", "tokens": 5}]}
    data, info = author.author_beats(_v1(), MockLLM(cassette))
    assert info["clusters_fallback"] == 2
    assert len(data["beats"]) == 3


def test_empty_v1_rejected():
    import pytest

    with pytest.raises(ValueError):
        author.author_beats({"items": []}, llm=None)


def test_unknown_kind_check_pruned():
    draft = {
        "beats": [
            {
                "id": "a1",
                "title": "A",
                "text": "t",
                "choices": [],
                "requires": [],
                "teaches": ["alpha"],
                "checks": ["e1"],
                "provenance": {"item_id": "alpha", "chunk_id": "c"},
            }
        ],
        "checks": [
            {
                "id": "e1",
                "kind": "essay",
                "prompt": "Write!",
                "payload": {},
                "item_id": "alpha",
                "max_score": 5,
            }
        ],
    }
    cassette = {"STORY": [{"text": json.dumps(draft), "tokens": 10}]}
    data, info = author.author_beats(_v1(), MockLLM(cassette))
    assert info["pruned"]["unknown_kind"] == 2  # essay draft cycles to both clusters
    assert all(c["kind"] in ("choice", "ordering", "numeric") for c in data["checks"])


def test_deterministic():
    first, _ = author.author_beats(_v1(), MockLLM(_story_cassette()))
    second, _ = author.author_beats(_v1(), MockLLM(_story_cassette()))
    assert first == second
