"""Tests for gramophone_m5.bookquest (+ quest/unified CLIs)."""

import io
import json
import socket
import sys
from pathlib import Path

import pytest

from gramophone_m5 import bookquest, cli

ROOT = Path(__file__).resolve().parent.parent
CHA = str(ROOT / "fixtures" / "chapter_a.json")
CHB = str(ROOT / "fixtures" / "chapter_b.json")
RESPONSES = str(ROOT / "fixtures" / "m5_responses.txt")
NAMES = ["ch1", "ch2"]

ORDER = ["ch2:s2-beat", "ch1:alpha-beat", "ch1:beta-beat", "ch1:s1-beat",
         "ch2:gamma-beat"]


def _book_canon(path):
    """Book graph minus the inherited M3 wall clock (M1 precedent: outputs
    are byte-identical modulo timestamps)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data.get("metadata", {}).pop("generated_at", None)
    return data


def test_e2e_golden(tmp_path):
    out = str(tmp_path)
    session = bookquest.run_book_quest([CHA, CHB], out, responses_path=RESPONSES,
                                       names=NAMES)
    with open(tmp_path / "book-graph.json", encoding="utf-8") as f:
        book = json.load(f)
    assert len(book["items"]) == 5
    assert len(book["surmise"]) == 3
    assert len(book["states"]) == 12
    with open(tmp_path / "beats.json", encoding="utf-8") as f:
        beats = json.load(f)
    assert len(beats["beats"]) == 5
    assert len(beats["checks"]) == 5
    # Policy order: s2 first (fringe tie broken by the flow/difficulty term),
    # then the ch1 chain in topo order, gamma last.
    assert session["beats_visited"] == ORDER
    assert (session["attempts"], session["passed"], session["xp"]) == (6, 5, 50)
    assert session["level"] == 1
    assert session["streak_max"] == 5
    assert session["flow_in_band_ratio"] == pytest.approx(0.5)
    assert session["xapi_statements"] == 17
    assert session["skipped"] == []
    assert session["retries_used"] == 1
    assert session["completion"] == {"reason": "quest_complete", "picks": 5,
                                     "visited": 5}
    rows = [(t["beat"], t["success"]) for t in session["transcript"]]
    assert rows == [(ORDER[0], False), (ORDER[0], True), (ORDER[1], True),
                    (ORDER[2], True), (ORDER[3], True), (ORDER[4], True)]
    assert session["mastery"]["ch2:s2"] == pytest.approx(0.3628, abs=1e-3)
    report = (tmp_path / "M5-REPORT.md").read_text(encoding="utf-8")
    assert "BOOK CHAPTERS=2 ITEMS=5 EDGES=3 STATES=12" in report
    assert "BEATS=5 CHECKS=5 CLUSTERS=2 VIA_FALLBACK=2 TOKENS=0" in report
    assert "COMPLETION=quest_complete PICKS=5" in report


def test_default_names_from_stems(tmp_path):
    session = bookquest.run_book_quest([CHA, CHB], str(tmp_path),
                                       responses_path=RESPONSES)
    assert session["beats_visited"][0] == "chapter_b:s2-beat"
    assert session["completion"]["reason"] == "quest_complete"


def test_cli_quest_and_unified(tmp_path, capsys, monkeypatch):
    out = str(tmp_path / "m5")
    base = [CHA, CHB, "--names", "ch1", "ch2", "--responses", RESPONSES]
    assert cli.quest_main(base + ["--out", out]) == 0
    printed = capsys.readouterr().out
    assert "BOOK CHAPTERS=2 ITEMS=5 EDGES=3 BEATS=5 CHECKS=5" in printed
    assert ("SESSION VISITED=5 ATTEMPTS=6 PASSED=5 XP=50 LEVEL=1 "
            "STREAK_MAX=5 SKIPPED=0 RETRIES=1 "
            "COMPLETION=quest_complete") in printed
    out2 = str(tmp_path / "uni")
    assert cli.main(["quest"] + base + ["--out", out2]) == 0
    assert _book_canon(tmp_path / "m5" / "book-graph.json") == _book_canon(
        tmp_path / "uni" / "book-graph.json")
    for name in ("beats.json", "session.json", "xapi.jsonl"):
        assert (tmp_path / "m5" / name).read_bytes() == (
            tmp_path / "uni" / name).read_bytes()
    with pytest.raises(SystemExit) as exc:
        cli.main(["m1", "--help"])
    assert exc.value.code == 0
    assert cli.main([]) == 2
    assert cli.main(["nope"]) == 2
    assert "usage: gramophone" in capsys.readouterr().err
    fake = io.StringIO("Alpha\nShared\nAlpha\nBeta\nShared\nGamma\n")
    monkeypatch.setattr(sys, "stdin", fake)
    out3 = str(tmp_path / "stdin")
    assert cli.quest_main([CHA, CHB, "--names", "ch1", "ch2",
                           "--out", out3]) == 0
    assert "COMPLETION=quest_complete" in capsys.readouterr().out


def test_save_resume_e2e_equals_whole(tmp_path):
    lines = Path(RESPONSES).read_text(encoding="utf-8").splitlines()
    out = tmp_path / "run"
    state_path = str(tmp_path / "state.json")
    bookquest.run_book_quest([CHA, CHB], str(out), response_lines=lines[:2],
                             names=NAMES, save=state_path)
    resumed = bookquest.run_book_quest([CHA, CHB], str(out),
                                       response_lines=lines[2:], names=NAMES,
                                       resume=state_path)
    whole = bookquest.run_book_quest([CHA, CHB], str(tmp_path / "whole"),
                                     responses_path=RESPONSES, names=NAMES)
    assert resumed == whole
    assert (out / "xapi.jsonl").read_bytes() == (
        tmp_path / "whole" / "xapi.jsonl").read_bytes()


def test_bad_inputs_rejected(tmp_path, capsys, monkeypatch):
    out = str(tmp_path)
    with pytest.raises(ValueError):
        bookquest.run_book_quest([], out, response_lines=[])
    with pytest.raises(ValueError):
        bookquest.run_book_quest(CHA, out, response_lines=[])
    with pytest.raises(ValueError, match="names length"):
        bookquest.run_book_quest([CHA, CHB], out, response_lines=[],
                                 names=["only"])
    with pytest.raises(ValueError):
        bookquest.run_book_quest([CHA, CHB], out, response_lines=[],
                                 names=["dup", "dup"])
    with pytest.raises(ValueError):
        bookquest.run_book_quest([CHA, CHB], out, response_lines=[],
                                 names="ch1")
    with pytest.raises(ValueError, match="not found"):
        bookquest.run_book_quest([str(tmp_path / "nope.json")], out,
                                 response_lines=[])
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not JSON"):
        bookquest.run_book_quest([str(bad)], out, response_lines=[])
    bad.write_text('{"items": []}', encoding="utf-8")
    with pytest.raises(ValueError, match="items\\[\\]/surmise"):
        bookquest.run_book_quest([str(bad)], out, response_lines=[])
    with pytest.raises(ValueError, match="exclusive"):
        bookquest.run_book_quest([CHA], out, responses_path=RESPONSES,
                                 response_lines=["x"])
    with pytest.raises(ValueError, match="no responses"):
        bookquest.run_book_quest([CHA], out)
    with pytest.raises(ValueError, match="must be a list"):
        bookquest.run_book_quest([CHA], out, response_lines="Alpha")
    with pytest.raises(SystemExit) as exc:
        cli.quest_main(["--out", out])
    assert exc.value.code == 2
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert cli.quest_main([CHA, "--out", out]) == 0  # empty stdin: exhausted
    assert "COMPLETION=responses_exhausted" in capsys.readouterr().out


def test_deterministic(tmp_path):
    first = bookquest.run_book_quest([CHA, CHB], str(tmp_path / "a"),
                                     responses_path=RESPONSES, names=NAMES)
    second = bookquest.run_book_quest([CHA, CHB], str(tmp_path / "b"),
                                      responses_path=RESPONSES, names=NAMES)
    assert first == second
    assert _book_canon(tmp_path / "a" / "book-graph.json") == _book_canon(
        tmp_path / "b" / "book-graph.json")
    for name in ("beats.json", "session.json", "xapi.jsonl"):
        assert (tmp_path / "a" / name).read_bytes() == (
            tmp_path / "b" / name).read_bytes()


def test_no_network(tmp_path, monkeypatch):
    real_socket = socket.socket

    def blocked(*a, **k):
        raise RuntimeError("network disabled in test")

    monkeypatch.setattr(socket, "socket", blocked)
    try:
        session = bookquest.run_book_quest([CHA, CHB], str(tmp_path),
                                           responses_path=RESPONSES, names=NAMES)
        assert session["completion"]["reason"] == "quest_complete"
    finally:
        monkeypatch.setattr(socket, "socket", real_socket)
