"""Beat-graph model for Gramophone M2: load, save, structural validation.

A beats document is a plain dict::

    {"beats": [beat...], "checks": [check...], "metadata": {...}}

beat: {id, title, text, choices[{label, to}], requires[item-ids],
       teaches[item-ids], checks[check-ids], difficulty,
       provenance{item_id, chunk_id}}
check: {id, kind, prompt, payload, item_id, max_score}

``validate()`` reports every structural issue (unknown ids, dangling
choice targets, duplicate ids, unreachable beats) and never drops anything.
"""

from __future__ import annotations

import json

REQUIRED_BEAT_KEYS = (
    "id",
    "title",
    "text",
    "choices",
    "requires",
    "teaches",
    "checks",
    "provenance",
)
REQUIRED_CHECK_KEYS = ("id", "kind", "prompt", "payload", "item_id", "max_score")


def load_beats(path: str) -> dict:
    """Load a beats JSON document. Raises on missing file / bad JSON / shape."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or not isinstance(data.get("beats"), list):
        raise ValueError(f"bad beats document (need {{beats:[...]}}): {path}")
    data.setdefault("checks", [])
    data.setdefault("metadata", {})
    if not isinstance(data["checks"], list):
        raise ValueError(f"bad beats document ('checks' must be a list): {path}")
    return data


def save_beats(data: dict, path: str) -> None:
    """Write a beats JSON document (sorted keys, stable formatting)."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, sort_keys=True)
        f.write("\n")


def validate(data: dict) -> list[str]:
    """Return a list of structural issue strings (empty == valid)."""
    issues: list[str] = []
    beats = data.get("beats", [])
    checks = data.get("checks", [])

    beat_ids: set[str] = set()
    for i, beat in enumerate(beats):
        where = f"beats[{i}]"
        if not isinstance(beat, dict):
            issues.append(f"{where}: not an object")
            continue
        for key in REQUIRED_BEAT_KEYS:
            if key not in beat:
                issues.append(f"{where}: missing key {key!r}")
        bid = beat.get("id")
        if bid in beat_ids:
            issues.append(f"{where}: duplicate beat id {bid!r}")
        if isinstance(bid, str):
            beat_ids.add(bid)

    check_ids: set[str] = set()
    for i, check in enumerate(checks):
        where = f"checks[{i}]"
        if not isinstance(check, dict):
            issues.append(f"{where}: not an object")
            continue
        for key in REQUIRED_CHECK_KEYS:
            if key not in check:
                issues.append(f"{where}: missing key {key!r}")
        cid = check.get("id")
        if cid in check_ids:
            issues.append(f"{where}: duplicate check id {cid!r}")
        if isinstance(cid, str):
            check_ids.add(cid)

    targets: set[str] = set()
    for beat in beats:
        if not isinstance(beat, dict):
            continue
        bid = beat.get("id", "?")
        choices = beat.get("choices", [])
        if not isinstance(choices, list):
            issues.append(f"beat {bid!r}: 'choices' must be a list")
            continue
        for choice in choices:
            if not isinstance(choice, dict) or "to" not in choice:
                issues.append(f"beat {bid!r}: malformed choice {choice!r}")
                continue
            if choice["to"] not in beat_ids:
                issues.append(f"beat {bid!r}: dangling choice target {choice['to']!r}")
            elif isinstance(choice["to"], str):
                targets.add(choice["to"])
        refs = beat.get("checks", [])
        if not isinstance(refs, list):
            issues.append(f"beat {bid!r}: 'checks' must be a list")
            continue
        for ref in refs:
            if ref not in check_ids:
                issues.append(f"beat {bid!r}: unknown check ref {ref!r}")

    # Reachability: entries are beats no choice points to; anything outside
    # the closure from the entries is reported (never dropped).
    if beats and isinstance(beats[0], dict):
        entries = sorted(b for b in beat_ids if b not in targets)
        if not entries:
            issues.append("no entry beat: every beat is targeted by a choice (cycle?)")
        else:
            by_id = {b["id"]: b for b in beats if isinstance(b, dict) and "id" in b}
            seen = set(entries)
            stack = list(entries)
            while stack:
                current = stack.pop()
                edge = by_id.get(current, {})
                edge_choices = edge.get("choices", [])
                if not isinstance(edge_choices, list):
                    continue
                for choice in edge_choices:
                    dest = choice.get("to") if isinstance(choice, dict) else None
                    if isinstance(dest, str) and dest in by_id and dest not in seen:
                        seen.add(dest)
                        stack.append(dest)
            for bid in sorted(beat_ids - seen):
                issues.append(f"beat {bid!r}: unreachable from entries {entries}")
    return issues
