"""Tests for M8: Flash backend selection + llm threading (all offline)."""

import json
from pathlib import Path

from gramophone_m1.llm_client import (
    GeminiFlashLLM,
    MockLLM,
    flash_llm_or_raise,
)
from gramophone_m2.cli import main as m2_main
from gramophone_m5 import bookquest
from gramophone_m5.cli import quest_main
from gramophone_m6 import cli as m6_cli
from gramophone_m6 import fullchain

ROOT = Path(__file__).resolve().parent.parent
CHA = str(ROOT / "fixtures" / "chapter_a.json")
CHB = str(ROOT / "fixtures" / "chapter_b.json")
RESPONSES = str(ROOT / "fixtures" / "m5_responses.txt")
CHAPTER = str(ROOT / "fixtures" / "sample_chapter.md")
M6_RESPONSES = str(ROOT / "fixtures" / "m6_responses.txt")
STORY = str(ROOT / "cassettes" / "mock_story.json")
DEFAULT = str(ROOT / "cassettes" / "mock_default.json")


def _keyless(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


def test_flash_helper_keyless_raises_value_error(monkeypatch):
    _keyless(monkeypatch)
    try:
        flash_llm_or_raise()
    except ValueError as e:
        assert "GEMINI_API_KEY" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_flash_helper_with_key_returns_backend_zero_calls(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "FAKE")
    llm = flash_llm_or_raise()
    assert isinstance(llm, GeminiFlashLLM)
    assert llm.total_tokens == 0


def test_bookquest_threads_story_llm(tmp_path, monkeypatch):
    _keyless(monkeypatch)
    out = str(tmp_path)
    session = bookquest.run_book_quest(
        [CHA, CHB], out, responses_path=RESPONSES,
        llm=MockLLM.from_file(STORY),
    )
    report = (tmp_path / "M5-REPORT.md").read_text(encoding="utf-8")
    assert "TOKENS=0" not in [
        ln for ln in report.splitlines() if ln.startswith("BEATS=")
    ][-1]
    assert session["completion"]["reason"] == "quest_complete"


def test_fullchain_threads_explicit_mock(tmp_path, monkeypatch):
    _keyless(monkeypatch)
    result = fullchain.run_full_chain(
        [CHAPTER], str(tmp_path), responses_path=M6_RESPONSES, names=["chap"],
        llm=MockLLM.from_file(DEFAULT),
    )
    assert result["m1"][0]["tokens"] > 0
    assert result["session"]["completion"]["reason"] == "quest_complete"


def test_fullchain_none_matches_explicit_default_mock(tmp_path, monkeypatch):
    _keyless(monkeypatch)
    kw = dict(responses_path=M6_RESPONSES, names=["chap"])
    a = fullchain.run_full_chain([CHAPTER], str(tmp_path / "a"), **kw)
    b = fullchain.run_full_chain(
        [CHAPTER], str(tmp_path / "b"), llm=MockLLM.from_file(DEFAULT), **kw)
    assert a["session"] == b["session"]
    assert (a["m1"][0]["items"], a["m1"][0]["edges"]) == (
        b["m1"][0]["items"], b["m1"][0]["edges"])


def test_m2_author_flash_keyless_exits_2(tmp_path, monkeypatch):
    _keyless(monkeypatch)
    graph = tmp_path / "g.json"
    graph.write_text(json.dumps({"metadata": {}, "items": [], "surmise": []}))
    rc = m2_main(["author", str(graph), "--out", str(tmp_path / "o"),
                  "--llm", "flash"])
    assert rc == 2


def test_m5_quest_flash_keyless_exits_2(tmp_path, monkeypatch):
    _keyless(monkeypatch)
    rc = quest_main([CHA, CHB, "--out", str(tmp_path), "--responses", RESPONSES,
                     "--llm", "flash"])
    assert rc == 2


def test_m6_flash_keyless_exits_2(tmp_path, monkeypatch):
    _keyless(monkeypatch)
    rc = m6_cli.main([CHAPTER, "--out", str(tmp_path), "--llm", "flash",
                      "--responses", M6_RESPONSES])
    assert rc == 2


def test_m6_mock_flag_matches_default(tmp_path, monkeypatch):
    _keyless(monkeypatch)
    base = [CHAPTER, "--responses", M6_RESPONSES]
    assert m6_cli.main(base + ["--out", str(tmp_path / "a")]) == 0
    assert m6_cli.main(base + ["--out", str(tmp_path / "b"), "--llm", "mock"]) == 0
    for name in ("beats.json", "session.json"):
        a = (tmp_path / "a" / name).read_text(encoding="utf-8")
        b = (tmp_path / "b" / name).read_text(encoding="utf-8")
        assert a == b
    ga = json.loads((tmp_path / "a" / "book-graph.json").read_text())
    gb = json.loads((tmp_path / "b" / "book-graph.json").read_text())
    ga.get("metadata", {}).pop("generated_at", None)
    gb.get("metadata", {}).pop("generated_at", None)
    assert ga == gb
