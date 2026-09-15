"""DSR-inspired scheduler for M2 (logical clock, fully deterministic).

Each item has a stability S (default 1.0); the review interval is S steps.
``due(item, now)`` is True for never-reviewed items or when
``now - last_review >= interval``. ``review(item, grade, now)`` updates S:
correct (grade >= 0.6) grows it by ``S *= (1 + grade)``; wrong shrinks it
to ``max(1, S * grade)``. The clock is a caller-supplied step counter —
no wall time anywhere.
"""

from __future__ import annotations

PASS_GRADE = 0.6


class DSR:
    """Per-item stability store with due/review scheduling."""

    def __init__(self):
        self.stability: dict[str, float] = {}
        self.last_review: dict[str, int] = {}

    def interval(self, item: str) -> int:
        return max(1, round(self.stability.get(item, 1.0)))

    def due(self, item: str, now: int) -> bool:
        if item not in self.last_review:
            return True
        return now - self.last_review[item] >= self.interval(item)

    def review(self, item: str, grade: float, now: int) -> float:
        """Record a graded review; return the new stability."""
        s = self.stability.get(item, 1.0)
        if grade >= PASS_GRADE:
            s = s * (1.0 + grade)
        else:
            s = max(1.0, s * grade)
        self.stability[item] = s
        self.last_review[item] = now
        return s
