"""Minimal xAPI telemetry for M2: append-only JSONL store + export.

Statements are {actor, verb, object, result, timestamp} with a logical
step timestamp (default: the statement index, so sessions stay
byte-deterministic). Verbs: attempted/passed/failed/experienced/mastered.
"""

from __future__ import annotations

import json
import os

ATTEMPTED = "attempted"
PASSED = "passed"
FAILED = "failed"
EXPERIENCED = "experienced"
MASTERED = "mastered"


class XAPIStore:
    """Append-only JSONL statement store."""

    def __init__(self, path: str):
        self.path = path
        self.count = 0
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.count = sum(1 for line in f if line.strip())

    def append(
        self,
        actor: str,
        verb: str,
        obj: str,
        result: dict | None = None,
        timestamp: int | None = None,
    ) -> dict:
        """Append one statement; return it."""
        stmt = {
            "actor": actor,
            "verb": verb,
            "object": obj,
            "result": result or {},
            "timestamp": self.count if timestamp is None else timestamp,
        }
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(stmt, sort_keys=True) + "\n")
        self.count += 1
        return stmt


def export_xapi(store_path: str, out_path: str) -> int:
    """Validate every statement line and copy the store. Return count."""
    if not os.path.exists(store_path):
        raise ValueError(f"xAPI store not found: {store_path}")
    n = 0
    with open(store_path, encoding="utf-8") as f:
        lines = [line for line in f if line.strip()]
    for i, line in enumerate(lines):
        try:
            stmt = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"xAPI store line {i}: bad JSON: {e}") from e
        for key in ("actor", "verb", "object"):
            if key not in stmt:
                raise ValueError(f"xAPI store line {i}: missing key {key!r}")
        n += 1
    with open(out_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    return n
