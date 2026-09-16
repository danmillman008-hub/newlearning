"""CLI for Gramophone M2: author / learn / export-xapi.

Exits: 0 ok, 2 bad input, 1 internal error. Default backend is MockLLM
with the bundled STORY cassette; --llm none selects the rule fallback.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback

from gramophone_m1.llm_client import MockLLM, flash_llm_or_raise

from . import pipeline, xapi


def default_cassette_path() -> str:
    """Bundled STORY cassette (sibling of the package) or env override."""
    override = os.environ.get("M2_CASSETTE")
    if override:
        return override
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(here), "cassettes", "mock_story.json")


def default_llm(path: str | None = None):
    """Default backend: MockLLM with the STORY cassette (None if missing)."""
    cassette = path or default_cassette_path()
    if not os.path.exists(cassette):
        return None
    return MockLLM.from_file(cassette)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gramophone-m2")
    sub = parser.add_subparsers(dest="cmd", required=True)
    auth = sub.add_parser("author", help="author beats from a v1 graph")
    auth.add_argument("graph", help="input knowledge-graph.json v1")
    auth.add_argument("--out", required=True, help="output directory")
    auth.add_argument("--llm", choices=["mock", "none", "flash"], default="mock")
    auth.add_argument("--cassette", default=None, help="STORY cassette path")
    auth.add_argument("--token-budget", type=int, default=None)
    learn = sub.add_parser("learn", help="replay a scripted session")
    learn.add_argument("beats", help="input beats.json")
    learn.add_argument("--script", required=True, help="scripted attempts JSON")
    learn.add_argument("--out", required=True, help="output directory")
    exp = sub.add_parser("export-xapi", help="validate + copy an xAPI store")
    exp.add_argument("store", help="input xapi.jsonl")
    exp.add_argument("--out", required=True, help="output file")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "author":
            if args.llm == "mock":
                llm = default_llm(args.cassette)
            elif args.llm == "flash":
                llm = flash_llm_or_raise()
            else:
                llm = None
            report = pipeline.run_author(args.graph, args.out, llm, args.token_budget)
            pruned = sum(report["pruned"].values())
            print(
                f"SESSION BEATS={report['beats']} CHECKS={report['checks']} "
                f"PRUNED={pruned} TOKENS={report['tokens']}"
            )
        elif args.cmd == "learn":
            session = pipeline.run_learn(args.beats, args.script, args.out)
            print(
                f"SESSION VISITED={len(session['beats_visited'])} "
                f"ATTEMPTS={session['attempts']} PASSED={session['passed']} "
                f"XP={session['xp']} LEVEL={session['level']} "
                f"STREAK_MAX={session['streak_max']}"
            )
        elif args.cmd == "export-xapi":
            n = xapi.export_xapi(args.store, args.out)
            print(f"SESSION STATEMENTS={n}")
        return 0
    except (FileNotFoundError, ValueError, KeyError, json.JSONDecodeError) as e:
        print(f"gramophone-m2: error: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001 - CLI maps these to exit 1
        print(f"gramophone-m2: internal error: {e}", file=sys.stderr)
        traceback.print_exc(limit=3)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
