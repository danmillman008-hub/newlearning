"""KG stage: blocks -> entity-relation knowledge graph.

Output::

    {"entities": [{"id", "label", "type", "chunk_ids"}],
     "relations": [{"src", "rel", "dst", "chunk_ids"}]}

Two paths, both deterministic:

- LLM path (``llm`` given): one ROLE_EXTRACT call; the reply must be JSON
  ``{"entities": [...], "relations": [...]}``. Unknown chunk ids and relation
  endpoints are coerced to known ones (documented, deterministic).
- Regex fallback (``llm`` is None, budget exhausted upstream, or the reply is
  not valid JSON): capitalized-phrase term spotting plus same-chunk
  co-occurrence relations. Used by tests and by degraded runs.
"""

from __future__ import annotations

import json
import re

from .llm_client import ROLE_EXTRACT

_CAP_PHRASE = re.compile(r"\b[A-Z][A-Za-z0-9-]*(?:\s+[A-Z][A-Za-z0-9-]*){0,2}\b")

# Pure function words stripped/coerced by the regex fallback. Never concepts.
_STOPLIST = frozenset(
    """
    a an the this that these those it its it’s it´s in on at to for with from by
    as of and or but if when while where which who whom whose what how why not
    no we you they he she him her them his our their your my is are was were be
    been being do does did have has had will would can could should may might
    each every any all both few many much more most other some such than too
    very under within without because however although though since good small
    large new first second third one two three finally neither either also just
    only even still yet already often never always usually sometimes wider
    narrower higher lower larger smaller
    """.split()
)


def slugify(label: str) -> str:
    """Lowercase kebab-case id for a label (deterministic)."""
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    return slug or "item"


def _unique_ids(labels: list[str]) -> list[str]:
    """Deterministic dedupe: append -2, -3, ... on collision."""
    seen: dict[str, int] = {}
    out: list[str] = []
    for label in labels:
        base = slugify(label)
        n = seen.get(base, 0) + 1
        seen[base] = n
        out.append(base if n == 1 else f"{base}-{n}")
    return out


def _extract_prompt(blocks: list[dict]) -> str:
    compact = [
        {
            "chunk_id": b["chunk_id"],
            "page": b["page"],
            "span": b["span"],
            "text": b["text"],
        }
        for b in blocks
    ]
    return (
        "Extract the key concepts and their relations from these textbook blocks.\n"
        "Reply with JSON ONLY, exactly:\n"
        '{"entities": [{"label": str, "type": str, "chunk_ids": [str]}], '
        '"relations": [{"src": label, "rel": str, "dst": label, "chunk_ids": [str]}]}\n'
        "Use one of: concept, method, measure, person. chunk_ids must come from the blocks.\n"
        "BLOCKS:\n" + json.dumps(compact, sort_keys=True)
    )


def _normalize_llm_kg(payload: dict, blocks: list[dict]) -> dict:
    known_chunks = [b["chunk_id"] for b in blocks]
    known_set = set(known_chunks)
    fallback_chunk = known_chunks[0] if known_chunks else "c001"

    raw_entities = payload.get("entities") or []
    labels = [str(e.get("label", "")).strip() for e in raw_entities]
    ids = _unique_ids(labels)
    label_to_id: dict[str, str] = {}
    for label, eid in zip(labels, ids):  # first mention wins on duplicates
        if label and label.lower() not in label_to_id:
            label_to_id[label.lower()] = eid

    entities: list[dict] = []
    for ent, label, eid in zip(raw_entities, labels, ids):
        if not label:
            continue
        chunk_ids = sorted({c for c in (ent.get("chunk_ids") or []) if c in known_set})
        if not chunk_ids:
            chunk_ids = [fallback_chunk]
        etype = str(ent.get("type", "concept") or "concept").strip().lower() or "concept"
        entities.append(
            {"id": eid, "label": label, "type": etype, "chunk_ids": chunk_ids}
        )

    relations: list[dict] = []
    seen_rel: set[tuple] = set()
    for rel in payload.get("relations") or []:
        src = label_to_id.get(str(rel.get("src", "")).strip().lower(), "")
        dst = label_to_id.get(str(rel.get("dst", "")).strip().lower(), "")
        if not src or not dst or src == dst:
            continue
        chunk_ids = sorted({c for c in (rel.get("chunk_ids") or []) if c in known_set})
        if not chunk_ids:
            chunk_ids = [fallback_chunk]
        key = (src, str(rel.get("rel", "related_to")), dst)
        if key in seen_rel:
            continue
        seen_rel.add(key)
        relations.append(
            {"src": src, "rel": key[1], "dst": dst, "chunk_ids": chunk_ids}
        )
    relations.sort(key=lambda r: (r["src"], r["rel"], r["dst"]))
    return {"entities": entities, "relations": relations}


def _fallback_terms(text: str) -> list[str]:
    """Capitalized-phrase spotting with function-word stripping (deterministic)."""
    terms: list[str] = []
    for match in _CAP_PHRASE.finditer(text):
        words = match.group(0).split()
        while words and words[0].lower().strip("’'") in _STOPLIST:
            words.pop(0)
        while words and words[-1].lower().strip("’'") in _STOPLIST:
            words.pop()
        if not words:
            continue
        term = " ".join(words)
        if len(term) < 3:
            continue
        terms.append(term)
    return terms


def _fallback_kg(blocks: list[dict]) -> dict:
    per_chunk: dict[str, list[str]] = {}
    first_seen: dict[str, str] = {}
    chunks_of: dict[str, set[str]] = {}
    for block in blocks:
        cid = block["chunk_id"]
        labels: list[str] = []
        for term in _fallback_terms(block["text"]):
            key = term.lower()
            if key not in first_seen:
                first_seen[key] = term
            chunks_of.setdefault(key, set()).add(cid)
            labels.append(key)
        per_chunk[cid] = labels

    labels_sorted = sorted(first_seen, key=lambda k: first_seen[k].lower())
    ids = _unique_ids([first_seen[k] for k in labels_sorted])
    key_to_id = dict(zip(labels_sorted, ids))
    entities = [
        {
            "id": key_to_id[k],
            "label": first_seen[k],
            "type": "concept",
            "chunk_ids": sorted(chunks_of[k]),
        }
        for k in labels_sorted
    ]

    rel_chunks: dict[tuple, set[str]] = {}
    for cid, labels in per_chunk.items():
        ordered = sorted(set(labels), key=labels.index)
        for src_key, dst_key in zip(ordered, ordered[1:]):
            if src_key == dst_key:
                continue
            triple = (key_to_id[src_key], "related_to", key_to_id[dst_key])
            rel_chunks.setdefault(triple, set()).add(cid)
    relations = [
        {"src": s, "rel": r, "dst": d, "chunk_ids": sorted(c)}
        for (s, r, d), c in sorted(rel_chunks.items())
    ]
    return {"entities": entities, "relations": relations}


def extract_kg(
    blocks: list[dict],
    llm=None,
    budget: int | None = None,
) -> dict:
    """Extract the KG for blocks via LLM, with deterministic regex fallback."""
    if llm is not None:
        reply = llm.complete(ROLE_EXTRACT, _extract_prompt(blocks), budget)
        try:
            payload = json.loads(reply["text"])
            if isinstance(payload, dict):
                return _normalize_llm_kg(payload, blocks)
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass  # fall through to the deterministic fallback
    return _fallback_kg(blocks)
