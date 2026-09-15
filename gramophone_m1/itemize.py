"""Itemize stage: KG -> atomic knowledge items + competences.

Item schema (v0.1)::

    {"id", "label", "description", "bloom", "knowledge_type", "dok",
     "assessment_criteria", "required_competences", "tags",
     "provenance": {"chunk_id", "page", "span"}}

Atomicity gate: an item is accepted only if it is Atomic + Assessable +
Meaningful. Rule pre-filters (length bounds, verb presence) run always; the
LLM path may additionally attach per-item oracle booleans. Failures go to a
single rule-based split attempt, then drop-plus-log.
"""

from __future__ import annotations

import json
import re

from .kg_extract import _unique_ids, slugify
from .llm_client import ROLE_ANALYZE

BLOOM_LEVELS = ("remember", "understand", "apply", "analyze", "evaluate", "create")
KNOWLEDGE_TYPES = ("factual", "conceptual", "procedural", "metacognitive")

# Verb presence heuristic for the assessable pre-filter (deterministic).
_VERBS = frozenset(
    """
    is are was were be been define defines defined state states stated describe
    describes described explain explains explained identify identifies identify
    calculate calculates calculated compute compare compares contrast
    distinguish interpret apply applies use uses demonstrate illustrate give
    gives list name recall recognize solve distinguish predict infer summarize
    discuss contrast outline show shows determine derive prove construct draw
    """.split()
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def atomicity_gate(item: dict) -> tuple[bool, str]:
    """Rule pre-filters + optional LLM-oracle booleans. Returns (ok, reason)."""
    label = str(item.get("label", ""))
    desc = str(item.get("description", ""))
    if not (3 <= len(label) <= 120):
        return False, f"label length {len(label)} outside 3..120"
    if not (10 <= len(desc) <= 2000):
        return False, f"description length {len(desc)} outside 10..2000"
    words = set(re.findall(r"[a-z]+", desc.lower()))
    if not (words & _VERBS):
        return False, "description has no assessable verb"
    oracle = item.get("atomicity") or {}
    for key in ("atomic", "assessable", "meaningful"):
        if key in oracle and not oracle[key]:
            return False, f"oracle flags {key}=false"
    return True, "pass"


def try_split(item: dict) -> list[dict]:
    """Split a failing item on its first sentence boundary (0, 1 or 2 items)."""
    desc = str(item.get("description", ""))
    parts = [p.strip() for p in _SENTENCE_SPLIT.split(desc) if p.strip()]
    if len(parts) < 2:
        return []
    children = []
    for suffix, part in (("-a", parts[0]), ("-b", " ".join(parts[1:]))):
        child = dict(item)
        child.pop("atomicity", None)
        child["id"] = f"{item.get('id', 'item')}{suffix}"
        child["description"] = part
        children.append(child)
    return children


def _itemize_prompt(kg: dict) -> str:
    return (
        "Turn this knowledge graph into atomic knowledge items for assessment.\n"
        "Reply with JSON ONLY:\n"
        '{"items": [{"label": str, "description": str, "bloom": one of '
        + "/".join(BLOOM_LEVELS)
        + ', "knowledge_type": one of '
        + "/".join(KNOWLEDGE_TYPES)
        + ', "dok": 1-4, "assessment_criteria": str, '
        '"required_competences": [str], "tags": [str], '
        '"provenance": {"chunk_id": str}, '
        '"atomicity": {"atomic": bool, "assessable": bool, "meaningful": bool}}], '
        '"competences": [{"label": str, "type": str}]}\n'
        "KG:\n" + json.dumps(kg, sort_keys=True)
    )


def _coerce_bloom(value) -> str:
    v = str(value or "").strip().lower()
    return v if v in BLOOM_LEVELS else "understand"


def _coerce_knowledge_type(value) -> str:
    v = str(value or "").strip().lower()
    return v if v in KNOWLEDGE_TYPES else "conceptual"


def _coerce_dok(value) -> int:
    try:
        dok = int(value)
    except (TypeError, ValueError):
        return 1
    return dok if 1 <= dok <= 4 else 1


def _resolve_provenance(chunk_id: str, blocks: list[dict]) -> dict:
    by_id = {b["chunk_id"]: b for b in blocks}
    block = by_id.get(chunk_id)
    if block is None and blocks:
        block = blocks[0]
    if block is None:
        return {"chunk_id": "c001", "page": 0, "span": [0, 0]}
    return {
        "chunk_id": block["chunk_id"],
        "page": block["page"],
        "span": [block["span"][0], block["span"][1]],
    }


def _rule_items(kg: dict, blocks: list[dict]) -> tuple[list[dict], list[dict]]:
    items: list[dict] = []
    for ent in sorted(kg.get("entities", []), key=lambda e: e["id"]):
        label = ent["label"]
        chunk_id = (ent.get("chunk_ids") or ["c001"])[0]
        items.append(
            {
                "id": ent["id"],
                "label": label,
                "description": (
                    f"State the definition of {label} and explain its role."
                ),
                "bloom": "remember" if ent.get("type") == "factual" else "understand",
                "knowledge_type": (
                    "factual" if ent.get("type") == "factual" else "conceptual"
                ),
                "dok": 1,
                "assessment_criteria": f"Learner can define {label} in their own words.",
                "required_competences": [],
                "tags": [str(ent.get("type", "concept"))],
                "provenance": _resolve_provenance(chunk_id, blocks),
            }
        )
    return items, []


def _normalize_llm_items(
    payload: dict, kg: dict, blocks: list[dict]
) -> tuple[list[dict], list[dict]]:
    raw_items = payload.get("items") or []
    labels = [str(i.get("label", "")).strip() for i in raw_items]
    ids = _unique_ids(
        [str(i.get("id", "")).strip() or slugify(lb) or "item" for i, lb in zip(raw_items, labels)]
    )
    items: list[dict] = []
    for raw, label, iid in zip(raw_items, labels, ids):
        if not label:
            continue
        prov = raw.get("provenance") or {}
        chunk_id = str(prov.get("chunk_id", "") or "c001")
        item = {
            "id": iid,
            "label": label,
            "description": str(raw.get("description", "")),
            "bloom": _coerce_bloom(raw.get("bloom")),
            "knowledge_type": _coerce_knowledge_type(raw.get("knowledge_type")),
            "dok": _coerce_dok(raw.get("dok")),
            "assessment_criteria": str(raw.get("assessment_criteria", "")),
            "required_competences": [str(c) for c in (raw.get("required_competences") or [])],
            "tags": [str(t) for t in (raw.get("tags") or [])],
            "provenance": _resolve_provenance(chunk_id, blocks),
        }
        if isinstance(raw.get("atomicity"), dict):
            item["atomicity"] = {
                k: bool(raw["atomicity"].get(k, True))
                for k in ("atomic", "assessable", "meaningful")
            }
        items.append(item)

    competences: list[dict] = []
    seen: set[str] = set()
    for comp in payload.get("competences") or []:
        label = str(comp.get("label", "")).strip()
        if not label:
            continue
        cid = slugify(label)
        if cid in seen:
            continue
        seen.add(cid)
        competences.append(
            {
                "id": cid,
                "label": label,
                "type": str(comp.get("type", "cognitive") or "cognitive"),
            }
        )
    competences.sort(key=lambda c: c["id"])
    return items, competences


def items_from_kg(
    kg: dict,
    llm=None,
    budget: int | None = None,
    max_items: int = 300,
    blocks: list[dict] | None = None,
) -> dict:
    """Build gated items + competences from a KG (LLM path or rule path)."""
    blocks = blocks or []
    candidates: list[dict]
    competences: list[dict]
    if llm is not None:
        reply = llm.complete(ROLE_ANALYZE, _itemize_prompt(kg), budget)
        try:
            payload = json.loads(reply["text"])
            if isinstance(payload, dict):
                candidates, competences = _normalize_llm_items(payload, kg, blocks)
            else:
                raise ValueError("non-dict payload")
        except (json.JSONDecodeError, TypeError, ValueError, AttributeError):
            candidates, competences = _rule_items(kg, blocks)
    else:
        candidates, competences = _rule_items(kg, blocks)

    accepted: list[dict] = []
    log: list[dict] = []
    for cand in candidates:
        ok, reason = atomicity_gate(cand)
        if ok:
            accepted.append(cand)
            log.append({"id": cand["id"], "decision": "accepted", "reason": reason})
            continue
        children = [c for c in try_split(cand) if atomicity_gate(c)[0]]
        if children:
            accepted.extend(children)
            log.append(
                {
                    "id": cand["id"],
                    "decision": "split",
                    "reason": reason,
                    "children": [c["id"] for c in children],
                }
            )
        else:
            log.append({"id": cand["id"], "decision": "dropped", "reason": reason})

    accepted.sort(key=lambda i: i["id"])
    if len(accepted) > max_items:
        dropped_extra = accepted[max_items:]
        accepted = accepted[:max_items]
        for extra in dropped_extra:
            log.append(
                {
                    "id": extra["id"],
                    "decision": "dropped",
                    "reason": f"over max_items={max_items}",
                }
            )
    log.sort(key=lambda e: e["id"])
    return {"items": accepted, "competences": competences, "log": log}
