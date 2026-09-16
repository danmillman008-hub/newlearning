"""Tests for gramophone_m6.fullchain (+ gramophone-m6 CLI)."""

import io
import json
import socket
import sys
from pathlib import Path

import pytest

from gramophone_m6 import cli, fullchain

ROOT = Path(__file__).resolve().parent.parent
CHAPTER = str(ROOT / "fixtures" / "sample_chapter.md")
RESPONSES = str(ROOT / "fixtures" / "m6_responses.txt")

ORDER = ["chap:correlation-beat", "chap:outlier-beat",
         "chap:central-tendency-beat", "chap:descriptive-statistics-beat",
         "chap:dispersion-beat", "chap:null-hypothesis-beat",
         "chap:population-beat", "chap:probability-beat",
         "chap:hypothesis-testing-beat", "chap:mean-beat", "chap:p-value-beat",
         "chap:regression-beat", "chap:variance-beat",
         "chap:confidence-interval-beat", "chap:inferential-statistics-beat",
         "chap:median-beat", "chap:mode-beat", "chap:sample-beat",
         "chap:sampling-beat", "chap:sampling-bias-beat",
         "chap:standard-deviation-beat", "chap:normal-distribution-beat"]


def _canon_graph(path):
    """Parsed v1 minus the inherited wall clock (M1 precedent)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data.get("metadata", {}).pop("generated_at", None)
    return data


def test_full_golden(tmp_path):
    result = fullchain.run_full_chain([CHAPTER], str(tmp_path),
                                      responses_path=RESPONSES, names=["chap"])
    m1 = result["m1"][0]
    assert (m1["items"], m1["edges"], m1["states"]) == (22, 17, 36000)
    assert (m1["fringe0"], m1["tokens"]) == (8, 5100)
    assert (tmp_path / "m1_chap" / "knowledge-graph.json").exists()
    with open(tmp_path / "book-graph.json", encoding="utf-8") as f:
        book = json.load(f)
    assert (len(book["items"]), len(book["surmise"])) == (22, 17)
    with open(tmp_path / "beats.json", encoding="utf-8") as f:
        beats = json.load(f)
    assert (len(beats["beats"]), len(beats["checks"])) == (22, 22)
    session = result["session"]
    assert session["beats_visited"] == ORDER
    assert (session["attempts"], session["passed"], session["xp"]) == (23, 22, 220)
    assert session["level"] == 3
    assert session["streak_max"] == 20
    # Near-perfect run reads as "too easy" (out of band) by design.
    assert session["flow_in_band_ratio"] == pytest.approx(0.1304)
    assert session["xapi_statements"] == 68
    assert session["skipped"] == []
    assert session["retries_used"] == 1
    assert session["completion"] == {"reason": "quest_complete", "picks": 22,
                                     "visited": 22}
    rows = [(t["beat"], t["success"]) for t in session["transcript"]]
    assert len(rows) == 23
    assert rows[2] == ("chap:central-tendency-beat", False)
    assert rows[3] == ("chap:central-tendency-beat", True)
    assert session["mastery"]["chap:central-tendency"] == pytest.approx(
        0.3628, abs=1e-3)
    with open(tmp_path / "xapi.jsonl", encoding="utf-8") as f:
        assert len(f.readlines()) == 68
    report = (tmp_path / "M6-REPORT.md").read_text(encoding="utf-8")
    assert "ITEMS=22 EDGES=17 STATES=36000" in report
    assert "COMPLETION=quest_complete PICKS=22" in report
    assert (tmp_path / "M5-REPORT.md").exists()


def test_cli_golden_and_exits(tmp_path, capsys, monkeypatch):
    out = str(tmp_path / "cli")
    args = [CHAPTER, "--names", "chap", "--responses", RESPONSES, "--out", out]
    assert cli.main(args) == 0
    printed = capsys.readouterr().out
    assert "ITEMS=22 EDGES=17 STATES=36000 FRINGE0=8 TOKENS=5100" in printed
    assert "BOOK CHAPTERS=1 ITEMS=22 EDGES=17 BEATS=22 CHECKS=22" in printed
    assert ("SESSION VISITED=22 ATTEMPTS=23 PASSED=22 XP=220 LEVEL=3 "
            "STREAK_MAX=20 SKIPPED=0 RETRIES=1 "
            "COMPLETION=quest_complete") in printed
    fake = io.StringIO(Path(RESPONSES).read_text(encoding="utf-8"))
    monkeypatch.setattr(sys, "stdin", fake)
    assert cli.main([CHAPTER, "--names", "chap", "--out",
                     str(tmp_path / "stdin")]) == 0
    assert "COMPLETION=quest_complete" in capsys.readouterr().out
    with pytest.raises(SystemExit) as exc:
        cli.main(["--out", out])
    assert exc.value.code == 2
    assert cli.main([str(tmp_path / "nope.md"), "--out", out,
                     "--responses", RESPONSES]) == 2
    assert cli.main([CHAPTER, "--out", out, "--names", "a", "b",
                     "--responses", RESPONSES]) == 2


def test_save_resume_fullchain_equals_whole(tmp_path):
    lines = Path(RESPONSES).read_text(encoding="utf-8").splitlines()
    out = tmp_path / "run"
    state_path = str(tmp_path / "state.json")
    fullchain.run_full_chain([CHAPTER], str(out), response_lines=lines[:2],
                             names=["chap"], save=state_path)
    resumed = fullchain.run_full_chain([CHAPTER], str(out),
                                       response_lines=lines[2:], names=["chap"],
                                       resume=state_path)
    whole = fullchain.run_full_chain([CHAPTER], str(tmp_path / "whole"),
                                     responses_path=RESPONSES, names=["chap"])
    assert resumed["session"] == whole["session"]
    for key in ("items", "edges", "states", "tokens"):
        assert resumed["m1"][0][key] == whole["m1"][0][key]
    assert (out / "xapi.jsonl").read_bytes() == (
        tmp_path / "whole" / "xapi.jsonl").read_bytes()


def test_bad_inputs_rejected(tmp_path, monkeypatch):
    out = str(tmp_path)
    with pytest.raises(ValueError):
        fullchain.run_full_chain([], out, response_lines=[])
    with pytest.raises(ValueError):
        fullchain.run_full_chain(CHAPTER, out, response_lines=[])
    with pytest.raises(ValueError, match="not found"):
        fullchain.run_full_chain([str(tmp_path / "nope.md")], out,
                                 response_lines=[])
    with pytest.raises(ValueError, match="names length"):
        fullchain.run_full_chain([CHAPTER], out, response_lines=[],
                                 names=["a", "b"])
    with pytest.raises(ValueError, match="names must be"):
        fullchain.run_full_chain([CHAPTER], out, response_lines=[], names="x")
    with pytest.raises(ValueError, match="exclusive"):
        fullchain.run_full_chain([CHAPTER], out, responses_path=RESPONSES,
                                 response_lines=["x"], names=["chap"])
    with pytest.raises(ValueError, match="no responses"):
        fullchain.run_full_chain([CHAPTER], out, names=["chap"])
    monkeypatch.setenv("GRAMOPHONE_CASSETTE", str(tmp_path / "nope.json"))
    with pytest.raises(ValueError, match="cassette missing"):
        fullchain.run_full_chain([CHAPTER], out, response_lines=[],
                                 names=["chap"])


def test_deterministic(tmp_path):
    first = fullchain.run_full_chain([CHAPTER], str(tmp_path / "a"),
                                     responses_path=RESPONSES, names=["chap"])
    second = fullchain.run_full_chain([CHAPTER], str(tmp_path / "b"),
                                      responses_path=RESPONSES, names=["chap"])
    assert first["session"] == second["session"]
    assert _canon_graph(tmp_path / "a" / "book-graph.json") == _canon_graph(
        tmp_path / "b" / "book-graph.json")
    assert _canon_graph(tmp_path / "a" / "m1_chap" / "knowledge-graph.json") == (
        _canon_graph(tmp_path / "b" / "m1_chap" / "knowledge-graph.json"))
    for name in ("beats.json", "session.json", "xapi.jsonl"):
        assert (tmp_path / "a" / name).read_bytes() == (
            tmp_path / "b" / name).read_bytes()


def test_no_network(tmp_path, monkeypatch):
    real_socket = socket.socket

    def blocked(*a, **k):
        raise RuntimeError("network disabled in test")

    monkeypatch.setattr(socket, "socket", blocked)
    try:
        result = fullchain.run_full_chain([CHAPTER], str(tmp_path),
                                          responses_path=RESPONSES,
                                          names=["chap"])
        assert result["session"]["completion"]["reason"] == "quest_complete"
    finally:
        monkeypatch.setattr(socket, "socket", real_socket)
