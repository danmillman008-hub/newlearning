"""M4 pipeline: run_quest_file (beats + v1 + responses -> quest outputs).

Writes ``session.json`` + ``xapi.jsonl`` (fresh unless resume) + the quest
section of ``M4-REPORT.md``. Bad input raises ValueError before anything is
written; same inputs = byte-identical outputs.
"""

from __future__ import annotations

import json
import os

from gramophone_m2 import story_model, xapi
from gramophone_m3.live import load_state, save_state

from . import adaptive

REPORT_NAME = "M4-REPORT.md"


def parse_response_line(line: str):
    """Parse one bare response line (JSON literal or raw string)."""
    raw = line.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def run_quest_file(
    beats_path: str,
    graph_path: str,
    outdir: str,
    responses_path: str | None = None,
    response_lines: list[str] | None = None,
    save: str | None = None,
    resume: str | None = None,
    actor: str = "learner",
    max_retries: int = 1,
    max_steps: int = 1000,
) -> dict:
    """Run an adaptive quest from files. Bad input -> ValueError."""
    if not os.path.exists(beats_path):
        raise ValueError(f"quest: input not found: {beats_path}")
    if not os.path.exists(graph_path):
        raise ValueError(f"quest: input not found: {graph_path}")
    data = story_model.load_beats(beats_path)
    issues = story_model.validate(data)
    if issues:
        raise ValueError(f"quest: beats invalid: {issues}")
    with open(graph_path, encoding="utf-8") as f:
        try:
            v1 = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"quest: graph is not JSON: {e}") from e
    if responses_path is not None and response_lines is not None:
        raise ValueError("quest: --responses and stdin lines are exclusive")
    if responses_path is not None:
        if not os.path.exists(responses_path):
            raise ValueError(f"quest: responses not found: {responses_path}")
        with open(responses_path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    elif response_lines is not None:
        lines = response_lines
    else:
        raise ValueError("quest: no responses (need --responses or stdin lines)")
    responses = [parse_response_line(l) for l in lines if l.strip()]
    restore = None
    if resume is not None:
        restore = load_state(resume)
        # live.load_state keeps M3 keys only; re-attach M4 quest keys.
        with open(resume, encoding="utf-8") as f:
            raw = json.load(f)
        restore["quest_transcript"] = raw.get("quest_transcript", [])
        restore["quest_picks"] = raw.get("quest_picks", 0)
    os.makedirs(outdir, exist_ok=True)
    store_path = os.path.join(outdir, "xapi.jsonl")
    if os.path.exists(store_path) and restore is None:
        os.remove(store_path)
    store = xapi.XAPIStore(store_path)
    session, state, _ = adaptive.run_quest(
        data, v1, responses, actor, max_retries, max_steps, restore, store
    )
    with open(os.path.join(outdir, "session.json"), "w", encoding="utf-8") as f:
        json.dump(session, f, indent=1, sort_keys=True)
        f.write("\n")
    if save is not None:
        save_state(state, save)
    report_path = os.path.join(outdir, REPORT_NAME)
    section = _quest_report(responses_path or "stdin", session)
    if os.path.exists(report_path):
        with open(report_path, "a", encoding="utf-8") as f:
            f.write(section)
    else:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("# Gramophone M4 — Run Report\n" + section)
    return session


def _quest_report(source: str, session: dict) -> str:
    completion = session["completion"]
    return (
        f"\n## Quest\nsource={source} "
        f"VISITED={len(session['beats_visited'])} ATTEMPTS={session['attempts']} "
        f"PASSED={session['passed']} XP={session['xp']} LEVEL={session['level']} "
        f"STREAK_MAX={session['streak_max']} "
        f"FLOW_RATIO={session['flow_in_band_ratio']} "
        f"XAPI={session['xapi_statements']} "
        f"SKIPPED={len(session['skipped'])} RETRIES={session['retries_used']} "
        f"COMPLETION={completion['reason']} PICKS={completion['picks']}\n"
    )
