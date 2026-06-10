"""Tests for JobStore: dedup, analysis round-trip, status, and message tracking."""
import pytest

from jd_analyser.models import JobAnalysis, JobDescription, LikeVerdict, RecommendedAction
from jd_analyser.store import JobStore


@pytest.fixture
def store(tmp_path):
    return JobStore(tmp_path / "jobs.db")


def _job(external_id: str, source: str = "stepstone") -> JobDescription:
    return JobDescription(
        source=source,
        external_id=external_id,
        title="Backend Engineer",
        company="ACME",
        full_text="We need Python and SQL.",
        url=f"https://www.stepstone.de/job-{external_id}",
        location="Berlin",
    )


def _analysis(score: int = 82) -> JobAnalysis:
    return JobAnalysis(
        match_score=score,
        summary="Strong fit",
        pros=["Python", "SQL"],
        cons_hard=[],
        cons_soft=["No Kubernetes"],
        like_verdict=LikeVerdict.LIKE,
        like_rationale="Remote-friendly",
        cv_suggestions=["Highlight SQL"],
        cover_letter="Dear hiring team...",
        recommended_action=RecommendedAction.APPLY,
    )


def test_filter_new_then_dedup(store):
    jobs = [_job("1"), _job("2")]
    assert store.filter_new(jobs) == jobs  # nothing stored yet
    for j in jobs:
        store.save_job(j)
    # Re-running with the same + one new job returns only the new one.
    new = store.filter_new([_job("1"), _job("2"), _job("3")])
    assert [j.external_id for j in new] == ["3"]


def test_save_job_is_idempotent(store):
    store.save_job(_job("1"))
    store.save_job(_job("1"))  # INSERT OR IGNORE -> no duplicate, no error
    assert store.get_job("stepstone", "1") is not None
    assert store.filter_new([_job("1")]) == []


def test_analysis_roundtrip_and_status(store):
    store.save_job(_job("1"))
    store.save_analysis("stepstone", "1", _analysis(score=91))
    row = store.get_job("stepstone", "1")
    assert row["status"] == "analysed"
    assert row["score"] == 91
    got = store.get_analysis("stepstone", "1")
    assert got == _analysis(score=91)

    store.set_status("stepstone", "1", "notified")
    row = store.get_job("stepstone", "1")
    assert row["status"] == "notified"
    assert row["notified_at"] is not None


def test_get_jobs_by_status_sorted_by_score(store):
    for ext, score in [("1", 50), ("2", 95), ("3", 70)]:
        store.save_job(_job(ext))
        store.save_analysis("stepstone", ext, _analysis(score=score))
    ordered = [r["external_id"] for r in store.get_jobs_by_status("analysed")]
    assert ordered == ["2", "3", "1"]


def test_processed_messages(store):
    assert store.is_message_processed("msg-1") is False
    store.mark_message_processed("msg-1")
    store.mark_message_processed("msg-1")  # idempotent
    assert store.is_message_processed("msg-1") is True
