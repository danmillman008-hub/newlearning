"""Adaptation for M2: BKT mastery, fringe-aware next-beat, flow control.

- BKT: ``bkt_update(p, correct, params)`` with standard params
  {p_init, p_learn, p_slip, p_guess}; ``is_mastered(p, thr=0.95)``.
- next_beat: ready beats (requires subset-of mastered-or-visited, unvisited),
  scored by fringe bonus + (1 - mastery of teaches) + flow adjustment;
  deterministic tie-break by beat id. Returns None when nothing is ready.
- FlowTracker: rolling success rate over the last ``window`` attempts;
  the 0.70-0.85 band steers next_beat toward harder/easier beats.
"""

from __future__ import annotations

DEFAULT_BKT = {"p_init": 0.0, "p_learn": 0.1, "p_slip": 0.1, "p_guess": 0.2}
MASTERED_THRESHOLD = 0.95
FLOW_LO = 0.70
FLOW_HI = 0.85


def bkt_update(p: float, correct: bool, params: dict | None = None) -> float:
    """One BKT step: learning transition then evidence update."""
    q = params or DEFAULT_BKT
    p_learn, p_slip, p_guess = q["p_learn"], q["p_slip"], q["p_guess"]
    p_known = p + (1.0 - p) * p_learn
    if correct:
        num = p_known * (1.0 - p_slip)
        den = num + (1.0 - p_known) * p_guess
    else:
        num = p_known * p_slip
        den = num + (1.0 - p_known) * (1.0 - p_guess)
    return num / den if den > 0 else p_known


def is_mastered(p: float, threshold: float = MASTERED_THRESHOLD) -> bool:
    """Mastery test (default threshold 0.95)."""
    return p >= threshold


class FlowTracker:
    """Rolling success rate + in-band history (deterministic, no clock)."""

    def __init__(self, window: int = 10, lo: float = FLOW_LO, hi: float = FLOW_HI):
        self.window = window
        self.lo = lo
        self.hi = hi
        self._results: list[bool] = []
        self._in_band_history: list[bool] = []

    def update(self, correct: bool) -> None:
        self._results.append(bool(correct))
        self._in_band_history.append(self.in_band())

    def rate(self) -> float:
        recent = self._results[-self.window :]
        if not recent:
            return 1.0
        return sum(1 for r in recent if r) / len(recent)

    def in_band(self) -> bool:
        return self.lo <= self.rate() <= self.hi

    def ratio(self) -> float:
        """Fraction of recorded steps whose rolling rate was in-band."""
        if not self._in_band_history:
            return 1.0
        return sum(1 for b in self._in_band_history if b) / len(
            self._in_band_history
        )


def next_beat(
    beats: list[dict],
    visited: set[str],
    mastery: dict[str, float],
    fringe: set[str],
    flow: FlowTracker | None = None,
    mastered_thr: float = MASTERED_THRESHOLD,
) -> dict | None:
    """Pick the next beat (None when nothing is ready). Deterministic."""
    mastered = {i for i, p in mastery.items() if p >= mastered_thr}
    taught_by_visited: set[str] = set()
    by_id = {b["id"]: b for b in beats}
    for bid in visited:
        taught_by_visited.update(by_id.get(bid, {}).get("teaches", []))
    known = mastered | taught_by_visited

    rate = flow.rate() if flow else 1.0
    in_band = flow.in_band() if flow else True

    best: dict | None = None
    best_key: tuple | None = None
    for beat in sorted(beats, key=lambda b: b["id"]):
        if beat["id"] in visited:
            continue
        if any(r not in known for r in beat.get("requires", [])):
            continue
        teaches = beat.get("teaches", [])
        avg_mastery = (
            sum(mastery.get(i, 0.0) for i in teaches) / len(teaches)
            if teaches
            else 0.0
        )
        score = (2.0 if set(teaches) & fringe else 0.0) + (1.0 - avg_mastery)
        if not in_band:
            difficulty = float(beat.get("difficulty", 2))
            score += 0.25 * difficulty if rate > FLOW_HI else -0.25 * difficulty
        key = (round(score, 9),)  # ids already sorted: first max wins
        if best_key is None or key > best_key:
            best_key = key
            best = beat
    return best
