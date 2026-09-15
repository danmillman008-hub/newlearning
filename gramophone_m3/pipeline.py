"""M3 pipelines: merge (chapters -> book graph) and play (beats -> session).

``run_merge(paths, outdir, names=None)`` writes ``book-graph.json`` plus the
merge section of ``M3-REPORT.md``. ``run_play(beats_path, outdir, ...)``
writes ``session.json`` + ``xapi.jsonl`` (appended on resume, fresh
otherwise) and the play section of the report. Bad input raises ValueError
before anything is written; same inputs = byte-identical outputs modulo
the book's generated_at timestamp.
"""

from __future__ import annotations

import json
import os

from gramophone_m2 import story_model, xapi

from . import live, merge

REPORT_NAME = "M3-REPORT.md"


def _write_json(path: str, payload: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, sort_keys=True)
        f.write("\n")


def run_merge(paths: list[str], outdir: str, names: list[str] | None = None) -> dict:
    """Merge chapter v1 files into a book graph. Bad input -> ValueError."""
    if not paths:
        raise ValueError("merge: no input graphs")
    if names is None:
        names = [os.path.splitext(os.path.basename(p))[0] for p in paths]
    graphs = []
    for path in paths:
        if not os.path.exists(path):
            raise ValueError(f"merge: input not found: {path}")
        with open(path, encoding="utf-8") as f:
            try:
                graphs.append(json.load(f))
            except json.JSONDecodeError as e:
                raise ValueError(f"merge: {path} is not JSON: {e}") from e
    book = merge.merge_graphs(graphs, names)
    os.makedirs(outdir, exist_ok=True)
    _write_json(os.path.join(outdir, "book-graph.json"), book)
    report = {
        "chapters": len(graphs),
        "items": len(book["items"]),
        "edges": len(book["surmise"]),
        "states": len(book["states"]),
        "fringe0": len(book["fringe_cache"][""]),
        "overflow": book["metadata"]["overflow"],
    }
    with open(os.path.join(outdir, REPORT_NAME), "w", encoding="utf-8") as f:
        f.write(_merge_report(paths, report))
    return report


def run_play(
    beats_path: str,
    outdir: str,
    script: str | None = None,
    input_lines: list[str] | None = None,
    save: str | None = None,
    resume: str | None = None,
    actor: str = "learner",
    max_retries: int = 1,
) -> dict:
    """Play attempts over beats. Bad input -> ValueError."""
    if not os.path.exists(beats_path):
        raise ValueError(f"play: input not found: {beats_path}")
    data = story_model.load_beats(beats_path)
    issues = story_model.validate(data)
    if issues:
        raise ValueError(f"play: beats invalid: {issues}")
    if script is not None and input_lines is not None:
        raise ValueError("play: --script and stdin lines are exclusive")
    if script is not None:
        if not os.path.exists(script):
            raise ValueError(f"play: script not found: {script}")
        with open(script, encoding="utf-8") as f:
            try:
                loaded = json.load(f)
            except json.JSONDecodeError as e:
                raise ValueError(f"play: script is not JSON: {e}") from e
        attempts = loaded.get("attempts")
        if not isinstance(loaded, dict) or not isinstance(attempts, list):
            raise ValueError("play: script needs {actor, attempts:[...]}")
        actor = loaded.get("actor", actor)
    elif input_lines is not None:
        attempts = [live.parse_attempt_line(l) for l in input_lines if l.strip()]
    else:
        raise ValueError("play: no attempts (need --script or stdin lines)")
    restore = live.load_state(resume) if resume is not None else None
    os.makedirs(outdir, exist_ok=True)
    store_path = os.path.join(outdir, "xapi.jsonl")
    if os.path.exists(store_path) and restore is None:
        os.remove(store_path)
    store = xapi.XAPIStore(store_path)
    session, state = live.play_session(
        data, attempts, actor, max_retries, restore, store
    )
    _write_json(os.path.join(outdir, "session.json"), session)
    if save is not None:
        live.save_state(state, save)
    report_path = os.path.join(outdir, REPORT_NAME)
    section = _play_report(script or "stdin", session)
    if os.path.exists(report_path):
        with open(report_path, "a", encoding="utf-8") as f:
            f.write(section)
    else:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("# Gramophone M3 — Run Report\n" + section)
    return session


def _merge_report(paths: list[str], report: dict) -> str:
    return (
        "# Gramophone M3 — Run Report\n\n"
        f"## Merge\nchapters={','.join(paths)} "
        f"CHAPTERS={report['chapters']} ITEMS={report['items']} "
        f"EDGES={report['edges']} STATES={report['states']} "
        f"FRINGE0={report['fringe0']} OVERFLOW={int(report['overflow'])}\n"
    )


def _play_report(source: str, session: dict) -> str:
    return (
        f"\n## Play\nsource={source} "
        f"VISITED={len(session['beats_visited'])} ATTEMPTS={session['attempts']} "
        f"PASSED={session['passed']} XP={session['xp']} LEVEL={session['level']} "
        f"STREAK_MAX={session['streak_max']} "
        f"FLOW_RATIO={session['flow_in_band_ratio']} "
        f"XAPI={session['xapi_statements']} "
        f"SKIPPED={len(session['skipped'])} RETRIES={session['retries_used']}\n"
    )
