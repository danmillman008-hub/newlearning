"""Integration tests: LLM wiring, golden run, determinism, budget, no-network."""

import json
import re
from pathlib import Path

import pytest

from gramophone_m1 import cli as cli_module
from gramophone_m1.cli import main as cli_main
from gramophone_m1.llm_client import (
    BudgetExhausted,
    CassetteExhausted,
    GeminiFlashLLM,
    MockLLM,
)
from gramophone_m1.pipeline import break_file

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "fixtures" / "sample_chapter.md"
CASSETTE = ROOT / "cassettes" / "mock_default.json"

STDOUT_RE = re.compile(r"^ITEMS=(\d+) EDGES=(\d+) STATES=(\d+) FRINGE0=(\d+) TOKENS=(\d+)$")


def _fresh_mock() -> MockLLM:
    return MockLLM.from_file(str(CASSETTE))


# --- LLM client wiring -----------------------------------------------------


def test_mock_llm_consumes_roles_in_order_and_cycles():
    llm = MockLLM(
        {
            "EXTRACT": [{"text": "e1", "tokens": 2}],
            "ANALYZE": [{"text": "a1", "tokens": 3}, {"text": "a2", "tokens": 4}],
        }
    )
    assert llm.complete("EXTRACT", "p")["text"] == "e1"
    assert llm.complete("ANALYZE", "p")["text"] == "a1"
    assert llm.complete("ANALYZE", "p")["text"] == "a2"
    assert llm.complete("ANALYZE", "p")["text"] == "a1"  # deterministic cycle
    assert llm.total_tokens == 2 + 3 + 4 + 3


def test_mock_llm_unknown_role_raises():
    llm = MockLLM({"EXTRACT": [{"text": "e", "tokens": 1}]})
    try:
        llm.complete("ANALYZE", "p")
    except CassetteExhausted:
        pass
    else:
        raise AssertionError("expected CassetteExhausted")


def test_mock_llm_budget_checked_before_spending():
    llm = MockLLM({"EXTRACT": [{"text": "e1", "tokens": 10}]})
    try:
        llm.complete("EXTRACT", "p", budget=5)
    except BudgetExhausted:
        pass
    else:
        raise AssertionError("expected BudgetExhausted")
    assert llm.total_tokens == 0
    # Failed call consumed nothing: the response is still next.
    assert llm.complete("EXTRACT", "p", budget=50)["text"] == "e1"
    assert llm.total_tokens == 10


def test_gemini_backend_constructible_without_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("FLASH_MODEL", raising=False)
    client = GeminiFlashLLM()
    assert client.model == "gemini-3-flash-preview"
    assert client.total_tokens == 0
    try:
        client.complete("EXTRACT", "hi")
    except RuntimeError as exc:
        assert "API key" in str(exc)
    else:
        raise AssertionError("expected RuntimeError without key")


def test_gemini_backend_honors_flash_model_env(monkeypatch):
    monkeypatch.setenv("FLASH_MODEL", "gemini-9-flash-test")
    assert GeminiFlashLLM().model == "gemini-9-flash-test"


# --- Golden pipeline -------------------------------------------------------


def test_golden_run_meets_minimums_and_schema(tmp_path):
    res = break_file(str(FIXTURE), str(tmp_path), llm=_fresh_mock())
    assert res["items"] >= 15
    assert res["edges"] >= 10
    assert res["fringe0"] >= 1
    assert res["tokens"] == 1800 + 2400 + 900
    assert res["degraded"] == []
    assert res["overflow"] is False
    match = STDOUT_RE.match(res["stdout"])
    assert match and int(match.group(1)) == res["items"]

    v1 = json.loads(Path(res["v1_path"]).read_text(encoding="utf-8"))
    assert v1["metadata"]["version"] == "1"
    assert len(v1["items"]) == res["items"]
    assert len(v1["surmise"]) == res["edges"]
    assert len(v1["states"]) == res["states"]
    assert "" in v1["fringe_cache"]
    assert len(v1["competences"]) >= 1
    for item in v1["items"]:
        assert set(item["provenance"]) == {"chunk_id", "page", "span"}

    v01 = json.loads(Path(res["v01_path"]).read_text(encoding="utf-8"))
    assert v01["metadata"]["version"] == "0.1"
    assert len(v01["items"]) == res["items"]

    report = Path(res["report_path"]).read_text(encoding="utf-8")
    assert f"- items: {res['items']}" in report
    assert f"- tokens spent: {res['tokens']}" in report


def _normalized_graph(path: str) -> str:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    payload["metadata"]["generated_at"] = "NORMALIZED"
    return json.dumps(payload, sort_keys=True)


def test_deterministic_two_runs_identical_modulo_timestamps(tmp_path):
    first = break_file(str(FIXTURE), str(tmp_path / "a"), llm=_fresh_mock())
    second = break_file(str(FIXTURE), str(tmp_path / "b"), llm=_fresh_mock())
    assert _normalized_graph(first["v1_path"]) == _normalized_graph(second["v1_path"])
    assert _normalized_graph(first["v01_path"]) == _normalized_graph(second["v01_path"])
    assert first["stdout"] == second["stdout"]


def test_tiny_budget_degrades_to_fewer_items_and_exit_zero(tmp_path):
    full = break_file(str(FIXTURE), str(tmp_path / "full"), llm=_fresh_mock())
    lite = break_file(
        str(FIXTURE), str(tmp_path / "lite"), token_budget=100, llm=_fresh_mock()
    )
    assert lite["items"] < full["items"]
    assert lite["tokens"] < full["tokens"]
    assert lite["degraded"] == ["kg_extract", "itemize", "surmise"]
    v1 = json.loads(Path(lite["v1_path"]).read_text(encoding="utf-8"))
    assert v1["metadata"]["version"] == "1"
    assert len(v1["items"]) == lite["items"]


def test_no_network_during_default_run(monkeypatch, tmp_path):
    import socket

    def _blocked(*args, **kwargs):
        raise AssertionError("network socket used during MockLLM run")

    monkeypatch.setattr(socket, "socket", _blocked)
    res = break_file(str(FIXTURE), str(tmp_path), llm=_fresh_mock())
    assert res["items"] >= 15


# --- max_items validation + deep-chain stress (F2) ---------------------------


def test_max_items_validation_rejects_nonsense(tmp_path):
    for bad in (0, -5, 5000, True, "10"):
        try:
            break_file(str(FIXTURE), str(tmp_path), max_items=bad, llm=_fresh_mock())
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for max_items={bad!r}")


def test_deep_chains_beyond_recursion_limit():
    from gramophone_m1.spacing import enumerate_states
    from gramophone_m1.surmise import enforce_dag

    chain = [(f"n{i}", f"n{i+1}", 1.0) for i in range(1500)]
    dag, dropped = enforce_dag(chain)
    assert len(dag) == 1500 and dropped == []
    nodes = [f"n{i}" for i in range(1501)]
    pack = enumerate_states(nodes, [[p, i] for p, i, _ in chain])
    assert len(pack["states"]) == 1502 and pack["overflow"] is False


# --- Empty input (F4) --------------------------------------------------------


def test_empty_input_warns_and_yields_zero_items(tmp_path, capsys):
    empty = tmp_path / "e.md"
    empty.write_text("\n", encoding="utf-8")
    res = break_file(str(empty), str(tmp_path / "o"), llm=_fresh_mock())
    assert res["items"] == 0 and res["edges"] == 0 and res["tokens"] == 0
    assert "warning" in capsys.readouterr().err.lower()
    report = Path(res["report_path"]).read_text(encoding="utf-8")
    assert "WARNING" in report


# --- CLI entry (F3) ----------------------------------------------------------


def test_cli_break_missing_input_returns_2(tmp_path):
    assert (
        cli_main(["break", str(ROOT / "fixtures" / "nope.md"), "--out", str(tmp_path)])
        == 2
    )


def test_cli_break_golden_returns_0_and_prints_counts(tmp_path, capsys):
    assert cli_main(["break", str(FIXTURE), "--out", str(tmp_path)]) == 0
    out = capsys.readouterr().out.strip()
    assert STDOUT_RE.match(out) and "TOKENS=5100" in out


def test_cli_break_bad_extension_returns_2(tmp_path):
    bad = tmp_path / "x.foo"
    bad.write_text("hi", encoding="utf-8")
    assert cli_main(["break", str(bad), "--out", str(tmp_path)]) == 2


def test_cli_internal_error_returns_1(monkeypatch, tmp_path):
    def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(cli_module, "break_file", _boom)
    assert cli_main(["break", str(FIXTURE), "--out", str(tmp_path)]) == 1


def test_cli_rejects_bad_max_items(tmp_path):
    base = ["break", str(FIXTURE), "--out", str(tmp_path)]
    assert cli_main(base + ["--max-items", "0"]) == 2
    assert cli_main(base + ["--max-items", "5000"]) == 2


def test_cli_missing_required_flag_raises_systemexit():
    with pytest.raises(SystemExit):
        cli_main(["break", str(FIXTURE)])


# --- Gemini REST shape (F5, HTTP mocked — still no network) ------------------


def test_gemini_rest_request_shape_and_accounting(monkeypatch):
    import urllib.request as urlreq

    from gramophone_m1 import llm_client as lc

    calls: dict = {}

    class FakeResp:
        def __init__(self, payload):
            self.payload = payload

        def read(self):
            return json.dumps(self.payload).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(req, timeout=60):
        calls["url"] = req.full_url
        calls["body"] = json.loads(req.data.decode("utf-8"))
        return FakeResp(
            {
                "candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}],
                "usageMetadata": {"totalTokenCount": 42},
            }
        )

    monkeypatch.setattr(urlreq, "urlopen", fake_urlopen)
    client = lc.GeminiFlashLLM(api_key="KEY")
    out = client.complete("EXTRACT", "do it", budget=100)
    assert out == {"text": '{"ok": true}', "tokens": 42}
    assert client.total_tokens == 42
    assert "generateContent" in calls["url"] and calls["url"].endswith("key=KEY")
    assert calls["body"]["generationConfig"]["responseMimeType"] == "application/json"
    prompt = calls["body"]["contents"][0]["parts"][0]["text"]
    assert prompt.startswith("[ROLE EXTRACT]\n")


def test_gemini_exhausted_budget_skips_http_call(monkeypatch):
    import urllib.request as urlreq

    from gramophone_m1 import llm_client as lc

    def _boom(req, timeout=60):
        raise AssertionError("HTTP must not be called on exhausted budget")

    monkeypatch.setattr(urlreq, "urlopen", _boom)
    client = lc.GeminiFlashLLM(api_key="KEY")
    try:
        client.complete("EXTRACT", "do it", budget=0)
    except BudgetExhausted:
        pass
    else:
        raise AssertionError("expected BudgetExhausted")
    assert client.total_tokens == 0
