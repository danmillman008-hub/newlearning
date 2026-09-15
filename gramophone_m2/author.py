"""Authoring for M2: v1 knowledge graph -> beat-graph draft.

``author_beats(v1, llm=None, budget=None)`` works per tag-cluster
(cluster key = first sorted tag; clusters in sorted-key order):

- With an LLM: one STORY call per cluster drafts ``{beats, checks}`` JSON.
  Drafts are validated against v1 and repaired: beats/checks citing
  unknown items are dropped, dangling choice targets are pruned, duplicate
  ids keep their first occurrence — every prune is counted in the report.
- Budget exhaustion mid-run STOPS authoring (fewer beats, never wrong).
- Without an LLM (``llm=None``) or when the STORY role is missing, a
  deterministic rule fallback builds one quest chain per cluster (one beat
  per item in topo order, checks synthesized from assessment_criteria).

Provenance ({item_id, chunk_id}) and difficulty always come from v1 truth,
never from the draft. Returns ``(beats_data, info)``.
"""

from __future__ import annotations

import json

ROLE_STORY = "STORY"

REQUIRED_ITEM_KEYS = (
    "id",
    "label",
    "description",
    "dok",
    "tags",
    "assessment_criteria",
)


def cluster_items(items: list[dict]) -> list[tuple[str, list[dict]]]:
    """Group items by first sorted tag; deterministic cluster/item order."""
    clusters: dict[str, list[dict]] = {}
    for item in items:
        tags = sorted(item.get("tags", [])) or ["general"]
        clusters.setdefault(tags[0], []).append(item)
    return [
        (key, sorted(cluster, key=lambda i: i["id"]))
        for key, cluster in sorted(clusters.items())
    ]


def build_story_prompt(cluster_key: str, items: list[dict], edges: list) -> str:
    """Prompt text for one STORY call (structure documented for cassettes)."""
    lines = [
        f"Quest chain {cluster_key!r}: draft BEATS as JSON "
        '{"beats": [...], "checks": [...]}.',
        "Beat: {id, title, text, choices[{label, to}], requires[item-ids], "
        "teaches[item-ids], checks[check-ids]}. "
        "Check: {id, kind, prompt, payload, item_id, max_score}.",
        "Cite only these item ids; choices may only target beat ids you emit.",
        "Items:",
    ]
    for item in items:
        lines.append(
            f"- {item['id']}: {item['label']} (dok {item['dok']}): "
            f"{item['description']} Check-worthy: {item['assessment_criteria']}"
        )
    if edges:
        lines.append("Prerequisites (prereq -> item):")
        lines.extend(f"- {a} -> {b}" for a, b in edges)
    return "\n".join(lines)


def parse_story_draft(text: str) -> tuple[list[dict], list[dict]]:
    """Parse one STORY draft into (beats, checks). Raises ValueError."""
    raw = text.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"STORY draft is not JSON: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("STORY draft must be a JSON object")
    beats = data.get("beats", [])
    checks = data.get("checks", [])
    if not isinstance(beats, list) or not isinstance(checks, list):
        raise ValueError("STORY draft needs 'beats' and 'checks' lists")
    return beats, checks


def check_v1_items(v1: dict) -> list[dict]:
    """Validate the v1 items block; return items. Raises ValueError."""
    items = v1.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("v1 graph has no items")
    for item in items:
        for key in REQUIRED_ITEM_KEYS:
            if key not in item:
                raise ValueError(f"v1 item {item.get('id', '?')!r}: missing {key!r}")
        if not item.get("provenance", {}).get("chunk_id"):
            raise ValueError(f"v1 item {item['id']!r}: missing provenance.chunk_id")
    return items


def author_beats(v1: dict, llm=None, budget: int | None = None) -> tuple[dict, dict]:
    """Draft the beat graph from v1. Returns (beats_data, info dict)."""
    from gramophone_m1.llm_client import BudgetExhausted, CassetteExhausted

    items = check_v1_items(v1)
    by_id = {i["id"]: i for i in items}
    edges = [tuple(e) for e in v1.get("surmise", []) if len(e) == 2]
    clusters = cluster_items(items)

    beats: list[dict] = []
    checks: list[dict] = []
    info: dict = {
        "tokens": 0,
        "clusters": len(clusters),
        "clusters_story": 0,
        "clusters_fallback": 0,
        "stopped_on_budget": False,
        "pruned": {
            "beats_unknown_item": 0,
            "checks_unknown_item": 0,
            "dangling_choices": 0,
            "unknown_check_refs": 0,
            "duplicate_ids": 0,
        },
    }

    story_missing = False
    for key, cluster in clusters:
        if llm is None or story_missing:
            beats_c, checks_c = _fallback_chain(key, cluster, edges, by_id)
            info["clusters_fallback"] += 1
        else:
            prompt = build_story_prompt(key, cluster, _cluster_edges(cluster, edges))
            try:
                rsp = llm.complete(ROLE_STORY, prompt, budget)
            except BudgetExhausted:
                info["stopped_on_budget"] = True
                break
            except (CassetteExhausted, RuntimeError):
                story_missing = True
                beats_c, checks_c = _fallback_chain(key, cluster, edges, by_id)
                info["clusters_fallback"] += 1
            else:
                info["tokens"] = llm.total_tokens
                try:
                    draft_beats, draft_checks = parse_story_draft(rsp["text"])
                except ValueError:
                    beats_c, checks_c = _fallback_chain(key, cluster, edges, by_id)
                    info["clusters_fallback"] += 1
                else:
                    beats_c, checks_c = _ground_draft(
                        draft_beats, draft_checks, by_id, info["pruned"]
                    )
                    info["clusters_story"] += 1
        beats.extend(beats_c)
        checks.extend(checks_c)

    beats, checks = _prune_dangling(beats, checks, info["pruned"])
    data = {
        "beats": beats,
        "checks": checks,
        "metadata": {
            "source": v1.get("metadata", {}).get("chapter", "v1"),
            "clusters": info["clusters"],
            "via_story": info["clusters_story"],
            "via_fallback": info["clusters_fallback"],
        },
    }
    return data, info


def _cluster_edges(cluster: list[dict], edges: list[tuple]) -> list[tuple]:
    ids = {i["id"] for i in cluster}
    return sorted(e for e in edges if e[0] in ids and e[1] in ids)


def _topo_order(cluster: list[dict], edges: list[tuple]) -> list[dict]:
    ids = [i["id"] for i in cluster]
    prereqs: dict[str, set[str]] = {i: set() for i in ids}
    for a, b in _cluster_edges(cluster, edges):
        prereqs[b].add(a)
    ordered, remaining = [], sorted(ids)
    while remaining:
        ready = sorted(i for i in remaining if prereqs[i] <= set(ordered))
        if not ready:  # cycle: break deterministically by id order
            ready = [remaining[0]]
        nxt = ready[0]
        ordered.append(nxt)
        remaining.remove(nxt)
    by_id = {i["id"]: i for i in cluster}
    return [by_id[i] for i in ordered]


def _fallback_chain(
    key: str, cluster: list[dict], edges: list[tuple], by_id: dict
) -> tuple[list[dict], list[dict]]:
    """Rule fallback: one linear quest chain for the cluster."""
    ordered = _topo_order(cluster, edges)
    labels = sorted(by_id[i]["label"] for i in by_id)
    beats, checks = [], []
    for n, item in enumerate(ordered):
        beat_id = f"{item['id']}-beat"
        check_id = f"{item['id']}-check"
        options = [item["label"]] + [label for label in labels if label != item["label"]][:3]
        checks.append(
            {
                "id": check_id,
                "kind": "choice",
                "prompt": item["assessment_criteria"],
                "payload": {"options": options, "answer": item["label"]},
                "item_id": item["id"],
                "max_score": 1,
            }
        )
        choice = (
            [{"label": "Continue", "to": f"{ordered[n + 1]['id']}-beat"}]
            if n + 1 < len(ordered)
            else []
        )
        prereqs = sorted(a for a, b in edges if b == item["id"])
        beats.append(
            {
                "id": beat_id,
                "title": f"{key.title()} Quest: {item['label']}",
                "text": item["description"],
                "choices": choice,
                "requires": prereqs,
                "teaches": [item["id"]],
                "checks": [check_id],
                "difficulty": item["dok"],
                "provenance": {
                    "item_id": item["id"],
                    "chunk_id": item["provenance"]["chunk_id"],
                },
            }
        )
    return beats, checks


def _ground_draft(
    draft_beats: list, draft_checks: list, by_id: dict, pruned: dict
) -> tuple[list[dict], list[dict]]:
    """Validate a STORY draft against v1 truth; provenance from v1, counted."""
    beats: list[dict] = []
    seen_beats: set[str] = set()
    for beat in draft_beats:
        if not isinstance(beat, dict) or "id" not in beat:
            continue
        if beat["id"] in seen_beats:
            pruned["duplicate_ids"] += 1
            continue
        seen_beats.add(beat["id"])
        teaches = [i for i in beat.get("teaches", []) if i in by_id]
        prov = beat.get("provenance", {}) if isinstance(beat.get("provenance"), dict) else {}
        anchor = prov.get("item_id") if prov.get("item_id") in by_id else None
        if anchor is None:
            anchor = teaches[0] if teaches else None
        if anchor is None:
            pruned["beats_unknown_item"] += 1
            continue
        truth = by_id[anchor]
        beats.append(
            {
                "id": beat["id"],
                "title": str(beat.get("title", truth["label"])),
                "text": str(beat.get("text", truth["description"])),
                "choices": [
                    {"label": str(c.get("label", "Continue")), "to": c.get("to")}
                    for c in beat.get("choices", [])
                    if isinstance(c, dict)
                ],
                "requires": [i for i in beat.get("requires", []) if i in by_id],
                "teaches": teaches,
                "checks": list(beat.get("checks", [])),
                "difficulty": truth["dok"],
                "provenance": {
                    "item_id": anchor,
                    "chunk_id": truth["provenance"]["chunk_id"],
                },
            }
        )
    checks: list[dict] = []
    seen_checks: set[str] = set()
    for check in draft_checks:
        if not isinstance(check, dict) or "id" not in check:
            continue
        if check["id"] in seen_checks:
            pruned["duplicate_ids"] += 1
            continue
        seen_checks.add(check["id"])
        if check.get("item_id") not in by_id:
            pruned["checks_unknown_item"] += 1
            continue
        checks.append(
            {
                "id": check["id"],
                "kind": str(check.get("kind", "choice")),
                "prompt": str(check.get("prompt", "")),
                "payload": check.get("payload", {}),
                "item_id": check["item_id"],
                "max_score": int(check.get("max_score", 1)),
            }
        )
    return beats, checks


def _prune_dangling(
    beats: list[dict], checks: list[dict], pruned: dict
) -> tuple[list[dict], list[dict]]:
    """Drop dangling choice targets + unknown check refs (counted)."""
    beat_ids = {b["id"] for b in beats}
    check_ids = {c["id"] for c in checks}
    for beat in beats:
        kept = []
        for choice in beat["choices"]:
            if choice.get("to") in beat_ids:
                kept.append(choice)
            else:
                pruned["dangling_choices"] += 1
        beat["choices"] = kept
        refs = []
        for ref in beat["checks"]:
            if ref in check_ids:
                refs.append(ref)
            else:
                pruned["unknown_check_refs"] += 1
        beat["checks"] = refs
    return beats, checks
