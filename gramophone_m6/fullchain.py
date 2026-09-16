"""M6 full chain: raw chapters -> M1 graphs -> M5 book quest.

``run_full_chain`` runs stage 1 (``break_file`` per chapter into
``outdir/m1_<name>/``, kept as provenance) then stage 2
(``run_book_quest`` over the v1 graphs, outputs in ``outdir``). Writes
``M6-REPORT.md`` (chapters + quest summary); M5's own ``M5-REPORT.md``
is left in place. Bad input raises ValueError before anything is
written; same inputs = identical outputs modulo inherited wall clocks.
"""

from __future__ import annotations

import os

from gramophone_m1.pipeline import break_file, default_llm
from gramophone_m5.bookquest import run_book_quest

REPORT_NAME = "M6-REPORT.md"


def run_full_chain(
    chapter_inputs,
    outdir: str,
    responses_path: str | None = None,
    response_lines=None,
    names=None,
    save: str | None = None,
    resume: str | None = None,
    actor: str = "learner",
    max_retries: int = 1,
    max_steps: int = 1000,
    max_items: int = 300,
    token_budget: int | None = None,
) -> dict:
    """Run the full chain from raw chapter files. Bad input -> ValueError."""
    if not isinstance(chapter_inputs, (list, tuple)) or not chapter_inputs:
        raise ValueError("full chain: need at least one chapter")
    for path in chapter_inputs:
        if not os.path.exists(path):
            raise ValueError(f"full chain: chapter not found: {path}")
    if names is None:
        names = [
            os.path.splitext(os.path.basename(p))[0] for p in chapter_inputs
        ]
    if isinstance(names, str) or not isinstance(names, (list, tuple)):
        raise ValueError("full chain: names must be a list")
    if len(names) != len(chapter_inputs):
        raise ValueError("full chain: names length must match chapters")
    if default_llm() is None:
        # Never silently degrade to the no-cassette fallback graph: the
        # M1 stage must be the CLI-canonical cassette run (or a loud error).
        raise ValueError(
            "full chain: M1 cassette missing (cassettes/mock_default.json "
            "not found and GRAMOPHONE_CASSETTE unset)"
        )
    m1s = []
    for path, name in zip(chapter_inputs, names):
        m1s.append(
            break_file(
                path,
                os.path.join(outdir, f"m1_{name}"),
                max_items,
                token_budget,
                llm=default_llm(),
            )
        )
    v1_paths = [counts["v1_path"] for counts in m1s]
    session = run_book_quest(
        v1_paths, outdir, responses_path, response_lines, list(names),
        save, resume, actor, max_retries, max_steps,
    )
    report_path = os.path.join(outdir, REPORT_NAME)
    section = _chain_report(m1s, session)
    if os.path.exists(report_path):
        with open(report_path, "a", encoding="utf-8") as f:
            f.write(section)
    else:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("# Gramophone M6 — Run Report\n" + section)
    return {"m1": m1s, "session": session}


def _chain_report(m1s: list[dict], session: dict) -> str:
    completion = session["completion"]
    lines = ["\n## Chapters\n"]
    lines.extend(counts["stdout"] + "\n" for counts in m1s)
    lines.append(
        f"\n## Quest\nVISITED={len(session['beats_visited'])} "
        f"ATTEMPTS={session['attempts']} PASSED={session['passed']} "
        f"XP={session['xp']} LEVEL={session['level']} "
        f"STREAK_MAX={session['streak_max']} "
        f"FLOW_RATIO={session['flow_in_band_ratio']} "
        f"XAPI={session['xapi_statements']} SKIPPED={len(session['skipped'])} "
        f"RETRIES={session['retries_used']} "
        f"COMPLETION={completion['reason']} PICKS={completion['picks']}\n"
    )
    return "".join(lines)
