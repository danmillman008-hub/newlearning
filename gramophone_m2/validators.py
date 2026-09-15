"""Local deterministic validators for M2 checks (no LLM needed).

``grade(check, response)`` returns ``{"score", "max_score", "success"}``.

Kinds:
- choice: ``payload`` {options[], answer}; exact label match, all-or-nothing.
- ordering: ``payload`` {items[], answer[]}; partial credit from the
  normalized Kendall-tau distance: ``frac = 1 - 2*inversions/(n*(n-1))``
  floored at 0; success requires a perfect ordering.
- numeric: ``payload`` {answer, tolerance}; success iff
  ``abs(response - answer) <= tolerance`` (default relative 1e-6
  when tolerance is None).
"""

from __future__ import annotations

from collections import deque

CHOICE = "choice"
ORDERING = "ordering"
NUMERIC = "numeric"
KNOWN_KINDS = (CHOICE, ORDERING, NUMERIC)


def grade(check: dict, response) -> dict:
    """Grade one attempt. Raises ValueError on unknown check kinds."""
    kind = check.get("kind")
    max_score = check.get("max_score", 1)
    payload = check.get("payload", {})
    if kind == CHOICE:
        success = response == payload.get("answer")
        score = max_score if success else 0
    elif kind == ORDERING:
        frac = _ordering_fraction(payload.get("answer", []), response)
        success = frac >= 0.999
        score = round(max_score * frac, 4)
    elif kind == NUMERIC:
        answer = float(payload.get("answer", 0.0))
        tolerance = payload.get("tolerance")
        if tolerance is None:
            tolerance = abs(answer) * 1e-6 or 1e-9
        success = abs(float(response) - answer) <= tolerance
        score = max_score if success else 0
    else:
        raise ValueError(f"unknown check kind: {kind!r}")
    return {"score": score, "max_score": max_score, "success": bool(success)}


def _ordering_fraction(answer: list, response) -> float:
    """Similarity of two orderings in [0, 1] (1 == identical)."""
    if not isinstance(response, list) or sorted(map(str, response)) != sorted(
        map(str, answer)
    ):
        return 0.0
    n = len(answer)
    if n < 2:
        return 1.0
    # Occurrence queues: duplicates map to answer indices in order, so ties
    # get stable ranks instead of collapsing onto one index.
    queues: dict[str, deque] = {}
    for i, v in enumerate(answer):
        queues.setdefault(str(v), deque()).append(i)
    order = [queues[str(v)].popleft() for v in response]
    inversions = 0
    for i in range(n):
        for j in range(i + 1, n):
            if order[i] > order[j]:
                inversions += 1
    return max(0.0, 1.0 - 2.0 * inversions / (n * (n - 1)))
