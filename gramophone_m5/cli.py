"""CLI for Gramophone M5: book quest + unified `gramophone` dispatcher.

Exits: 0 ok, 2 bad input, 1 internal error (stage codes propagate through
the dispatcher unchanged).
"""

from __future__ import annotations

import argparse
import json
import sys

from gramophone_m1.cli import main as _m1
from gramophone_m2.cli import main as _m2
from gramophone_m3.cli import main as _m3
from gramophone_m4.cli import main as _m4
from gramophone_m6.cli import main as _m6

from . import bookquest

USAGE = "usage: gramophone {m1|m2|m3|m4|m6|quest} ..."


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gramophone-m5")
    parser.add_argument("chapters", nargs="+", help="input chapter v1 graphs")
    parser.add_argument("--out", required=True, help="output directory")
    parser.add_argument("--responses", default=None, help="response lines file")
    parser.add_argument("--names", nargs="*", default=None,
                        help="chapter names (default: file stems)")
    parser.add_argument("--save", default=None, help="write end-state JSON here")
    parser.add_argument("--resume", default=None, help="resume from state JSON")
    parser.add_argument("--actor", default="learner")
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--max-steps", type=int, default=1000)
    return parser


def _read_stdin_lines() -> list[str]:
    if sys.stdin.isatty():
        print("gramophone-m5: type one response per line, blank to finish.",
              file=sys.stderr)
    lines = []
    for raw in sys.stdin:
        line = raw.rstrip("\n")
        if sys.stdin.isatty() and not line.strip():
            break
        if line.strip():
            lines.append(line)
    return lines


def quest_main(argv: list[str] | None = None) -> int:
    """Direct book-quest entry (gramophone-m5 / gramophone quest)."""
    args = build_parser().parse_args(argv)
    try:
        lines = None if args.responses is not None else _read_stdin_lines()
        session = bookquest.run_book_quest(
            args.chapters, args.out, args.responses, lines, args.names,
            args.save, args.resume, args.actor,
            args.max_retries, args.max_steps,
        )
        with open(f"{args.out}/book-graph.json", encoding="utf-8") as f:
            book = json.load(f)
        with open(f"{args.out}/beats.json", encoding="utf-8") as f:
            beats = json.load(f)
        print(
            f"BOOK CHAPTERS={len(args.chapters)} ITEMS={len(book['items'])} "
            f"EDGES={len(book['surmise'])} BEATS={len(beats['beats'])} "
            f"CHECKS={len(beats['checks'])}"
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
        print(f"gramophone-m5: error: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001 - CLI maps these to exit 1
        print(f"gramophone-m5: internal error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc(limit=3)
        return 1


_STAGES = {"m1": _m1, "m2": _m2, "m3": _m3, "m4": _m4, "m6": _m6,
           "quest": quest_main}


def main(argv: list[str] | None = None) -> int:
    """Unified `gramophone` dispatcher: stage word + trailing args."""
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in _STAGES:
        print(USAGE, file=sys.stderr)
        return 2
    return _STAGES[args[0]](args[1:])


if __name__ == "__main__":
    raise SystemExit(main())
