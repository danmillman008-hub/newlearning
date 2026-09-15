"""Tests for gramophone_m4.adaptive (+ quest CLI)."""

import io
import json
import socket
import sys
from pathlib import Path

import pytest

from gramophone_m2 import story_model, xapi
from gramophone_m4 import adaptive, cli, pipeline

ROOT = Path(__file__).resolve().parent.parent
BEATS = str(ROOT / "fixtures" / "sample_beats.json")
GRAPH = str(ROOT / "fixtures" / "fringe_graph.json")
RESPONSES = str(ROOT / "fixtures" / "m4_responses.txt")


def _beats():
    return story_model.load_beats(BEATS)


def _graph():
    with open(GRAPH, encoding="utf-8") as f:
        return json.load(f)


def _responses():
    with open(RESPONSES, encoding="utf-8") as f:
        return [pipeline.parse_response_line(l) for l in f if l.strip()]


def test_quest_golden(tmp_path):
    out = str(tmp_path)
    session = pipeline.run_quest_file(BEATS, GRAPH, out, responses_path=RESPONSES)
    assert session["beats_visited"] == ["q1", "q2", "q3", "q4", "q5", "q6", "q7", "q8"]
    assert (session["attempts"], session["passed"], session["xp"]) == (6, 5, 57)
    assert session["level"] == 1
    assert session["streak_max"] == 3
    assert session["flow_in_band_ratio"] == pytest.approx(0.5)
    assert session["xapi_statements"] == 20
    assert session["skipped"] == []
    assert session["retries_used"] == 1
    assert session["completion"] == {"reason": "quest_complete", "picks": 8, "visited": 8}
    assert session["mastery"]["median"] == pytest.approx(0.3628, abs=1e-3)
    rows = [(t["beat"], t["check"], t["success"]) for t in session["transcript"]]
    assert rows == [
        ("q1", "q1-check", True), ("q2", "q2-check", True),
        ("q3", "q3-check", False), ("q3", "q3-check", True),
        ("q5", "q5-check", True), ("q7", "q7-check", True),
    ]
    assert session["transcript"][2]["score"] == pytest.approx(0.6667, abs=1e-3)
    with open(tmp_path / "xapi.jsonl", encoding="utf-8") as f:
        assert len(f.readlines()) == 20
    assert (tmp_path / "session.json").exists()
    assert (tmp_path / "M4-REPORT.md").exists()


def _branched_beats():
    def beat(bid, teaches):
        return {"id": bid, "title": bid, "text": "", "choices": [],
                "requires": [], "teaches": [teaches], "checks": [bid + "-c"],
                "difficulty": 2, "provenance": {"item_id": teaches, "chunk_id": "c"}}
    return {
        "beats": [beat("aa", "y"), beat("zz", "x")],
        "checks": [{"id": "aa-c", "kind": "choice", "prompt": "p",
                    "payload": {"options": ["v"], "answer": "v"},
                    "item_id": "y", "max_score": 1},
                   {"id": "zz-c", "kind": "choice", "prompt": "p",
                    "payload": {"options": ["v"], "answer": "v"},
                    "item_id": "x", "max_score": 1}],
    }


def test_fringe_pick_beats_id_order(tmp_path):
    v1 = {"items": [{"id": "x"}, {"id": "y"}], "surmise": [["x", "y"]]}
    store = xapi.XAPIStore(str(tmp_path / "x.jsonl"))
    session, _, transcript = adaptive.run_quest(
        _branched_beats(), v1, ["v", "v"], store=store)
    assert transcript[0]["beat"] == "zz"  # teaches fringe item x, not id-first aa
    assert session["completion"]["reason"] == "quest_complete"


def test_gated_stop(tmp_path):
    beats = _branched_beats()
    beats["beats"][1]["requires"] = ["ghost-never-known"]
    v1 = {"items": [{"id": "x"}, {"id": "y"}], "surmise": []}
    store = xapi.XAPIStore(str(tmp_path / "x.jsonl"))
    session, _, _ = adaptive.run_quest(beats, v1, ["v"], store=store)
    assert session["completion"]["reason"] == "gated"
    assert session["beats_visited"] == ["aa"]


def test_responses_exhausted_and_max_steps(tmp_path):
    store = xapi.XAPIStore(str(tmp_path / "x.jsonl"))
    session, _, _ = adaptive.run_quest(_beats(), _graph(), ["Mean"], store=store)
    assert session["completion"]["reason"] == "responses_exhausted"
    assert session["beats_visited"] == ["q1"]
    store2 = xapi.XAPIStore(str(tmp_path / "y.jsonl"))
    session2, _, _ = adaptive.run_quest(
        _beats(), _graph(), _responses(), max_steps=2, store=store2)
    assert session2["completion"] == {"reason": "max_steps", "picks": 2, "visited": 2}


def test_save_resume_midquest_equals_whole(tmp_path):
    resps = _responses()
    out = tmp_path / "run"
    state_path = str(tmp_path / "state.json")
    lines = RESP_TEXT.splitlines()
    part1 = [pipeline.parse_response_line(l) for l in lines[:2]]
    pipeline.run_quest_file(BEATS, GRAPH, str(out), response_lines=lines[:2],
                            save=state_path)
    resumed = pipeline.run_quest_file(BEATS, GRAPH, str(out),
                                      response_lines=lines[2:],
                                      resume=state_path)
    whole = pipeline.run_quest_file(BEATS, GRAPH, str(tmp_path / "whole"),
                                    responses_path=RESPONSES)
    assert resumed == whole
    assert (out / "xapi.jsonl").read_bytes() == (
        tmp_path / "whole" / "xapi.jsonl").read_bytes()
    assert part1[0] == "Mean"  # response parsing sanity


RESP_TEXT = open(RESPONSES, encoding="utf-8").read()


def test_bad_inputs_rejected(tmp_path):
    store = xapi.XAPIStore(str(tmp_path / "x.jsonl"))
    with pytest.raises(ValueError):
        adaptive.run_quest(_beats(), {"items": []}, [], store=store)
    with pytest.raises(ValueError):
        adaptive.run_quest(_beats(), {"items": [{"id": "x"}],
                                      "surmise": [["x", "ghost"]]},
                           [], store=store)
    with pytest.raises(ValueError):
        adaptive.run_quest(_beats(), _graph(), [], max_steps=0, store=store)
    with pytest.raises(ValueError):
        adaptive.run_quest(_beats(), _graph(), [], max_retries=-1, store=store)
    with pytest.raises(ValueError, match="must be a list"):
        adaptive.run_quest(_beats(), _graph(), "Mean", store=store)
    session, _, _ = adaptive.run_quest(
        _beats(), _graph(), ("Mean",), store=xapi.XAPIStore(str(tmp_path / "t.jsonl")))
    assert session["beats_visited"] == ["q1"]
    with pytest.raises(ValueError):
        pipeline.run_quest_file(BEATS, GRAPH, str(tmp_path), responses_path=RESPONSES,
                                response_lines=["x"])
    with pytest.raises(ValueError):
        pipeline.run_quest_file(BEATS, GRAPH, str(tmp_path))


def test_cli_golden_and_exits(tmp_path, capsys, monkeypatch):
    out = str(tmp_path / "cli")
    args = ["play", BEATS, "--graph", GRAPH, "--responses", RESPONSES, "--out", out]
    assert cli.main(args) == 0
    line = capsys.readouterr().out
    assert "VISITED=8 ATTEMPTS=6 PASSED=5 XP=57 LEVEL=1 STREAK_MAX=3" in line
    assert "SKIPPED=0 RETRIES=1 COMPLETION=quest_complete" in line
    fake = io.StringIO("Mean\n")
    monkeypatch.setattr(sys, "stdin", fake)
    out2 = str(tmp_path / "stdin")
    assert cli.main(["play", BEATS, "--graph", GRAPH, "--out", out2]) == 0
    assert "COMPLETION=responses_exhausted" in capsys.readouterr().out
    assert cli.main(["play", str(tmp_path / "nope.json"), "--graph", GRAPH,
                     "--out", out]) == 2
    assert cli.main(["play", BEATS, "--graph", str(tmp_path / "nope.json"),
                     "--out", out, "--responses", RESPONSES]) == 2


def test_deterministic(tmp_path):
    first = pipeline.run_quest_file(BEATS, GRAPH, str(tmp_path / "a"),
                                    responses_path=RESPONSES)
    second = pipeline.run_quest_file(BEATS, GRAPH, str(tmp_path / "b"),
                                     responses_path=RESPONSES)
    assert first == second
    for name in ("session.json", "xapi.jsonl"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()


def test_no_network(tmp_path, monkeypatch):
    real_socket = socket.socket

    def blocked(*a, **k):
        raise RuntimeError("network disabled in test")

    monkeypatch.setattr(socket, "socket", blocked)
    try:
        session = pipeline.run_quest_file(BEATS, GRAPH, str(tmp_path),
                                          responses_path=RESPONSES)
        assert session["completion"]["reason"] == "quest_complete"
    finally:
        monkeypatch.setattr(socket, "socket", real_socket)
