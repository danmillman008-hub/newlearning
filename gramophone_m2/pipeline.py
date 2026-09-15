"""M2 pipelines: author (v1 -> beats) and learn (beats + script -> session).

``run_author(graph_path, outdir, llm=None, budget=None)`` writes
``beats.json`` plus the author section of ``M2-REPORT.md`` and returns its
report dict. ``run_learn(beats_path, script_path, outdir)`` replays the
scripted attempts (grade -> BKT/SRS/flow -> xAPI), writes ``session.json``
and ``xapi.jsonl``, appends the session section to ``M2-REPORT.md``, and
returns the session dict. Same inputs + same cassette = byte-identical
outputs (logical step timestamps only, no wall time).
"""

from __future__ import annotations

import json
import os

from . import adapt, author, srs, story_model, validators, xapi

REPORT_NAME = "M2-REPORT.md"
XP_PER_POINT = 10


def run_author(
    graph_path: str, outdir: str, llm=None, budget: int | None = None
) -> dict:
    """Author beats from a v1 graph file. Bad input raises ValueError."""
    if not os.path.exists(graph_path):
        raise ValueError(f"graph not found: {graph_path}")
    with open(graph_path, encoding="utf-8") as f:
        try:
            v1 = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"graph is not JSON: {e}") from e
    if not isinstance(v1, dict):
        raise ValueError("graph must be a JSON object")
    data, info = author.author_beats(v1, llm=llm, budget=budget)
    issues = story_model.validate(data)
    if issues:
        raise RuntimeError(f"internal error: authored beats invalid: {issues}")
    os.makedirs(outdir, exist_ok=True)
    story_model.save_beats(data, os.path.join(outdir, "beats.json"))
    report = {
        "beats": len(data["beats"]),
        "checks": len(data["checks"]),
        "tokens": info["tokens"],
        "clusters": info["clusters"],
        "via_story": info["clusters_story"],
        "via_fallback": info["clusters_fallback"],
        "stopped_on_budget": info["stopped_on_budget"],
        "pruned": info["pruned"],
    }
    with open(os.path.join(outdir, REPORT_NAME), "w", encoding="utf-8") as f:
        f.write(_author_report(graph_path, report))
    return report


def run_learn(beats_path: str, script_path: str, outdir: str) -> dict:
    """Replay a scripted session. Bad input raises ValueError."""
    for path in (beats_path, script_path):
        if not os.path.exists(path):
            raise ValueError(f"input not found: {path}")
    data = story_model.load_beats(beats_path)
    issues = story_model.validate(data)
    if issues:
        raise ValueError(f"beats invalid: {issues}")
    with open(script_path, encoding="utf-8") as f:
        try:
            script = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"script is not JSON: {e}") from e
    attempts = script.get("attempts")
    if not isinstance(script, dict) or not isinstance(attempts, list):
        raise ValueError("script needs {actor, attempts:[...]}")

    actor = script.get("actor", "learner")
    by_beat = {b["id"]: b for b in data["beats"]}
    by_check = {c["id"]: c for c in data["checks"]}
    sched = srs.DSR()
    flow = adapt.FlowTracker()
    mastery: dict[str, float] = {}
    os.makedirs(outdir, exist_ok=True)
    store_path = os.path.join(outdir, "xapi.jsonl")
    if os.path.exists(store_path):
        os.remove(store_path)
    store = xapi.XAPIStore(store_path)

    visited: list[str] = []
    passed = 0
    xp = 0
    streak = 0
    streak_max = 0
    for step, attempt in enumerate(attempts):
        beat = by_beat.get(attempt.get("beat_id"))
        check = by_check.get(attempt.get("check_id"))
        if beat is None or check is None:
            raise ValueError(f"script attempt {step}: unknown beat/check")
        if check["id"] not in beat.get("checks", []):
            raise ValueError(
                f"script attempt {step}: check {check['id']} not on beat {beat['id']}"
            )
        if beat["id"] not in visited:
            visited.append(beat["id"])
            store.append(actor, xapi.EXPERIENCED, beat["id"], timestamp=step)
        result = validators.grade(check, attempt.get("response"))
        ok = result["success"]
        store.append(
            actor,
            xapi.ATTEMPTED,
            check["id"],
            {"score": result["score"], "success": ok},
            timestamp=step,
        )
        store.append(
            actor,
            xapi.PASSED if ok else xapi.FAILED,
            check["id"],
            {"score": result["score"], "success": ok},
            timestamp=step,
        )
        item = check["item_id"]
        was = adapt.is_mastered(mastery.get(item, adapt.DEFAULT_BKT["p_init"]))
        mastery[item] = adapt.bkt_update(
            mastery.get(item, adapt.DEFAULT_BKT["p_init"]), ok
        )
        if not was and adapt.is_mastered(mastery[item]):
            store.append(actor, xapi.MASTERED, item, {"p": mastery[item]}, timestamp=step)
        frac = result["score"] / result["max_score"] if result["max_score"] else 0.0
        sched.review(item, frac, step)
        flow.update(ok)
        if ok:
            passed += 1
            streak += 1
            streak_max = max(streak_max, streak)
        else:
            streak = 0
        xp += int(round(result["score"] * XP_PER_POINT))

    session = {
        "beats_visited": visited,
        "attempts": len(attempts),
        "passed": passed,
        "xp": xp,
        "level": 1 + xp // 100,
        "streak_max": streak_max,
        "mastery": {k: round(v, 6) for k, v in sorted(mastery.items())},
        "flow_in_band_ratio": round(flow.ratio(), 4),
        "xapi_statements": store.count,
    }
    with open(os.path.join(outdir, "session.json"), "w", encoding="utf-8") as f:
        json.dump(session, f, indent=1, sort_keys=True)
        f.write("\n")
    with open(os.path.join(outdir, REPORT_NAME), "a", encoding="utf-8") as f:
        f.write(_session_report(script_path, session))
    return session


def _author_report(graph_path: str, report: dict) -> str:
    pruned = " ".join(f"{k}={v}" for k, v in sorted(report["pruned"].items()))
    return (
        "# Gramophone M2 — Run Report\n\n"
        f"## Author\nsource={graph_path} BEATS={report['beats']} "
        f"CHECKS={report['checks']} TOKENS={report['tokens']} "
        f"CLUSTERS={report['clusters']} VIA_STORY={report['via_story']} "
        f"VIA_FALLBACK={report['via_fallback']} "
        f"STOPPED_ON_BUDGET={int(report['stopped_on_budget'])} PRUNED[{pruned}]\n"
    )


def _session_report(script_path: str, session: dict) -> str:
    return (
        f"\n## Learn\nscript={script_path} "
        f"VISITED={len(session['beats_visited'])} ATTEMPTS={session['attempts']} "
        f"PASSED={session['passed']} XP={session['xp']} LEVEL={session['level']} "
        f"STREAK_MAX={session['streak_max']} "
        f"FLOW_RATIO={session['flow_in_band_ratio']} "
        f"XAPI={session['xapi_statements']}\n"
    )
