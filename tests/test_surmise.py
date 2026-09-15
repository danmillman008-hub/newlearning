"""Unit tests: surmise cycle detection, DAG enforcement, property tests."""

import json
import random

from gramophone_m1.llm_client import MockLLM
from gramophone_m1.surmise import enforce_dag, find_cycle, infer_edges

ITEMS = [
    {"id": "a", "label": "Alpha"},
    {"id": "b", "label": "Beta"},
    {"id": "c", "label": "Gamma"},
]


def test_find_cycle_detects_triangle_and_clears_dag():
    assert find_cycle({"a": ["b"], "b": ["c"], "c": ["a"]}) is not None
    assert find_cycle({"a": ["b"], "b": ["c"], "c": []}) is None
    assert find_cycle({}) is None


def test_find_cycle_is_deterministic():
    adj = {"a": ["b", "c"], "b": ["c"], "c": ["a"], "d": ["a"]}
    assert find_cycle(adj) == find_cycle(adj)


def test_enforce_dag_drops_lowest_confidence_edge():
    dag, dropped = enforce_dag([("a", "b", 0.9), ("b", "c", 0.9), ("c", "a", 0.1)])
    assert dag == [["a", "b"], ["b", "c"]]
    assert dropped == [
        {"prereq": "c", "item": "a", "confidence": 0.1, "reason": "removed to break cycle"}
    ]


def test_enforce_dag_breaks_confidence_ties_by_id_order():
    dag, dropped = enforce_dag([("b", "c", 0.5), ("c", "a", 0.5), ("a", "b", 0.5)])
    # All confidences tied: the lexicographically smallest edge drops.
    assert dag == [["b", "c"], ["c", "a"]]
    assert [d["prereq"] for d in dropped] == ["a"]


def test_enforce_dag_keeps_clean_graph_and_sorts():
    dag, dropped = enforce_dag([("b", "c"), ("a", "b")])
    assert dag == [["a", "b"], ["b", "c"]]
    assert dropped == []


def _is_acyclic(pairs) -> bool:
    adj: dict = {}
    for p, i in pairs:
        adj.setdefault(p, []).append(i)
        adj.setdefault(i, [])
    return find_cycle(adj) is None


def test_dag_property_random_graphs_are_acyclic_subsets():
    rng = random.Random(42)
    for _ in range(100):
        n = rng.randint(0, 8)
        nodes = [f"n{i}" for i in range(n)]
        edges = [
            (a, b, round(rng.random(), 3))
            for a in nodes
            for b in nodes
            if a != b and rng.random() < 0.3
        ]
        dag, _ = enforce_dag(edges)
        pairs = {(p, i) for p, i in dag}
        assert _is_acyclic(pairs)
        assert pairs <= {(p, i) for p, i, _ in edges}
        # Deterministic: same input, same output.
        assert enforce_dag(edges)[0] == dag


def test_infer_edges_llm_path_filters_and_breaks_cycles():
    payload = {
        "edges": [
            {"prereq": "a", "item": "b", "confidence": 0.9},
            {"prereq": "Beta", "item": "Gamma", "confidence": 0.8},
            {"prereq": "c", "item": "a", "confidence": 0.1},
            {"prereq": "a", "item": "a", "confidence": 1.0},
            {"prereq": "ghost", "item": "a", "confidence": 1.0},
        ]
    }
    llm = MockLLM({"ANALYZE": [{"text": json.dumps(payload), "tokens": 4}]})
    pack = infer_edges(ITEMS, {"entities": [], "relations": []}, llm=llm)
    assert pack["edges"] == [["a", "b"], ["b", "c"]]
    assert [d["prereq"] for d in pack["dropped"]] == ["c"]


def test_infer_edges_rule_path_proposes_no_edges():
    assert infer_edges(ITEMS, llm=None) == {"edges": [], "dropped": []}
