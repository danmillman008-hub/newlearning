"""Merge for M3: chapter v1 graphs -> one namespaced book v1 graph.

``merge_graphs(v1_list, chapter_names)`` unions items as {chapter}:{id}
(chapters in input order, items sorted by id within), remaps surmise edges
and competence refs, and recomputes states + fringe via M1 spacing (same
overflow/partition fallback and {"": [...]} fringe_cache shape as M1).
Provenance gains a "chapter" key; relation-detail lists M1 leaves empty are
carried over unmapped (documented). Failures raise ValueError before
anything is written.
"""

from __future__ import annotations

from datetime import datetime, timezone

from gramophone_m1 import spacing


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def merge_graphs(v1_list: list[dict], chapter_names: list[str]) -> dict:
    """Merge chapter graphs into a book v1. Raises ValueError on bad input."""
    if not v1_list:
        raise ValueError("merge: need at least one chapter graph")
    if len(chapter_names) != len(v1_list):
        raise ValueError("merge: chapter names count must match graphs count")
    if len(set(chapter_names)) != len(chapter_names):
        raise ValueError("merge: duplicate chapter names")

    items: list[dict] = []
    competences: list[dict] = []
    edges: list[list[str]] = []
    surmise_relations: list = []
    competence_relations: list = []
    sources: list[str] = []
    changelogs: list[str] = []

    for name, v1 in zip(chapter_names, v1_list):
        ch_items = v1.get("items")
        ch_edges = v1.get("surmise")
        if not isinstance(v1, dict) or not isinstance(ch_items, list) or not isinstance(
            ch_edges, list
        ):
            raise ValueError(f"merge: chapter {name!r} is not a v1 graph")
        have: set[str] = set()
        for item in sorted(ch_items, key=lambda i: i.get("id", "")):
            if not isinstance(item, dict) or "id" not in item:
                raise ValueError(f"merge: chapter {name!r} has a bad item")
            new = dict(item)
            new["id"] = f"{name}:{item['id']}"
            prov = dict(item.get("provenance", {}))
            prov["chapter"] = name
            new["provenance"] = prov
            new["required_competences"] = [
                f"{name}:{c}" for c in item.get("required_competences", [])
            ]
            items.append(new)
            have.add(item["id"])
        for edge in ch_edges:
            if (
                not isinstance(edge, (list, tuple))
                or len(edge) != 2
                or edge[0] not in have
                or edge[1] not in have
            ):
                raise ValueError(f"merge: chapter {name!r} has a bad edge {edge!r}")
            edges.append([f"{name}:{edge[0]}", f"{name}:{edge[1]}"])
        for comp in v1.get("competences", []):
            if not isinstance(comp, dict) or "id" not in comp:
                raise ValueError(f"merge: chapter {name!r} has a bad competence")
            new_comp = dict(comp)
            new_comp["id"] = f"{name}:{comp['id']}"
            competences.append(new_comp)
        surmise_relations.extend(v1.get("surmise_relations", []))
        competence_relations.extend(v1.get("competence_relations", []))
        meta = v1.get("metadata", {})
        sources.extend(meta.get("provenance", {}).get("source_materials", []))
        changelogs.extend(meta.get("provenance", {}).get("change_log", []))

    edges = [list(e) for e in sorted({tuple(e) for e in edges})]
    ids = [i["id"] for i in items]
    enum = spacing.enumerate_states(ids, edges)
    overflow = bool(enum["overflow"])
    partitions = None
    if overflow:
        clusters = spacing.partition_by_tag(items, edges)
        partitions = {
            tag: spacing.enumerate_states(c["items"], c["edges"])["states"]
            for tag, c in sorted(clusters.items())
        }
        states: list = []
    else:
        states = enum["states"]
    fringe0 = spacing.fringe([], ids, edges)

    metadata = {
        "chapter": "+".join(chapter_names),
        "chapters": list(chapter_names),
        "version": "1",
        "generated_at": _utcnow(),
        "overflow": overflow,
        "degraded_stages": [],
        "provenance": {
            "source_materials": sources,
            "change_log": changelogs
            + [f"merged by gramophone-m3 merge: {', '.join(chapter_names)}"],
        },
    }
    if partitions is not None:
        metadata["partitions"] = partitions
    return {
        "metadata": metadata,
        "items": items,
        "competences": competences,
        "surmise_relations": surmise_relations,
        "competence_relations": competence_relations,
        "surmise": edges,
        "states": states,
        "fringe_cache": {"": fringe0},
    }
