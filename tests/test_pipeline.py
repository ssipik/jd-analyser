"""Tests for run_pipeline: status lifecycle, idempotency, resumability, error isolation.

Fakes follow the house pattern: a FakeScan serves prepared JobDescriptions, a FakeAnalyzer
returns a canned JobAnalysis (optionally failing for chosen jobs), a FakeNotifier records
what it was asked to send. The JobStore is real, on a tmp-path SQLite file.
"""
import pytest

from jd_analyser.models import JobAnalysis, JobDescription
from jd_analyser.pipeline import run_pipeline
from jd_analyser.store import JobStore

CANNED = {
    "language": "de",
    "tone": "formal",
    "profile_used": "de",
    "fit_score": 72,
    "combined_score": 78,
    "summary": "Good fit overall.",
    "pros": ["Python", "SQL"],
    "cons_hard": [],
    "cons_soft": ["No Kubernetes"],
    "like_verdict": "like",
    "like_rationale": "Remote-friendly.",
    "salary_range": "65.000-80.000 €",
    "salary_ask": "78.000 €",
    "cv_edits": [{"old": "Did data.", "new": "Built pipelines."}],
    "cover_letter": "Sehr geehrte Damen und Herren, ...",
}


def _jd(i: int) -> JobDescription:
    return JobDescription(
        source="stepstone",
        external_id=f"job-{i}",
        title=f"Data Engineer {i}",
        company="ACME",
        full_text=f"Job {i}: Python and SQL.",
        url=f"https://example.com/{i}",
        location="Berlin",
    )


class FakeScan:
    def __init__(self, jobs):
        self.jobs = jobs

    def fetch_job_descriptions(self):
        return list(self.jobs)


class FakeAnalyzer:
    def __init__(self, fail_for=()):
        self.fail_for = set(fail_for)
        self.analysed = []

    def analyse(self, job):
        if job.external_id in self.fail_for:
            raise RuntimeError("LLM exploded")
        self.analysed.append(job.external_id)
        return JobAnalysis.from_dict(CANNED)


class FakeNotifier:
    def __init__(self):
        self.sent = []

    def send_digest(self, items):
        if not items:
            return None
        self.sent.append(items)
        return {"id": f"sent-{len(self.sent)}"}


@pytest.fixture
def store(tmp_path):
    return JobStore(tmp_path / "jobs.db")


def test_full_run_stores_analyses_and_notifies(store):
    scan = FakeScan([_jd(1), _jd(2)])
    analyzer = FakeAnalyzer()
    notifier = FakeNotifier()

    result = run_pipeline([scan], store, analyzer, notifier)

    assert result.fetched == 2
    assert len(result.new) == 2
    assert result.analysed == 2
    assert result.errors == []
    assert result.notified == 2
    assert len(notifier.sent) == 1 and len(notifier.sent[0]) == 2
    assert store.get_job("stepstone", "job-1")["status"] == "notified"
    assert store.get_analysis("stepstone", "job-2").combined_score == 78


def test_second_run_is_idempotent(store):
    scan = FakeScan([_jd(1)])
    analyzer = FakeAnalyzer()
    notifier = FakeNotifier()
    run_pipeline([scan], store, analyzer, notifier)

    result = run_pipeline([scan], store, analyzer, notifier)

    assert result.fetched == 1
    assert result.new == []  # job already known
    assert result.analysed == 0  # LLM not billed again
    assert result.notified == 0
    assert len(notifier.sent) == 1  # no second digest


def test_dry_run_changes_nothing(store):
    scan = FakeScan([_jd(1)])
    analyzer = FakeAnalyzer()
    notifier = FakeNotifier()

    result = run_pipeline([scan], store, analyzer, notifier, dry_run=True)

    assert len(result.new) == 1
    assert store.get_job("stepstone", "job-1") is None  # nothing persisted
    assert analyzer.analysed == []
    assert notifier.sent == []


def test_no_analyzer_leaves_jobs_pending_for_a_later_run(store):
    scan = FakeScan([_jd(1)])
    run_pipeline([scan], store)  # like --no-llm
    assert store.get_job("stepstone", "job-1")["status"] == "new"

    # Next run: nothing newly fetched, but the pending job is analysed and notified.
    notifier = FakeNotifier()
    result = run_pipeline([FakeScan([])], store, FakeAnalyzer(), notifier)
    assert result.analysed == 1
    assert result.notified == 1
    assert store.get_job("stepstone", "job-1")["status"] == "notified"


def test_analysis_error_is_isolated(store):
    scan = FakeScan([_jd(1), _jd(2)])
    analyzer = FakeAnalyzer(fail_for={"job-1"})
    notifier = FakeNotifier()

    result = run_pipeline([scan], store, analyzer, notifier)

    assert result.analysed == 1
    assert len(result.errors) == 1 and result.errors[0][0] == "stepstone:job-1"
    assert store.get_job("stepstone", "job-1")["status"] == "error"
    assert store.get_job("stepstone", "job-2")["status"] == "notified"  # digest still sent
    assert result.notified == 1


def test_limit_caps_analysis_per_run(store):
    scan = FakeScan([_jd(1), _jd(2), _jd(3)])
    result = run_pipeline([scan], store, FakeAnalyzer(), FakeNotifier(), limit=1)

    assert result.analysed == 1
    assert result.notified == 1
    remaining = store.get_jobs_by_status("new")
    assert len(remaining) == 2  # picked up by the next run


def test_no_notifier_leaves_jobs_analysed(store):
    scan = FakeScan([_jd(1)])
    result = run_pipeline([scan], store, FakeAnalyzer())  # like --no-email
    assert result.analysed == 1
    assert result.notified == 0
    assert store.get_job("stepstone", "job-1")["status"] == "analysed"
