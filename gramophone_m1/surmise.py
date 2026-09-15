"""Surmise stage: items -> prerequisite edges (a DAG, always).

Output edges are ``[prereq_id, item_id]`` pairs. LLM proposals pass through
deterministic DAG enforcement: iterative DFS cycle detection; per cycle the
lowest-confidence edge is dropped (ties broken by id order) until acyclic.
The rule path proposes no edges (fewer-never-wrong: invented prerequisites
could be wrong, missing ones are merely fewer).
"""

from __future__ import annotations

import json

from .llm_client import ROLE_ANALYZE


def _surmise_prompt(items: list[dict], kg: dict) -> str:
    slim = [{"id": i["id"], "label": i["label"]} for i in items]
    return (
        "Given these knowledge items (and the KG relations for context), propose "
        "prerequisite edges: [prereq, item] means prereq must be learned first.\n"
        "Reply with JSON ONLY:\n"
        '{"edges": [{"prereq": id-or-label, "item": id-or-label, "confidence": 0..1}]}\n'
        "ITEMS:\n" + json.dumps(slim, sort_keys=True)
        + "\nRELATIONS:\n" + json.dumps(kg.get("relations", []), sort_keys=True)
    )


def _normalize_llm_edges(
    payload: dict, items: list[dict]
) -> list[tuple[str, str, float]]:
    by_id = {i["id"]: i["id"] for i in items}
    by_label = {i["label"].strip().lower(): i["id"] for i in items}

    def resolve(ref) -> str:
        key = str(ref or "").strip()
        return by_id.get(key) or by_label.get(key.lower(), "")

    edges: dict[tuple[str, str], float] = {}
    for raw in payload.get("edges") or []:
        pre, itm = resolve(raw.get("prereq")), resolve(raw.get("item"))
        if not pre or not itm or pre == itm:
            continue
        try:
            conf = float(raw.get("confidence", 1.0))
        except (TypeError, ValueError):
            conf = 1.0
        conf = min(1.0, max(0.0, conf))
        key = (pre, itm)
        edges[key] = max(conf, edges.get(key, 0.0))
    return [(p, i, c) for (p, i), c in edges.items()]


def find_cycle(adj: dict[str, list[str]]) -> list[tuple[str, str]] | None:
    """Deterministic iterative DFS cycle detection; returns cycle edges or None.

    Explicit stack (no recursion): safe for chains far beyond the 1000-frame
    interpreter limit. Traversal order matches the recursive formulation, so
    the reported cycle is identical: sorted roots, sorted neighbors.
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {node: WHITE for node in adj}
    for root in sorted(adj):
        if color[root] != WHITE:
            continue
        path: list[str] = [root]
        iters: list = [iter(sorted(adj.get(root, [])))]
        color[root] = GRAY
        while iters:
            descended = False
            for nxt in iters[-1]:
                if nxt not in color:
                    continue
                if color[nxt] == GRAY:
                    idx = path.index(nxt)
                    cyc_nodes = path[idx:] + [nxt]
                    return list(zip(cyc_nodes, cyc_nodes[1:]))
                if color[nxt] == WHITE:
                    color[nxt] = GRAY
                    path.append(nxt)
                    iters.append(iter(sorted(adj.get(nxt, []))))
                    descended = True
                    break
            if not descended:
                color[path.pop()] = BLACK
                iters.pop()
    return None


def enforce_dag(
    edges: list[tuple[str, str, float]] | list[list[str]],
) -> tuple[list[list[str]], list[dict]]:
    """Drop lowest-confidence edge per cycle until the graph is a DAG.

    Returns (dag_edges sorted by [prereq, item], dropped records).
    """
    weighted = [
        (e[0], e[1], float(e[2]) if len(e) > 2 else 1.0) for e in edges
    ]
    remaining = {(p, i): c for p, i, c in weighted if p != i}
    dropped: list[dict] = []
    while True:
        adj: dict[str, list[str]] = {}
        for p, i in remaining:
            adj.setdefault(p, []).append(i)
            adj.setdefault(i, [])
        cycle = find_cycle(adj)
        if not cycle:
            break
        victim = min(cycle, key=lambda e: (remaining[e], e[0], e[1]))
        dropped.append(
            {
                "prereq": victim[0],
                "item": victim[1],
                "confidence": remaining[victim],
                "reason": "removed to break cycle",
            }
        )
        del remaining[victim]
    dag = sorted([[p, i] for p, i in remaining])
    dropped.sort(key=lambda d: (d["prereq"], d["item"]))
    return dag, dropped


def infer_edges(
    items: list[dict],
    kg: dict | None = None,
    llm=None,
    budget: int | None = None,
) -> dict:
    """Infer prerequisite edges for items (LLM path or empty rule path)."""
    kg = kg or {"entities": [], "relations": []}
    proposals: list[tuple[str, str, float]] = []
    if llm is not None:
        reply = llm.complete(ROLE_ANALYZE, _surmise_prompt(items, kg), budget)
        try:
            payload = json.loads(reply["text"])
            if isinstance(payload, dict):
                proposals = _normalize_llm_edges(payload, items)
        except (json.JSONDecodeError, TypeError, AttributeError):
            proposals = []
    dag, dropped = enforce_dag(proposals)
    return {"edges": dag, "dropped": dropped}
