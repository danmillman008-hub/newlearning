"""Tests for gramophone_m3.merge (+ merge CLI)."""

import json
from pathlib import Path

import pytest

from gramophone_m3 import cli, merge, pipeline

ROOT = Path(__file__).resolve().parent.parent
CH_A = str(ROOT / "fixtures" / "chapter_a.json")
CH_B = str(ROOT / "fixtures" / "chapter_b.json")


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_merge_golden_counts_and_shape():
    book = merge.merge_graphs([_load(CH_A), _load(CH_B)], ["a", "b"])
    assert [i["id"] for i in book["items"]] == [
        "a:alpha", "a:beta", "a:s1", "b:gamma", "b:s2",
    ]
    assert book["surmise"] == [
        ["a:alpha", "a:beta"], ["a:beta", "a:s1"], ["b:s2", "b:gamma"],
    ]
    assert len(book["states"]) == 12  # chain3 x chain2 ideals
    assert book["fringe_cache"] == {"": ["a:alpha", "b:s2"]}
    assert [c["id"] for c in book["competences"]] == ["a:ca1", "b:cb1"]
    by_id = {i["id"]: i for i in book["items"]}
    assert by_id["a:alpha"]["required_competences"] == ["a:ca1"]
    assert by_id["b:gamma"]["required_competences"] == ["b:cb1"]
    assert by_id["a:beta"]["provenance"]["chapter"] == "a"
    # shared label coexists as two distinct namespaced ids
    shared = [i["id"] for i in book["items"] if i["label"] == "Shared"]
    assert shared == ["a:s1", "b:s2"]
    meta = book["metadata"]
    assert meta["chapters"] == ["a", "b"]
    assert meta["version"] == "1"
    assert meta["overflow"] is False
    assert meta["provenance"]["source_materials"] == ["chapter_a.md", "chapter_b.md"]
    assert any("gramophone-m3" in e for e in meta["provenance"]["change_log"])


def test_merge_rejections():
    a = _load(CH_A)
    with pytest.raises(ValueError):
        merge.merge_graphs([], [])
    with pytest.raises(ValueError):
        merge.merge_graphs([a, a], ["x", "x"])
    with pytest.raises(ValueError):
        merge.merge_graphs([a], ["x", "y"])
    with pytest.raises(ValueError):
        merge.merge_graphs([{"nope": 1}], ["x"])
    bad_edge = dict(a, surmise=[["alpha", "ghost"]])
    with pytest.raises(ValueError):
        merge.merge_graphs([bad_edge], ["x"])
    bad_item = dict(a, items=[{"label": "no-id"}])
    with pytest.raises(ValueError):
        merge.merge_graphs([bad_item], ["x"])


def test_merge_deterministic(tmp_path):
    first = pipeline.run_merge([CH_A, CH_B], str(tmp_path / "a"), ["a", "b"])
    second = pipeline.run_merge([CH_A, CH_B], str(tmp_path / "b"), ["a", "b"])
    assert first == second
    books = []
    for side in ("a", "b"):
        with open(tmp_path / side / "book-graph.json", encoding="utf-8") as f:
            book = json.load(f)
        book["metadata"].pop("generated_at")
        books.append(book)
    assert books[0] == books[1]


def test_merge_overflow_partitions():
    def chain(n, tag):
        items = [
            {"id": f"i{k}", "tags": [tag], "required_competences": [],
             "provenance": {"chunk_id": "c", "page": 0, "span": [0, 1]}}
            for k in range(n)
        ]
        edges = [[f"i{k}", f"i{k+1}"] for k in range(n - 1)]
        return {"items": items, "surmise": edges, "metadata": {}}

    book = merge.merge_graphs([chain(223, "t1"), chain(223, "t2")], ["a", "b"])
    assert book["metadata"]["overflow"] is True
    assert book["states"] == []
    assert sorted(book["metadata"]["partitions"]) == ["t1", "t2"]
    assert book["fringe_cache"] == {"": ["a:i0", "b:i0"]}


def test_cli_merge_golden_and_exits(tmp_path, capsys):
    out = str(tmp_path)
    assert cli.main(["merge", CH_A, CH_B, "--out", out, "--names", "a", "b"]) == 0
    assert "MERGED CHAPTERS=2 ITEMS=5 EDGES=3 STATES=12 FRINGE0=2 OVERFLOW=0" in capsys.readouterr().out
    assert (tmp_path / "book-graph.json").exists()
    assert (tmp_path / "M3-REPORT.md").exists()
    assert cli.main(["merge", str(tmp_path / "nope.json"), "--out", out]) == 2
    assert cli.main(["merge", CH_A, CH_B, "--out", out, "--names", "only"]) == 2
