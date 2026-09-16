"""Tests execute TUTORIAL.md's exact commands (tutorial cannot rot)."""

import json
from pathlib import Path

import pytest

from gramophone_m1.cli import main as m1_main
from gramophone_m5.cli import main as uni_main
from gramophone_m6.cli import main as m6_main

ROOT = Path(__file__).resolve().parent.parent
CHAPTER = str(ROOT / "fixtures" / "sample_chapter.md")
RESPONSES = str(ROOT / "fixtures" / "m6_responses.txt")


def test_tutorial_e2e(tmp_path, capsys):
    # Tutorial step 1: break the sample chapter.
    m1out = str(tmp_path / "m1")
    assert m1_main(["break", CHAPTER, "--out", m1out]) == 0
    assert "ITEMS=22 EDGES=17 STATES=36000 FRINGE0=8 TOKENS=5100" in (
        capsys.readouterr().out)
    assert (tmp_path / "m1" / "knowledge-graph.json").exists()
    # Tutorial step 2: quest it via the unified CLI.
    quest = str(tmp_path / "quest")
    assert uni_main(["m6", CHAPTER, "--names", "chap", "--responses",
                     RESPONSES, "--out", quest]) == 0
    printed = capsys.readouterr().out
    assert "BOOK CHAPTERS=1 ITEMS=22 EDGES=17 BEATS=22 CHECKS=22" in printed
    assert "SESSION VISITED=22 ATTEMPTS=23 PASSED=22 XP=220 LEVEL=3" in printed
    assert "COMPLETION=quest_complete" in printed
    with open(tmp_path / "quest" / "session.json", encoding="utf-8") as f:
        session = json.load(f)
    assert len(session["transcript"]) == 23
    assert (tmp_path / "quest" / "M6-REPORT.md").exists()
    assert (tmp_path / "quest" / "m1_chap" / "knowledge-graph.json").exists()
    # Tutorial step 3: split save/resume equals the whole quest.
    lines = Path(RESPONSES).read_text(encoding="utf-8").splitlines()
    (tmp_path / "first.txt").write_text("\n".join(lines[:2]) + "\n",
                                        encoding="utf-8")
    (tmp_path / "rest.txt").write_text("\n".join(lines[2:]) + "\n",
                                       encoding="utf-8")
    part = str(tmp_path / "part")
    state_path = str(tmp_path / "quest.json")
    assert m6_main([CHAPTER, "--names", "chap", "--responses",
                    str(tmp_path / "first.txt"), "--save", state_path,
                    "--out", part]) == 0
    assert "COMPLETION=responses_exhausted" in capsys.readouterr().out
    assert m6_main([CHAPTER, "--names", "chap", "--responses",
                    str(tmp_path / "rest.txt"), "--resume", state_path,
                    "--out", part]) == 0
    assert "COMPLETION=quest_complete" in capsys.readouterr().out
    with open(tmp_path / "part" / "session.json", encoding="utf-8") as f:
        resumed = json.load(f)
    assert resumed == session


def test_unified_m6_route_parity(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        uni_main(["m6", "--help"])
    assert exc.value.code == 0
    direct = str(tmp_path / "direct")
    via = str(tmp_path / "via")
    assert m6_main([CHAPTER, "--names", "chap", "--responses", RESPONSES,
                    "--out", direct]) == 0
    capsys.readouterr()
    assert uni_main(["m6", CHAPTER, "--names", "chap", "--responses",
                     RESPONSES, "--out", via]) == 0
    assert (tmp_path / "direct" / "session.json").read_bytes() == (
        tmp_path / "via" / "session.json").read_bytes()
