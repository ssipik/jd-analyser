"""Command-line entry point for jd-analyser.

Subcommands: ``dump-samples`` (P1, capture raw alert emails for parser work) and ``run``
(P6, the scan → analyse → notify pipeline). Each subcommand attaches its callable via
``set_defaults(handler=...)``.
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


def cmd_run(args: argparse.Namespace) -> int:
    """Run the full pipeline: scan sources, analyse new jobs, email the digest."""
    from jd_analyser.analyzer import JobAnalyzer
    from jd_analyser.config import Settings
    from jd_analyser.interfaces.gmail_api import GmailAPIInterface
    from jd_analyser.pipeline import run_pipeline
    from jd_analyser.sources.stepstone import StepstoneScan
    from jd_analyser.store import JobStore

    settings = Settings.load()
    gmail = GmailAPIInterface(settings.client_secret_path, settings.token_path)
    store = JobStore(settings.db_path)
    scans = [StepstoneScan(gmail, settings.gmail_query)]

    analyzer = None
    if not args.no_llm:
        from jd_analyser.interfaces.anthropic_llm import AnthropicLLM

        llm = AnthropicLLM(settings.anthropic_api_key, settings.model)
        analyzer = JobAnalyzer.from_config(llm)

    notifier = None
    if not args.no_email:
        if not settings.notify_to:
            print("NOTIFY_TO is not set in .env — skipping the digest email.", file=sys.stderr)
        else:
            from jd_analyser.notifier.email_notifier import EmailNotifier

            notifier = EmailNotifier(gmail, settings.notify_to, settings.score_threshold)

    result = run_pipeline(
        scans, store, analyzer, notifier, limit=args.limit, dry_run=args.dry_run
    )

    print(f"Fetched {result.fetched} job(s); {len(result.new)} new.")
    if args.dry_run:
        for job in result.new:
            print(f"  would store: {job.title!r} — {job.company} [{job.key}]")
        return 0
    if analyzer is not None:
        print(f"Analysed {result.analysed} job(s); {len(result.errors)} error(s).")
        for key, message in result.errors:
            print(f"  error for {key}: {message}", file=sys.stderr)
    if result.notified:
        print(f"Digest sent to {settings.notify_to} ({result.notified} job(s)).")
    return 1 if result.errors else 0


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

    p_run = sub.add_parser(
        "run", help="Scan sources, analyse new jobs via the LLM, and email the digest."
    )
    p_run.add_argument("--dry-run", action="store_true", help="Report what is new; change nothing.")
    p_run.add_argument("--limit", type=int, default=None, help="Max jobs to analyse this run.")
    p_run.add_argument("--no-llm", action="store_true", help="Skip analysis; just store new jobs.")
    p_run.add_argument("--no-email", action="store_true", help="Analyse but do not send the digest.")
    p_run.set_defaults(handler=cmd_run)

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
