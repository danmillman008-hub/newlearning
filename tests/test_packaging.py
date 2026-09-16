"""Tests for the M7 bundled-cassette packaging."""

import json
import os
from pathlib import Path

import gramophone_m1.pipeline as m1pipe
from gramophone_m1.llm_client import MockLLM

PKG_DIR = Path(m1pipe.__file__).resolve().parent


def test_bundled_cassette_preferred_without_env(monkeypatch):
    monkeypatch.delenv("GRAMOPHONE_CASSETTE", raising=False)
    path = m1pipe.default_cassette_path()
    assert path == os.path.join(str(PKG_DIR), "cassettes", "mock_default.json")
    assert os.path.exists(path)
    llm = m1pipe.default_llm()
    assert isinstance(llm, MockLLM)
    rsp = llm.complete("EXTRACT", "probe")
    assert rsp["text"]
    assert llm.total_tokens > 0


def test_bundled_matches_repo_cassettes():
    repo = Path(m1pipe.__file__).resolve().parent.parent / "cassettes"
    for name in ("mock_default.json", "mock_story.json"):
        bundled = (PKG_DIR / "cassettes" / name).read_bytes()
        assert bundled == (repo / name).read_bytes()


def test_cassette_resolves_from_bare_cwd(tmp_path, monkeypatch):
    # Install layout has no repo-root sibling; resolution is package-
    # relative, so a bare cwd must still work.
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GRAMOPHONE_CASSETTE", raising=False)
    llm = m1pipe.default_llm()
    assert isinstance(llm, MockLLM)
    assert llm.complete("EXTRACT", "probe")["text"]


def test_override_honored_and_bogus_override_is_none(tmp_path, monkeypatch):
    mini = tmp_path / "mini.json"
    mini.write_text(json.dumps({"EXTRACT": [{"text": "e", "tokens": 1}]}),
                    encoding="utf-8")
    monkeypatch.setenv("GRAMOPHONE_CASSETTE", str(mini))
    assert m1pipe.default_cassette_path() == str(mini)
    assert m1pipe.default_llm().complete("EXTRACT", "p")["text"] == "e"
    monkeypatch.setenv("GRAMOPHONE_CASSETTE", str(tmp_path / "nope.json"))
    assert m1pipe.default_cassette_path() == str(tmp_path / "nope.json")
    assert m1pipe.default_llm() is None
