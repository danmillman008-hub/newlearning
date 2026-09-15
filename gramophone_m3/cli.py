"""CLI for Gramophone M3: merge / play.

Exits: 0 ok, 2 bad input, 1 internal error. play without --script reads
attempt lines (beat|check|response) from stdin — piped or live-typed
(prompts go to stderr, SESSION lines stay clean on stdout).
"""

from __future__ import annotations

import argparse
import json
import sys

from . import pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gramophone-m3")
    sub = parser.add_subparsers(dest="cmd", required=True)
    mg = sub.add_parser("merge", help="merge chapter v1 graphs into a book")
    mg.add_argument("graphs", nargs="+", help="input knowledge-graph.json v1 files")
    mg.add_argument("--out", required=True, help="output directory")
    mg.add_argument("--names", nargs="*", default=None, help="chapter names")
    pl = sub.add_parser("play", help="play attempts over a beat graph")
    pl.add_argument("beats", help="input beats.json")
    pl.add_argument("--out", required=True, help="output directory")
    pl.add_argument("--script", default=None, help="scripted attempts JSON")
    pl.add_argument("--save", default=None, help="write end-state JSON here")
    pl.add_argument("--resume", default=None, help="resume from state JSON")
    pl.add_argument("--actor", default="learner")
    pl.add_argument("--max-retries", type=int, default=1)
    return parser


def _read_stdin_lines() -> list[str]:
    if sys.stdin.isatty():
        print("gramophone-m3 play: type beat|check|response lines, blank to finish.",
              file=sys.stderr)
    lines = []
    for raw in sys.stdin:
        line = raw.rstrip("\n")
        if sys.stdin.isatty() and not line.strip():
            break
        if line.strip():
            lines.append(line)
    return lines


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "merge":
            report = pipeline.run_merge(args.graphs, args.out, args.names)
            print(
                f"MERGED CHAPTERS={report['chapters']} ITEMS={report['items']} "
                f"EDGES={report['edges']} STATES={report['states']} "
                f"FRINGE0={report['fringe0']} OVERFLOW={int(report['overflow'])}"
            )
        elif args.cmd == "play":
            lines = None if args.script is not None else _read_stdin_lines()
            session = pipeline.run_play(
                args.beats, args.out, args.script, lines,
                args.save, args.resume, args.actor, args.max_retries,
            )
            print(
                f"SESSION VISITED={len(session['beats_visited'])} "
                f"ATTEMPTS={session['attempts']} PASSED={session['passed']} "
                f"XP={session['xp']} LEVEL={session['level']} "
                f"STREAK_MAX={session['streak_max']} "
                f"SKIPPED={len(session['skipped'])} RETRIES={session['retries_used']}"
            )
        return 0
    except (FileNotFoundError, ValueError, KeyError, json.JSONDecodeError) as e:
        print(f"gramophone-m3: error: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001 - CLI maps these to exit 1
        print(f"gramophone-m3: internal error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc(limit=3)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
