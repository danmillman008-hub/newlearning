"""CLI for Gramophone M6: full chain from raw chapters to quest.

Exits: 0 ok, 2 bad input, 1 internal error. Without --responses, bare
response lines (JSON literal or raw string) are read from stdin.
"""

from __future__ import annotations

import argparse
import json
import sys

from . import fullchain


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gramophone-m6")
    parser.add_argument("chapters", nargs="+", help="input chapter files")
    parser.add_argument("--out", required=True, help="output directory")
    parser.add_argument("--responses", default=None, help="response lines file")
    parser.add_argument("--names", nargs="*", default=None,
                        help="chapter names (default: file stems)")
    parser.add_argument("--max-items", type=int, default=300)
    parser.add_argument("--token-budget", type=int, default=None)
    parser.add_argument("--save", default=None, help="write end-state JSON here")
    parser.add_argument("--resume", default=None, help="resume from state JSON")
    parser.add_argument("--actor", default="learner")
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--max-steps", type=int, default=1000)
    return parser


def _read_stdin_lines() -> list[str]:
    if sys.stdin.isatty():
        print("gramophone-m6: type one response per line, blank to finish.",
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
        lines = None if args.responses is not None else _read_stdin_lines()
        result = fullchain.run_full_chain(
            args.chapters, args.out, args.responses, lines, args.names,
            args.save, args.resume, args.actor,
            args.max_retries, args.max_steps,
            args.max_items, args.token_budget,
        )
        for counts in result["m1"]:
            print(counts["stdout"])
        with open(f"{args.out}/book-graph.json", encoding="utf-8") as f:
            book = json.load(f)
        with open(f"{args.out}/beats.json", encoding="utf-8") as f:
            beats = json.load(f)
        session = result["session"]
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
        print(f"gramophone-m6: error: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001 - CLI maps these to exit 1
        print(f"gramophone-m6: internal error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc(limit=3)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
