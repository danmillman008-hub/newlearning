"""Tests for gramophone_m3.live (+ play CLI)."""

import io
import json
import socket
import sys
from pathlib import Path

import pytest

from gramophone_m2 import pipeline as m2_pipeline
from gramophone_m2 import story_model
from gramophone_m3 import cli, live, pipeline

ROOT = Path(__file__).resolve().parent.parent
BEATS = str(ROOT / "fixtures" / "sample_beats.json")
SCRIPT = str(ROOT / "fixtures" / "sample_script.json")


def test_scripted_golden_equals_m2(tmp_path):
    m2_session = m2_pipeline.run_learn(BEATS, SCRIPT, str(tmp_path / "m2"))
    session = pipeline.run_play(BEATS, str(tmp_path), script=SCRIPT)
    for key in ("beats_visited", "attempts", "passed", "xp", "level",
                "streak_max", "mastery", "flow_in_band_ratio", "xapi_statements"):
        assert session[key] == m2_session[key], key
    assert session["beats_visited"] == ["q1", "q2", "q5", "q3", "q7"]
    assert (session["attempts"], session["passed"], session["xp"]) == (7, 6, 67)
    assert session["skipped"] == []
    assert session["retries_used"] == 1
    assert (tmp_path / "session.json").exists()
    assert (tmp_path / "xapi.jsonl").exists()


def _beats():
    return story_model.load_beats(BEATS)


def _att(beat, check, response):
    return {"beat_id": beat, "check_id": check, "response": response}


def test_retry_cap_skips_extras(tmp_path):
    from gramophone_m2 import xapi

    store = xapi.XAPIStore(str(tmp_path / "x.jsonl"))
    attempts = [_att("q1", "q1-check", "Nope"), _att("q1", "q1-check", "Nope"),
                _att("q1", "q1-check", "Mean")]
    session, _ = live.play_session(_beats(), attempts, store=store)
    assert session["attempts"] == 2
    assert session["passed"] == 0
    assert session["skipped"] == [2]
    assert session["retries_used"] == 1
    assert session["xapi_statements"] == 5  # 1 exp + 2*(att+fail)


def test_nonconsecutive_repeat_not_a_retry(tmp_path):
    from gramophone_m2 import xapi

    store = xapi.XAPIStore(str(tmp_path / "x.jsonl"))
    attempts = [_att("q1", "q1-check", "Mean"), _att("q2", "q2-check", 5.0),
                _att("q1", "q1-check", "Mean")]
    session, _ = live.play_session(_beats(), attempts, store=store)
    assert session["skipped"] == []
    assert session["retries_used"] == 0
    assert session["passed"] == 3


def test_input_lines_json_responses(tmp_path):
    lines = ["q1|q1-check|Mean", "q2|q2-check|5.0",
             'q3|q3-check|["sort", "count", "pick-middle"]']
    session = pipeline.run_play(BEATS, str(tmp_path), input_lines=lines)
    assert (session["attempts"], session["passed"]) == (3, 3)
    with pytest.raises(ValueError):
        live.parse_attempt_line("oops-no-pipes")
    with pytest.raises(ValueError):
        live.parse_attempt_line("a|b")


def test_bad_attempts_rejected(tmp_path):
    from gramophone_m2 import xapi

    store = xapi.XAPIStore(str(tmp_path / "x.jsonl"))
    with pytest.raises(ValueError):
        live.play_session(_beats(), [_att("nope", "q1-check", "x")], store=store)
    with pytest.raises(ValueError):
        live.play_session(_beats(), ["not-a-dict"], store=store)
    with pytest.raises(ValueError):
        pipeline.run_play(BEATS, str(tmp_path), script=SCRIPT, input_lines=["x"])


def test_save_resume_roundtrip_and_continues(tmp_path):
    with open(SCRIPT, encoding="utf-8") as f:
        full = json.load(f)["attempts"]
    first4 = tmp_path / "s4.json"
    last3 = tmp_path / "s3.json"
    first4.write_text(json.dumps({"actor": "learner-1", "attempts": full[:4]}))
    last3.write_text(json.dumps({"actor": "learner-1", "attempts": full[4:]}))
    out = tmp_path / "run"
    state_path = tmp_path / "state.json"
    pipeline.run_play(BEATS, str(out), script=str(first4), save=str(state_path))
    state_path2 = tmp_path / "state2.json"
    live.save_state(live.load_state(str(state_path)), str(state_path2))
    assert state_path.read_bytes() == state_path2.read_bytes()
    resumed = pipeline.run_play(BEATS, str(out), script=str(last3),
                                resume=str(state_path))
    whole = pipeline.run_play(BEATS, str(tmp_path / "whole"), script=SCRIPT)
    assert resumed == whole
    assert (out / "xapi.jsonl").read_bytes() == (tmp_path / "whole" / "xapi.jsonl").read_bytes()


def test_cli_play_golden_and_stdin(tmp_path, capsys, monkeypatch):
    out = str(tmp_path / "cli")
    assert cli.main(["play", BEATS, "--script", SCRIPT, "--out", out]) == 0
    line = capsys.readouterr().out
    assert "VISITED=5 ATTEMPTS=7 PASSED=6 XP=67 LEVEL=1 STREAK_MAX=3" in line
    assert "SKIPPED=0 RETRIES=1" in line
    fake = io.StringIO("q1|q1-check|Mean\n")
    monkeypatch.setattr(sys, "stdin", fake)
    out2 = str(tmp_path / "stdin")
    assert cli.main(["play", BEATS, "--out", out2]) == 0
    assert "VISITED=1 ATTEMPTS=1 PASSED=1" in capsys.readouterr().out
    assert cli.main(["play", str(tmp_path / "nope.json"), "--out", out]) == 2


def test_no_network(tmp_path, monkeypatch):
    real_socket = socket.socket

    def blocked(*a, **k):
        raise RuntimeError("network disabled in test")

    monkeypatch.setattr(socket, "socket", blocked)
    try:
        pipeline.run_merge(
            [str(ROOT / "fixtures" / "chapter_a.json"),
             str(ROOT / "fixtures" / "chapter_b.json")], str(tmp_path), ["a", "b"])
        session = pipeline.run_play(BEATS, str(tmp_path), script=SCRIPT)
        assert session["attempts"] == 7
    finally:
        monkeypatch.setattr(socket, "socket", real_socket)
