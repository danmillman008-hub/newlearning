"""Session tests for M2: learn golden, author golden, CLI, determinism."""

import json
import socket
from pathlib import Path

import pytest

from gramophone_m2 import cli, pipeline, story_model, xapi

ROOT = Path(__file__).resolve().parent.parent
BEATS = str(ROOT / "fixtures" / "sample_beats.json")
SCRIPT = str(ROOT / "fixtures" / "sample_script.json")


def test_sample_quest_meets_minimums():
    data = story_model.load_beats(BEATS)
    assert story_model.validate(data) == []
    assert len(data["beats"]) >= 8
    assert len(data["checks"]) >= 4


def test_learn_golden_counts(tmp_path):
    session = pipeline.run_learn(BEATS, SCRIPT, str(tmp_path))
    assert session["beats_visited"] == ["q1", "q2", "q5", "q3", "q7"]
    assert session["attempts"] == 7
    assert session["passed"] == 6
    assert session["xp"] == 67
    assert session["level"] == 1
    assert session["streak_max"] == 3
    assert session["xapi_statements"] == 19
    assert session["flow_in_band_ratio"] == pytest.approx(3 / 7, abs=1e-4)
    assert session["mastery"]["central-tendency"] == pytest.approx(0.75)
    assert session["mastery"]["median"] == pytest.approx(0.3628, abs=1e-3)
    assert (tmp_path / "session.json").exists()
    assert (tmp_path / "xapi.jsonl").exists()
    assert (tmp_path / "M2-REPORT.md").exists()


def test_learn_deterministic_bytes(tmp_path):
    first = pipeline.run_learn(BEATS, SCRIPT, str(tmp_path / "a"))
    second = pipeline.run_learn(BEATS, SCRIPT, str(tmp_path / "b"))
    assert first == second
    for name in ("session.json", "xapi.jsonl"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()


def test_learn_rejects_bad_script(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"actor": "x", "attempts": [{"beat_id": "nope"}]}))
    with pytest.raises(ValueError):
        pipeline.run_learn(BEATS, str(bad), str(tmp_path))


def test_author_golden_on_m1_graph(tmp_path):
    from gramophone_m1 import pipeline as m1_pipeline

    m1out = tmp_path / "m1"
    m1_pipeline.break_file(
        str(ROOT / "fixtures" / "sample_chapter.md"), str(m1out),
        llm=m1_pipeline.default_llm(),
    )
    from gramophone_m1.llm_client import MockLLM

    llm = MockLLM.from_file(str(ROOT / "cassettes" / "mock_story.json"))
    report = pipeline.run_author(str(m1out / "knowledge-graph.json"), str(tmp_path), llm)
    assert report["beats"] == 10
    assert report["checks"] == 7
    assert sum(report["pruned"].values()) == 4
    assert report["tokens"] == 1000
    data = story_model.load_beats(str(tmp_path / "beats.json"))
    assert story_model.validate(data) == []


def test_no_network_default_path(tmp_path, monkeypatch):
    real_socket = socket.socket

    def blocked(*a, **k):
        raise RuntimeError("network disabled in test")

    monkeypatch.setattr(socket, "socket", blocked)
    try:
        session = pipeline.run_learn(BEATS, SCRIPT, str(tmp_path))
        assert session["attempts"] == 7
    finally:
        monkeypatch.setattr(socket, "socket", real_socket)


def test_export_xapi_roundtrip(tmp_path):
    pipeline.run_learn(BEATS, SCRIPT, str(tmp_path))
    n = xapi.export_xapi(str(tmp_path / "xapi.jsonl"), str(tmp_path / "export.jsonl"))
    assert n == 19
    with pytest.raises(ValueError):
        xapi.export_xapi(str(tmp_path / "missing.jsonl"), str(tmp_path / "x.jsonl"))


def test_cli_golden_and_exits(tmp_path, capsys):
    assert cli.main(["learn", BEATS, "--script", SCRIPT, "--out", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "VISITED=5 ATTEMPTS=7 PASSED=6 XP=67 LEVEL=1 STREAK_MAX=3" in out
    assert cli.main(["learn", str(tmp_path / "nope.json"), "--script", SCRIPT,
                     "--out", str(tmp_path)]) == 2
    assert cli.main(["export-xapi", str(tmp_path / "xapi.jsonl"),
                     "--out", str(tmp_path / "e.jsonl")]) == 0
    assert "STATEMENTS=19" in capsys.readouterr().out
