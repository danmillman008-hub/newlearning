"""M5 book quest: chapters -> book graph -> authored beats -> quest.

``run_book_quest`` is pure orchestration: M3 ``merge_graphs`` builds the
book graph, M2 ``author_beats`` (``llm=None``: deterministic fallback,
zero tokens) drafts the beats, M4 ``run_quest`` plays them. Writes
``book-graph.json`` + ``beats.json`` + ``session.json`` + ``xapi.jsonl``
(fresh unless resume) + the three sections of ``M5-REPORT.md``. Bad input
raises ValueError before anything is written; same inputs =
byte-identical outputs.
"""

from __future__ import annotations

import json
import os

from gramophone_m2.author import author_beats
from gramophone_m2.story_model import save_beats, validate
from gramophone_m2.xapi import XAPIStore
from gramophone_m3.live import load_state, save_state
from gramophone_m3.merge import merge_graphs
from gramophone_m4.adaptive import run_quest
from gramophone_m4.pipeline import parse_response_line

REPORT_NAME = "M5-REPORT.md"


def _load_chapter(path: str) -> dict:
    if not os.path.exists(path):
        raise ValueError(f"book quest: chapter not found: {path}")
    with open(path, encoding="utf-8") as f:
        try:
            v1 = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"book quest: chapter is not JSON: {path}: {e}") from e
    if (
        not isinstance(v1, dict)
        or not isinstance(v1.get("items"), list)
        or not isinstance(v1.get("surmise"), list)
    ):
        raise ValueError(f"book quest: chapter needs items[]/surmise[]: {path}")
    return v1


def run_book_quest(
    chapter_paths,
    outdir: str,
    responses_path: str | None = None,
    response_lines=None,
    names=None,
    save: str | None = None,
    resume: str | None = None,
    actor: str = "learner",
    max_retries: int = 1,
    max_steps: int = 1000,
) -> dict:
    """Run a book quest from chapter v1 files. Bad input -> ValueError."""
    if not isinstance(chapter_paths, (list, tuple)) or not chapter_paths:
        raise ValueError("book quest: need at least one chapter")
    v1s = [_load_chapter(p) for p in chapter_paths]
    if names is None:
        names = [
            os.path.splitext(os.path.basename(p))[0] for p in chapter_paths
        ]
    if isinstance(names, str) or not isinstance(names, (list, tuple)):
        raise ValueError("book quest: names must be a list")
    if len(names) != len(v1s):
        raise ValueError("book quest: names length must match chapters")
    if responses_path is not None and response_lines is not None:
        raise ValueError("book quest: --responses and stdin lines are exclusive")
    if responses_path is not None:
        if not os.path.exists(responses_path):
            raise ValueError(f"book quest: responses not found: {responses_path}")
        with open(responses_path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    elif response_lines is not None:
        if isinstance(response_lines, str) or not isinstance(
            response_lines, (list, tuple)
        ):
            raise ValueError("book quest: response lines must be a list")
        lines = response_lines
    else:
        raise ValueError("book quest: no responses (need --responses or stdin lines)")
    responses = [parse_response_line(l) for l in lines if l.strip()]
    restore = None
    prior_retries = 0
    prior_skipped: list = []
    if resume is not None:
        restore = load_state(resume)
        # live.load_state keeps M3 keys only; re-attach M4 quest keys.
        with open(resume, encoding="utf-8") as f:
            raw = json.load(f)
        restore["quest_transcript"] = raw.get("quest_transcript", [])
        restore["quest_picks"] = raw.get("quest_picks", 0)
        # M4's run_quest counts retries/skips per call, so resume would
        # drop pre-boundary totals; M5 carries them (no M4 modification).
        prior_retries = raw.get("m5_retries_total", 0)
        prior_skipped = raw.get("m5_skipped_total", [])
        if (
            isinstance(prior_retries, bool)
            or not isinstance(prior_retries, int)
            or prior_retries < 0
            or not isinstance(prior_skipped, list)
            or any(not isinstance(i, int) for i in prior_skipped)
        ):
            raise ValueError("book quest: resume state has bad M5 counters")
    os.makedirs(outdir, exist_ok=True)
    book = merge_graphs(v1s, list(names))
    with open(os.path.join(outdir, "book-graph.json"), "w", encoding="utf-8") as f:
        json.dump(book, f, indent=1, sort_keys=True)
        f.write("\n")
    beats, info = author_beats(book)
    issues = validate(beats)
    if issues:
        raise RuntimeError(f"internal error: authored beats invalid: {issues}")
    save_beats(beats, os.path.join(outdir, "beats.json"))
    store_path = os.path.join(outdir, "xapi.jsonl")
    if os.path.exists(store_path) and restore is None:
        os.remove(store_path)
    store = XAPIStore(store_path)
    session, state, _ = run_quest(
        beats, book, responses, actor, max_retries, max_steps, restore, store
    )
    # run_quest indices are already global (transcript carries over), so a
    # plain concatenation keeps skipped exact across the boundary.
    session["skipped"] = prior_skipped + session["skipped"]
    session["retries_used"] = prior_retries + session["retries_used"]
    state["m5_retries_total"] = session["retries_used"]
    state["m5_skipped_total"] = session["skipped"]
    with open(os.path.join(outdir, "session.json"), "w", encoding="utf-8") as f:
        json.dump(session, f, indent=1, sort_keys=True)
        f.write("\n")
    if save is not None:
        save_state(state, save)
    report_path = os.path.join(outdir, REPORT_NAME)
    section = _book_report(len(v1s), book, beats, info, session)
    if os.path.exists(report_path):
        with open(report_path, "a", encoding="utf-8") as f:
            f.write(section)
    else:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("# Gramophone M5 — Run Report\n" + section)
    return session


def _book_report(n_chapters: int, book: dict, beats: dict, info: dict,
                 session: dict) -> str:
    completion = session["completion"]
    return (
        f"\n## Merge\nBOOK CHAPTERS={n_chapters} "
        f"ITEMS={len(book['items'])} EDGES={len(book['surmise'])} "
        f"STATES={len(book.get('states', []))}\n"
        f"\n## Author\nBEATS={len(beats['beats'])} CHECKS={len(beats['checks'])} "
        f"CLUSTERS={info['clusters']} VIA_FALLBACK={info['clusters_fallback']} "
        f"TOKENS={info['tokens']}\n"
        f"\n## Quest\nVISITED={len(session['beats_visited'])} "
        f"ATTEMPTS={session['attempts']} PASSED={session['passed']} "
        f"XP={session['xp']} LEVEL={session['level']} "
        f"STREAK_MAX={session['streak_max']} "
        f"FLOW_RATIO={session['flow_in_band_ratio']} "
        f"XAPI={session['xapi_statements']} SKIPPED={len(session['skipped'])} "
        f"RETRIES={session['retries_used']} "
        f"COMPLETION={completion['reason']} PICKS={completion['picks']}\n"
    )
