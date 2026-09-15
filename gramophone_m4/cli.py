"""CLI for Gramophone M4: adaptive quest play.

Exits: 0 ok, 2 bad input, 1 internal error. Without --responses, bare
response lines (JSON literal or raw string) are read from stdin.
"""

from __future__ import annotations

import argparse
import json
import sys

from . import pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gramophone-m4")
    sub = parser.add_subparsers(dest="cmd", required=True)
    pl = sub.add_parser("play", help="run an adaptive quest")
    pl.add_argument("beats", help="input beats.json")
    pl.add_argument("--graph", required=True, help="input v1 graph (fringe)")
    pl.add_argument("--out", required=True, help="output directory")
    pl.add_argument("--responses", default=None, help="response lines file")
    pl.add_argument("--save", default=None, help="write end-state JSON here")
    pl.add_argument("--resume", default=None, help="resume from state JSON")
    pl.add_argument("--actor", default="learner")
    pl.add_argument("--max-retries", type=int, default=1)
    pl.add_argument("--max-steps", type=int, default=1000)
    return parser


def _read_stdin_lines() -> list[str]:
    if sys.stdin.isatty():
        print("gramophone-m4 play: type one response per line, blank to finish.",
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
        if args.cmd == "play":
            lines = None if args.responses is not None else _read_stdin_lines()
            session = pipeline.run_quest_file(
                args.beats, args.graph, args.out, args.responses, lines,
                args.save, args.resume, args.actor,
                args.max_retries, args.max_steps,
            )
            print(
                f"SESSION VISITED={len(session['beats_visited'])} "
                f"ATTEMPTS={session['attempts']} PASSED={session['passed']} "
                f"XP={session['xp']} LEVEL={session['level']} "
                f"STREAK_MAX={session['streak_max']} "
                f"SKIPPED={len(session['skipped'])} RETRIES={session['retries_used']} "
                f"COMPLETION={session['completion']['reason']}"
            )
        return 0
    except (FileNotFoundError, ValueError, KeyError, json.JSONDecodeError) as e:
        print(f"gramophone-m4: error: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001 - CLI maps these to exit 1
        print(f"gramophone-m4: internal error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc(limit=3)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
