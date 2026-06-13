"""End-to-end pipeline: scan → store (dedup) → analyse → notify (P6).

Status-driven and resumable: scanning stores new jobs as ``new``; the analysis pass picks
up *everything* still ``new`` (including leftovers from earlier ``--no-llm`` or crashed
runs); the notify pass digests everything ``analysed``. Each stage advances the store
status (`new → analysed → notified`, or ``error``), so re-running is always safe and never
re-bills the LLM for a job it has already analysed.

`run_pipeline` takes the components as arguments (any of them fake-able) and performs no
I/O of its own beyond what they do — the CLI builds the real ones.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from jd_analyser.analyzer import JobAnalyzer
from jd_analyser.models import JobDescription
from jd_analyser.notifier.base import DigestItem, Notifier
from jd_analyser.sources.base import JobDescriptionScan
from jd_analyser.store import JobStore


@dataclass
class PipelineResult:
    """What a run did, for reporting and tests."""

    fetched: int = 0
    new: list[JobDescription] = field(default_factory=list)
    analysed: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)  # (job key, message)
    notified: int = 0
    dry_run: bool = False


def _job_from_row(row: dict[str, Any]) -> JobDescription:
    return JobDescription(
        source=row["source"],
        external_id=row["external_id"],
        title=row["title"] or "",
        company=row["company"] or "",
        full_text=row["full_text"] or "",
        url=row["url"] or "",
        location=row["location"] or "",
    )


def run_pipeline(
    scans: list[JobDescriptionScan],
    store: JobStore,
    analyzer: Optional[JobAnalyzer] = None,
    notifier: Optional[Notifier] = None,
    *,
    limit: Optional[int] = None,
    dry_run: bool = False,
) -> PipelineResult:
    """Run scan/analyse/notify once. ``analyzer=None`` skips analysis (jobs stay ``new``);
    ``notifier=None`` skips the digest (jobs stay ``analysed``); ``limit`` caps how many
    jobs are analysed this run (cost control); ``dry_run`` only reports what would be new.
    """
    result = PipelineResult(dry_run=dry_run)

    fetched: list[JobDescription] = []
    for scan in scans:
        fetched.extend(scan.fetch_job_descriptions())
    result.fetched = len(fetched)
    result.new = store.filter_new(fetched)
    if dry_run:
        return result
    for job in result.new:
        store.save_job(job)

    if analyzer is not None:
        pending = store.get_jobs_by_status("new")
        if limit is not None:
            pending = pending[:limit]
        for row in pending:
            job = _job_from_row(row)
            try:
                analysis = analyzer.analyse(job)
            except Exception as exc:
                store.set_status(job.source, job.external_id, "error")
                result.errors.append((job.key, str(exc)))
                continue
            store.save_analysis(job.source, job.external_id, analysis)
            result.analysed += 1

    if notifier is not None:
        items: list[DigestItem] = []
        for row in store.get_jobs_by_status("analysed"):
            analysis = store.get_analysis(row["source"], row["external_id"])
            if analysis is not None:
                items.append(DigestItem(job=_job_from_row(row), analysis=analysis))
        if items and notifier.send_digest(items) is not None:
            for item in items:
                store.set_status(item.job.source, item.job.external_id, "notified")
            result.notified = len(items)

    return result
