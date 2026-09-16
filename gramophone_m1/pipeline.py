"""Orchestration: break_file() runs INPUT -> v0.1 graph -> v1 graph + report.

Budgets are checked before each LLM call; on BudgetExhausted the stage degrades
to its rule path (fewer-never-wrong) and the run still succeeds. Determinism:
same input + same cassette = byte-identical JSON outputs (modulo the
metadata timestamps, which callers can normalize).
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

from . import itemize, kg_extract, pdf_input, spacing, surmise
from .llm_client import BudgetExhausted, MockLLM

V01_FILENAME = "knowledge-graph.v0_1.json"
V1_FILENAME = "knowledge-graph.json"
REPORT_FILENAME = "M1-REPORT.md"
# NFR4 fewer-never-wrong: a run that exhausts its token budget caps items.
DEGRADED_MAX_ITEMS = 10
# Perf/recursion safety bound for user-supplied --max-items.
MAX_ITEMS_LIMIT = 2000


def default_cassette_path() -> str:
    """Default cassette: env override, else bundled, else legacy sibling."""
    override = os.environ.get("GRAMOPHONE_CASSETTE")
    if override:
        return override
    here = os.path.dirname(os.path.abspath(__file__))
    bundled = os.path.join(here, "cassettes", "mock_default.json")
    if os.path.exists(bundled):
        return bundled
    return os.path.join(os.path.dirname(here), "cassettes", "mock_default.json")


def default_llm() -> MockLLM | None:
    """Default backend: MockLLM with the bundled cassette (None if missing)."""
    path = default_cassette_path()
    if os.path.exists(path):
        return MockLLM.from_file(path)
    return None


def _remaining(token_budget: int | None, llm) -> int | None:
    if token_budget is None or llm is None:
        return None
    return token_budget - llm.total_tokens


def _write_json(path: str, payload: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(payload, sort_keys=True, indent=2) + "\n")


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def break_file(
    input_path: str,
    outdir: str,
    max_items: int = 300,
    token_budget: int | None = None,
    llm=None,
) -> dict:
    """Run the full M1 pipeline; returns counts, stdout line and out paths."""
    if (
        isinstance(max_items, bool)
        or not isinstance(max_items, int)
        or not 1 <= max_items <= MAX_ITEMS_LIMIT
    ):
        raise ValueError(
            f"pipeline: max_items must be an int in 1..{MAX_ITEMS_LIMIT}, "
            f"got {max_items!r}"
        )
    blocks = pdf_input.read_blocks(input_path)
    os.makedirs(outdir, exist_ok=True)
    if not blocks:
        # Empty or scanned-only input: warn loudly, spend no LLM tokens, and
        # let the rule paths yield the honest zero instead of cassette noise.
        print(
            f"gramophone-m1: warning: no text blocks extracted from {input_path} "
            "(empty or scanned-only input?)",
            file=sys.stderr,
        )
        llm = None

    degraded: list[str] = []
    drops: list[dict] = []

    # Stage 1: blocks -> KG.
    try:
        kg = kg_extract.extract_kg(blocks, llm=llm, budget=_remaining(token_budget, llm))
    except BudgetExhausted:
        degraded.append("kg_extract")
        kg = kg_extract.extract_kg(blocks, llm=None)

    # Stage 2: KG -> items (v0.1).
    try:
        pack = itemize.items_from_kg(
            kg,
            llm=llm,
            budget=_remaining(token_budget, llm),
            max_items=max_items,
            blocks=blocks,
        )
    except BudgetExhausted:
        degraded.append("itemize")
        pack = itemize.items_from_kg(kg, llm=None, max_items=max_items, blocks=blocks)
    items, competences = pack["items"], pack["competences"]
    drops.extend(pack["log"])
    if degraded and len(items) > DEGRADED_MAX_ITEMS:
        # NFR4: budget-degraded runs emit fewer (id-sorted, deterministic) items.
        for extra in items[DEGRADED_MAX_ITEMS:]:
            drops.append(
                {
                    "id": extra["id"],
                    "decision": "dropped",
                    "reason": f"degraded-mode cap {DEGRADED_MAX_ITEMS} (token budget)",
                }
            )
        items = items[:DEGRADED_MAX_ITEMS]

    chapter = os.path.basename(input_path)
    v01 = {
        "metadata": {
            "chapter": chapter,
            "version": "0.1",
            "generated_at": _utcnow(),
            "provenance": {
                "source_materials": [input_path],
                "change_log": ["built by gramophone-m1 break"],
            },
        },
        "items": items,
        "competences": competences,
        "surmise_relations": [],
        "competence_relations": [],
    }

    # Stage 3: items -> surmise DAG.
    try:
        epack = surmise.infer_edges(
            items, kg, llm=llm, budget=_remaining(token_budget, llm)
        )
    except BudgetExhausted:
        degraded.append("surmise")
        epack = surmise.infer_edges(items, kg, llm=None)
    edges = epack["edges"]

    # Stage 4: DAG -> states + fringe (v1).
    ids = [i["id"] for i in items]
    enum = spacing.enumerate_states(ids, edges)
    states: list[list[str]]
    partitions: dict | None = None
    overflow = bool(enum["overflow"])
    if overflow:
        clusters = spacing.partition_by_tag(items, edges)
        partitions = {
            tag: spacing.enumerate_states(c["items"], c["edges"])["states"]
            for tag, c in clusters.items()
        }
        states = []
    else:
        states = enum["states"]
    fringe0 = spacing.fringe([], ids, edges)

    v1 = dict(v01)
    v1["metadata"] = dict(v01["metadata"])
    v1["metadata"]["version"] = "1"
    v1["metadata"]["generated_at"] = _utcnow()
    v1["metadata"]["degraded_stages"] = degraded
    v1["metadata"]["overflow"] = overflow
    if partitions is not None:
        v1["metadata"]["partitions"] = partitions
    v1["surmise"] = edges
    v1["states"] = states
    v1["fringe_cache"] = {"": fringe0}

    v01_path = os.path.join(outdir, V01_FILENAME)
    v1_path = os.path.join(outdir, V1_FILENAME)
    _write_json(v01_path, v01)
    _write_json(v1_path, v1)

    tokens = llm.total_tokens if llm is not None else 0
    stdout_line = (
        f"ITEMS={len(items)} EDGES={len(edges)} STATES={len(states)} "
        f"FRINGE0={len(fringe0)} TOKENS={tokens}"
    )

    report_path = os.path.join(outdir, REPORT_FILENAME)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(
            "# Gramophone M1 report\n\n"
            f"- input: {input_path}\n"
            f"- chapter: {chapter}\n"
            f"- generated_at: {_utcnow()}\n"
            f"- blocks: {len(blocks)}"
            + ("" if blocks else " (WARNING: no text extracted — output is empty)")
            + "\n"
            f"- entities: {len(kg.get('entities', []))}\n"
            f"- relations: {len(kg.get('relations', []))}\n"
            f"- items: {len(items)}\n"
            f"- competences: {len(competences)}\n"
            f"- surmise edges: {len(edges)} "
            f"(dropped as cyclic: {len(epack['dropped'])})\n"
            f"- states: {len(states)} (overflow: {overflow})\n"
            f"- fringe(empty): {len(fringe0)}\n"
            f"- tokens spent: {tokens} (budget: {token_budget})\n"
            f"- degraded stages: {degraded or 'none'}\n"
            f"- gate decisions: "
            f"{sum(1 for d in drops if d['decision'] == 'accepted')} accepted, "
            f"{sum(1 for d in drops if d['decision'] == 'split')} split, "
            f"{sum(1 for d in drops if d['decision'] == 'dropped')} dropped\n"
            f"- outputs: {V01_FILENAME}, {V1_FILENAME}, {REPORT_FILENAME}\n"
        )

    return {
        "items": len(items),
        "edges": len(edges),
        "states": len(states),
        "fringe0": len(fringe0),
        "tokens": tokens,
        "overflow": overflow,
        "degraded": degraded,
        "stdout": stdout_line,
        "v01_path": v01_path,
        "v1_path": v1_path,
        "report_path": report_path,
    }
