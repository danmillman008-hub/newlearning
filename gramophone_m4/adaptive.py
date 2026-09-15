"""Adaptive quest loop for M4: policy over the reused M1/M2/M3 engines.

``run_quest(beats_data, v1_graph, responses, ...)`` picks beats with M2's
``adapt.next_beat`` over live outcomes (mastery from the running M3 state,
fringe recomputed via M1 spacing each pick), binds each picked beat's
checks to the response stream — pulling up to ``max_retries`` extra
responses per check on fails — and grades every attempt through M3's
``live.play_session`` with restore chaining (retry/skip/xapi/step/BKT/SRS
all inherited). Returns ``(session, state, transcript)``.

Completion reasons: quest_complete (all beats visited), gated (beats
remain but none ready), responses_exhausted, max_steps. Skipped is always
empty by construction (binding never exceeds the retry cap); the field is
kept for M2/M3 shape parity.
"""

from __future__ import annotations

from gramophone_m1 import spacing
from gramophone_m2 import adapt, validators, xapi
from gramophone_m3.live import play_session

QUEST_COMPLETE = "quest_complete"
GATED = "gated"
RESPONSES_EXHAUSTED = "responses_exhausted"
MAX_STEPS = "max_steps"


def _initial_state() -> dict:
    return {
        "mastery": {},
        "srs": {"stability": {}, "last_review": {}},
        "visited": [],
        "xp": 0,
        "streak": 0,
        "streak_max": 0,
        "step": 0,
        "flow_results": [],
        "attempts": 0,
        "passed": 0,
        "run": {"key": None, "len": 0, "first_fail": False},
    }


def _check_v1(v1_graph: dict) -> tuple[list[str], list[list[str]]]:
    if not isinstance(v1_graph, dict):
        raise ValueError("quest: graph must be a JSON object")
    items = v1_graph.get("items")
    edges = v1_graph.get("surmise")
    if not isinstance(items, list) or not isinstance(edges, list):
        raise ValueError("quest: graph needs items[] and surmise[]")
    ids = []
    for item in items:
        if not isinstance(item, dict) or "id" not in item:
            raise ValueError("quest: graph has a bad item")
        ids.append(item["id"])
    have = set(ids)
    clean = []
    for edge in edges:
        if (
            not isinstance(edge, (list, tuple))
            or len(edge) != 2
            or edge[0] not in have
            or edge[1] not in have
        ):
            raise ValueError(f"quest: graph has a bad edge {edge!r}")
        clean.append([edge[0], edge[1]])
    return ids, clean


def run_quest(
    beats_data: dict,
    v1_graph: dict,
    responses: list,
    actor: str = "learner",
    max_retries: int = 1,
    max_steps: int = 1000,
    restore: dict | None = None,
    store=None,
) -> tuple[dict, dict, list[dict]]:
    """Run an adaptive quest. Returns (session, end_state, transcript).

    Responses are positional: a save/resume split inside a check's retry
    window rebinds the leftover retry response to the next check, so save
    at retry-clean boundaries for an exact resume.
    """
    if isinstance(max_steps, bool) or not isinstance(max_steps, int) or max_steps < 1:
        raise ValueError(f"quest: max_steps must be an int >= 1, got {max_steps!r}")
    if isinstance(max_retries, bool) or not isinstance(max_retries, int) or max_retries < 0:
        raise ValueError(f"quest: max_retries must be an int >= 0, got {max_retries!r}")
    if not isinstance(responses, (list, tuple)):
        raise ValueError(
            "quest: responses must be a list, "
            f"got {type(responses).__name__}"
        )
    item_ids, edges = _check_v1(v1_graph)
    by_beat = {b["id"]: b for b in beats_data["beats"]}
    by_check = {c["id"]: c for c in beats_data["checks"]}

    state = restore if restore is not None else _initial_state()
    stream = list(responses)
    cursor = 0
    picks = state.get("quest_picks", 0)
    transcript: list[dict] = list(state.get("quest_transcript", []))
    skipped: list[int] = []
    retries_used = 0
    phantom = 0  # check-less experienced events when no store is passed
    last_session: dict | None = None
    reason = GATED

    def take():
        nonlocal cursor
        if cursor >= len(stream):
            return None, False
        resp = stream[cursor]
        cursor += 1
        return resp, True

    exhausted = False
    while True:
        if picks >= max_steps:
            reason = MAX_STEPS
            break
        mastery = state["mastery"]
        visited = set(state["visited"])
        mastered = {i for i, p in mastery.items() if p >= adapt.MASTERED_THRESHOLD}
        fringe = set(spacing.fringe(sorted(mastered), item_ids, edges))
        flow = adapt.FlowTracker()
        for result in state["flow_results"]:
            flow.update(bool(result))
        beat = adapt.next_beat(
            beats_data["beats"], visited, mastery, fringe, flow
        )
        if beat is None:
            reason = (
                QUEST_COMPLETE
                if len(visited) == len(beats_data["beats"])
                else GATED
            )
            break
        picks += 1
        if not beat.get("checks"):
            # Check-less beat: experienced + visited, no grading. (The M3
            # engine only visits through graded attempts, so policy-level
            # bookkeeping is the only honest way to visit these.)
            state["visited"].append(beat["id"])
            if store is not None:
                store.append(actor, xapi.EXPERIENCED, beat["id"],
                             timestamp=state["step"])
            else:
                phantom += 1
            continue
        for check_id in beat["checks"]:
            response, ok = take()
            if not ok:
                exhausted = True
                break
            fails = 0
            while True:
                attempt = {
                    "beat_id": beat["id"],
                    "check_id": check_id,
                    "response": response,
                }
                step_session, state = play_session(
                    beats_data, [attempt], actor, max_retries, state, store
                )
                last_session = step_session
                retries_used += step_session["retries_used"]
                if step_session["skipped"]:
                    skipped.append(len(transcript) + len(skipped))
                else:
                    grade = validators.grade(by_check[check_id], response)
                    transcript.append(
                        {
                            "beat": beat["id"],
                            "check": check_id,
                            "response": response,
                            "score": grade["score"],
                            "max_score": grade["max_score"],
                            "success": grade["success"],
                        }
                    )
                    if grade["success"]:
                        break
                    fails += 1
                    if fails > max_retries:
                        break
                    response, ok = take()
                    if not ok:
                        exhausted = True
                        break
                if exhausted:
                    break
            if exhausted:
                break
        if exhausted:
            reason = RESPONSES_EXHAUSTED
            # An exhausted pick that never resolved its beat is un-counted,
            # so resume continues the pick count instead of double-counting.
            if beat["id"] not in state["visited"]:
                picks -= 1
            break

    if last_session is None:
        flow = adapt.FlowTracker()
        for result in state["flow_results"]:
            flow.update(bool(result))
        session = {
            "beats_visited": list(state["visited"]),
            "attempts": state["attempts"],
            "passed": state["passed"],
            "xp": state["xp"],
            "level": 1 + state["xp"] // 100,
            "streak_max": state["streak_max"],
            "mastery": {k: round(v, 6) for k, v in sorted(state["mastery"].items())},
            "flow_in_band_ratio": round(flow.ratio(), 4),
            "xapi_statements": store.count if store is not None else 0,
            "skipped": [],
            "retries_used": 0,
        }
    else:
        session = dict(last_session)
        session["skipped"] = skipped
        session["retries_used"] = retries_used
        # Check-less beats emit after the last graded step: recount.
        session["xapi_statements"] = (
            store.count if store is not None
            else last_session["xapi_statements"] + phantom
        )
    session["transcript"] = transcript
    session["completion"] = {
        "reason": reason,
        "picks": picks,
        "visited": len(state["visited"]),
    }
    state["quest_transcript"] = transcript
    state["quest_picks"] = picks
    return session, state, transcript
