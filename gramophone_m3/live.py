"""Live play for M3: beat graph + attempt stream -> M2-shaped session.

``play_session(beats_data, attempts, ...)`` grades a bound attempt list
(scripted or parsed stdin lines) reusing M2's validators/adapt/srs/xapi —
no duplicated learning logic. Retry rule: consecutive same-check attempts
after a fail are retries, capped at 1 + max_retries per run; further
repeats are SKIPPED (recorded, no step, no xAPI). Returns (session, state);
session matches M2's shape plus "skipped" and "retries_used".
``save_state``/``load_state`` roundtrip resume state byte-identically.
"""

from __future__ import annotations

import json

from gramophone_m2 import adapt, srs, validators, xapi
from gramophone_m2.pipeline import XP_PER_POINT

STATE_KEYS = (
    "mastery",
    "srs",
    "visited",
    "xp",
    "streak",
    "streak_max",
    "step",
    "flow_results",
    "attempts",
    "passed",
    "run",
)


def parse_attempt_line(line: str) -> dict:
    """Parse one 'beat|check|response' line (response: JSON or raw string)."""
    parts = line.split("|", 2)  # responses may themselves contain pipes
    if len(parts) != 3 or not parts[0].strip() or not parts[1].strip():
        raise ValueError(f"bad attempt line (want beat|check|response): {line!r}")
    raw = parts[2].strip()
    try:
        response = json.loads(raw)
    except json.JSONDecodeError:
        response = raw
    return {"beat_id": parts[0].strip(), "check_id": parts[1].strip(), "response": response}


def save_state(state: dict, path: str) -> None:
    """Write resume state (sorted keys: byte-identical roundtrips)."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1, sort_keys=True)
        f.write("\n")


def load_state(path: str) -> dict:
    """Load resume state. Missing file / bad shape raises ValueError."""
    try:
        with open(path, encoding="utf-8") as f:
            state = json.load(f)
    except FileNotFoundError:
        raise ValueError(f"state not found: {path}") from None
    except json.JSONDecodeError as e:
        raise ValueError(f"state is not JSON: {e}") from e
    if not isinstance(state, dict):
        raise ValueError("state must be a JSON object")
    missing = [k for k in STATE_KEYS if k not in state]
    if missing:
        raise ValueError(f"state missing keys: {missing}")
    run = state["run"]
    key = run.get("key") if isinstance(run, dict) else None
    key_ok = key is None or (
        isinstance(key, list)
        and len(key) == 2
        and all(isinstance(k, str) for k in key)
    )
    len_ok = (
        isinstance(run, dict)
        and not isinstance(run.get("len"), bool)
        and isinstance(run.get("len"), int)
        and run["len"] >= 0
    )
    if not (isinstance(run, dict) and key_ok and len_ok and isinstance(run.get("first_fail"), bool)):
        raise ValueError("state has a bad run block")
    return state


def play_session(
    beats_data: dict,
    attempts: list[dict],
    actor: str = "learner",
    max_retries: int = 1,
    restore: dict | None = None,
    store=None,
) -> tuple[dict, dict]:
    """Play attempts over beats. Returns (session, end_state).

    beats_data must already be validated (pipeline does this). store is an
    optional gramophone_m2.xapi.XAPIStore (statements counted regardless).
    """
    if isinstance(max_retries, bool) or not isinstance(max_retries, int) or max_retries < 0:
        raise ValueError(f"play: max_retries must be an int >= 0, got {max_retries!r}")
    by_beat = {b["id"]: b for b in beats_data["beats"]}
    by_check = {c["id"]: c for c in beats_data["checks"]}

    sched = srs.DSR()
    flow = adapt.FlowTracker()
    flow_results: list[bool] = []
    if restore is None:
        mastery: dict[str, float] = {}
        visited: list[str] = []
        xp = streak = streak_max = step = prior_attempts = prior_passed = 0
    else:
        mastery = dict(restore["mastery"])
        sched.stability = dict(restore["srs"]["stability"])
        sched.last_review = {k: int(v) for k, v in restore["srs"]["last_review"].items()}
        visited = list(restore["visited"])
        xp = restore["xp"]
        streak = restore["streak"]
        streak_max = restore["streak_max"]
        step = restore["step"]
        prior_attempts = restore["attempts"]
        prior_passed = restore["passed"]
        saved_run = restore["run"]
        run_key = tuple(saved_run["key"]) if saved_run["key"] else None
        run_len = saved_run["len"]
        run_first_fail = saved_run["first_fail"]
        for result in restore["flow_results"]:
            flow.update(bool(result))
            flow_results.append(bool(result))

    stmts = store.count if store is not None else 0

    def emit(verb, obj, result=None):
        nonlocal stmts
        if store is not None:
            store.append(actor, verb, obj, result, timestamp=step)
        stmts += 1

    graded = 0
    passed = 0
    skipped: list[int] = []
    retries_used = 0
    if restore is None:
        run_key: tuple | None = None
        run_len = 0
        run_first_fail = False

    for idx, attempt in enumerate(attempts):
        if not isinstance(attempt, dict):
            raise ValueError(f"play attempt {idx}: not an object")
        beat = by_beat.get(attempt.get("beat_id"))
        check = by_check.get(attempt.get("check_id"))
        if beat is None or check is None:
            raise ValueError(f"play attempt {idx}: unknown beat/check")
        if check["id"] not in beat.get("checks", []):
            raise ValueError(
                f"play attempt {idx}: check {check['id']} not on beat {beat['id']}"
            )
        key = (beat["id"], check["id"])
        if key == run_key:
            run_len += 1
        else:
            run_key, run_len = key, 1
        is_retry = run_len > 1 and run_first_fail
        if is_retry and run_len - 1 > max_retries:
            skipped.append(idx)
            continue

        if beat["id"] not in visited:
            visited.append(beat["id"])
            emit(xapi.EXPERIENCED, beat["id"])
        result = validators.grade(check, attempt.get("response"))
        ok = result["success"]
        emit(xapi.ATTEMPTED, check["id"], {"score": result["score"], "success": ok})
        emit(
            xapi.PASSED if ok else xapi.FAILED,
            check["id"],
            {"score": result["score"], "success": ok},
        )
        item = check["item_id"]
        was = adapt.is_mastered(mastery.get(item, adapt.DEFAULT_BKT["p_init"]))
        mastery[item] = adapt.bkt_update(mastery.get(item, adapt.DEFAULT_BKT["p_init"]), ok)
        if not was and adapt.is_mastered(mastery[item]):
            emit(xapi.MASTERED, item, {"p": mastery[item]})
        frac = result["score"] / result["max_score"] if result["max_score"] else 0.0
        sched.review(item, frac, step)
        flow.update(ok)
        flow_results.append(ok)
        if run_len == 1:
            run_first_fail = not ok
        if is_retry:
            retries_used += 1
        if ok:
            passed += 1
            streak += 1
            streak_max = max(streak_max, streak)
        else:
            streak = 0
        xp += int(round(result["score"] * XP_PER_POINT))
        graded += 1
        step += 1

    session = {
        "beats_visited": visited,
        "attempts": prior_attempts + graded,
        "passed": prior_passed + passed,
        "xp": xp,
        "level": 1 + xp // 100,
        "streak_max": streak_max,
        "mastery": {k: round(v, 6) for k, v in sorted(mastery.items())},
        "flow_in_band_ratio": round(flow.ratio(), 4),
        "xapi_statements": store.count if store is not None else stmts,
        "skipped": skipped,
        "retries_used": retries_used,
    }
    state = {
        "mastery": mastery,
        "srs": {"stability": sched.stability, "last_review": sched.last_review},
        "visited": visited,
        "xp": xp,
        "streak": streak,
        "streak_max": streak_max,
        "step": step,
        "flow_results": flow_results,
        "attempts": prior_attempts + graded,
        "passed": prior_passed + passed,
        "run": {
            "key": list(run_key) if run_key else None,
            "len": run_len,
            "first_fail": run_first_fail,
        },
    }
    return session, state
