"""Command-line entry point for jd-analyser.

Subcommands are registered incrementally as phases land (P1: ``dump-samples``,
P6: ``run``). Each subcommand attaches its callable via ``set_defaults(handler=...)``.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path


def cmd_dump_samples(args: argparse.Namespace) -> int:
    """Fetch matching emails and save them to disk for parser development."""
    from jd_analyser.config import DATA_DIR, Settings
    from jd_analyser.interfaces.gmail_api import GmailAPIInterface

    settings = Settings.load()
    gmail = GmailAPIInterface(settings.client_secret_path, settings.token_path)
    query = args.query or settings.gmail_query
    out_dir = Path(args.out) if args.out else (DATA_DIR / "samples")
    out_dir.mkdir(parents=True, exist_ok=True)

    ids = gmail.search(query, max_results=args.limit)
    print(f"Found {len(ids)} message(s) for query: {query!r}")
    for mid in ids:
        msg = gmail.get_message(mid)
        base = out_dir / mid
        base.with_suffix(".json").write_text(
            json.dumps(asdict(msg), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        if msg.html:
            base.with_suffix(".html").write_text(msg.html, encoding="utf-8")
        if msg.text:
            base.with_suffix(".txt").write_text(msg.text, encoding="utf-8")
        print(f"  saved {mid}: {msg.subject!r}")
    print(f"Wrote samples to {out_dir}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jd-analyser",
        description="Scan, analyse & filter job descriptions.",
    )
    sub = parser.add_subparsers(dest="command")

    p_dump = sub.add_parser(
        "dump-samples", help="Fetch matching emails and save them for inspection."
    )
    p_dump.add_argument("--query", default=None, help="Gmail search query (defaults to GMAIL_QUERY).")
    p_dump.add_argument("--limit", type=int, default=10, help="Max messages to fetch.")
    p_dump.add_argument("--out", default=None, help="Output directory (default data/samples).")
    p_dump.set_defaults(handler=cmd_dump_samples)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0
    try:
        return handler(args)
    except (FileNotFoundError, ValueError) as exc:
        # Expected setup/config errors: show a clean message, not a traceback.
        print(f"error: {exc}", file=sys.stderr)
        return 1
