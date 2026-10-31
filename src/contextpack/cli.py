"""Command line interface: contextpack {pack, demo}.

`pack` writes the assembled context to stdout (or --out FILE) and a
one-line summary to stderr, so it composes in a pipeline:

    contextpack pack items.json --budget 4000 --out context.txt
    contextpack pack items.json --budget 4000 --manifest m.json | my-agent
"""

from __future__ import annotations

import argparse
import functools
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from .demo import render_manifest_markdown, run_demo
from .pack import estimate_tokens, load_items, pack


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="contextpack",
        description="Assemble LLM context under a hard token budget, "
        "with a manifest of every keep / truncate / drop decision.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_pack = sub.add_parser("pack", help="pack an items JSON file into a token budget")
    p_pack.add_argument("items", metavar="ITEMS.json")
    p_pack.add_argument(
        "--budget", type=int, required=True, metavar="TOKENS",
        help="token budget for the assembled context",
    )
    p_pack.add_argument(
        "--chars-per-token", type=int, default=4, metavar="N",
        help="token estimate heuristic (default: 4)",
    )
    p_pack.add_argument(
        "--out", metavar="FILE",
        help="write the assembled context to FILE instead of stdout",
    )
    p_pack.add_argument(
        "--manifest", metavar="FILE",
        help="write the decision manifest (JSON) to FILE",
    )

    sub.add_parser(
        "demo",
        help="pack a sample context: the huge tool result is "
        "truncated, yesterday's history is dropped",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            result = run_demo()
            lines = [
                "# contextpack demo",
                "",
                f"Budget: {result.budget_tokens} tokens "
                f"(estimate, 4 chars/token).",
                "",
                render_manifest_markdown(result),
                "",
                "## Assembled context",
                "",
                result.text,
                "",
            ]
            sys.stdout.write("\n".join(lines))
            return 0

        items = load_items(args.items)
        counter = functools.partial(
            estimate_tokens, chars_per_token=args.chars_per_token
        )
        result = pack(items, args.budget, token_counter=counter)
        if args.out:
            Path(args.out).write_text(result.text, encoding="utf-8")
        else:
            sys.stdout.write(result.text + "\n")
        if args.manifest:
            Path(args.manifest).write_text(
                json.dumps(result.manifest(), indent=2) + "\n",
                encoding="utf-8",
            )
        counts = result.manifest()["counts"]
        print(
            f"contextpack: used {result.used_tokens}/{result.budget_tokens} "
            f"tokens; kept {counts['kept']}, truncated "
            f"{counts['truncated']}, dropped {counts['dropped']}"
            + ("; WARNING: pinned items exceed the budget" if result.over_budget else ""),
            file=sys.stderr,
        )
        return 0
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
