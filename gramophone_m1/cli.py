"""Command line: gramophone-m1 break INPUT --out OUTDIR [--max-items N] [--token-budget N].

Exit codes: 0 ok, 2 bad input, 3 budget exhausted (reserved: per the M1 test
plan, budget exhaustion degrades to fewer outputs and still exits 0), 1
internal error.
"""

from __future__ import annotations

import argparse
import sys
import traceback

from .pipeline import break_file, default_llm

EXIT_OK = 0
EXIT_INTERNAL = 1
EXIT_INPUT = 2
EXIT_BUDGET = 3  # reserved; currently unused (see module docstring)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gramophone-m1")
    sub = parser.add_subparsers(dest="command", required=True)
    brk = sub.add_parser("break", help="break a chapter into a knowledge graph")
    brk.add_argument("input", help="input chapter (.md/.txt/.pdf)")
    brk.add_argument("--out", required=True, help="output directory")
    brk.add_argument("--max-items", type=int, default=300)
    brk.add_argument("--token-budget", type=int, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "break":
        try:
            result = break_file(
                args.input,
                args.out,
                max_items=args.max_items,
                token_budget=args.token_budget,
                llm=default_llm(),
            )
        except FileNotFoundError as exc:
            print(f"gramophone-m1: {exc}", file=sys.stderr)
            return EXIT_INPUT
        except ValueError as exc:
            print(f"gramophone-m1: {exc}", file=sys.stderr)
            return EXIT_INPUT
        except Exception as exc:  # noqa: BLE001 - CLI must map all errors to exit 1
            print(f"gramophone-m1: internal error: {exc}", file=sys.stderr)
            traceback.print_exc()
            return EXIT_INTERNAL
        print(result["stdout"])
        return EXIT_OK
    return EXIT_INTERNAL


if __name__ == "__main__":
    raise SystemExit(main())
