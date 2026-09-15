"""Tests for gramophone_m2.story_model."""

import json

import pytest

from gramophone_m2 import story_model


def _beat(bid, to=None, checks=()):
    return {
        "id": bid,
        "title": bid,
        "text": bid,
        "choices": [{"label": "go", "to": to}] if to else [],
        "requires": [],
        "teaches": [],
        "checks": list(checks),
        "provenance": {"item_id": "i", "chunk_id": "c"},
    }


def _check(cid):
    return {
        "id": cid,
        "kind": "choice",
        "prompt": "p",
        "payload": {},
        "item_id": "i",
        "max_score": 1,
    }


def test_valid_chain_passes():
    data = {"beats": [_beat("b1", "b2", ["c1"]), _beat("b2")], "checks": [_check("c1")]}
    assert story_model.validate(data) == []


def test_dangling_choice_target_reported():
    data = {"beats": [_beat("b1", "ghost")], "checks": []}
    issues = story_model.validate(data)
    assert any("dangling" in i and "ghost" in i for i in issues)


def test_unknown_check_ref_reported():
    data = {"beats": [_beat("b1", checks=["ghost"])], "checks": []}
    issues = story_model.validate(data)
    assert any("unknown check" in i for i in issues)


def test_duplicate_ids_reported():
    data = {
        "beats": [_beat("b1"), _beat("b1")],
        "checks": [_check("c1"), _check("c1")],
    }
    issues = story_model.validate(data)
    assert sum("duplicate" in i for i in issues) == 2


def test_unreachable_beat_reported_not_dropped():
    data = {"beats": [_beat("b1"), _beat("b2"), _beat("lone")], "checks": []}
    # b1, b2, lone are all entries (nothing targets them) -> all reachable.
    assert story_model.validate(data) == []
    data = {"beats": [_beat("b1", "b2"), _beat("b2", "b1")], "checks": []}
    issues = story_model.validate(data)
    assert any("no entry beat" in i for i in issues)


def test_unknown_check_kind_reported():
    bad = _check("c1")
    bad["kind"] = "essay"
    issues = story_model.validate({"beats": [_beat("b1", checks=["c1"])], "checks": [bad]})
    assert any("unknown kind" in i and "essay" in i for i in issues)


def test_missing_keys_reported():
    issues = story_model.validate({"beats": [{"id": "b1"}], "checks": [{}]})
    assert any("missing key" in i for i in issues)


def test_load_save_roundtrip(tmp_path):
    data = {"beats": [_beat("b1")], "checks": [], "metadata": {"q": 1}}
    path = str(tmp_path / "beats.json")
    story_model.save_beats(data, path)
    assert story_model.load_beats(path) == data


def test_load_bad_shape(tmp_path):
    path = str(tmp_path / "bad.json")
    with open(path, "w") as f:
        json.dump({"nope": []}, f)
    with pytest.raises(ValueError):
        story_model.load_beats(path)
