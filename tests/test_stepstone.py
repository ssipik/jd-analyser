"""Tests for the StepStone parser core (provisional) and StepstoneScan flow.

These pin down the *solid* parts (listing-id extraction, link discovery, the single/multi/
no-link branching). Title/company/full_text association is provisional and will be retuned
against a real captured email.
"""
import pytest

from jd_analyser.interfaces.gmail_api import EmailMessage
from jd_analyser.sources.stepstone import (
    StepstoneScan,
    extract_stepstone_listing_id,
    parse_stepstone_email,
)


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://www.stepstone.de/stellenangebote--Data-Eng-Berlin-ACME--7654321-inline.html", "7654321"),
        ("https://www.stepstone.de/jobs/data-engineer/123456", "123456"),
        ("https://click.stepstone.de/track?rid=9988776&x=1", "9988776"),
        ("https://www.stepstone.de/cmp/de/something", None),
        ("https://example.com/no-id-here", None),
    ],
)
def test_extract_listing_id(url, expected):
    assert extract_stepstone_listing_id(url) == expected


def _email(html: str, text: str = "", subject: str = "StepStone: Data Engineer") -> EmailMessage:
    return EmailMessage(
        id="msg-1",
        thread_id="t1",
        subject=subject,
        sender="StepStone <jobs@stepstone.de>",
        date="Tue, 10 Jun 2026 08:00:00 +0000",
        snippet="...",
        text=text,
        html=html,
    )


def test_single_job_uses_full_body_text():
    html = (
        '<html><body>'
        '<a href="https://www.stepstone.de/stellenangebote--Data-Eng-Berlin--7654321-inline.html">'
        "Data Engineer</a>"
        "<p>We need Python and SQL. Kubernetes is a plus.</p>"
        "</body></html>"
    )
    text = "Data Engineer\nWe need Python and SQL. Kubernetes is a plus."
    jobs = parse_stepstone_email(_email(html, text=text))
    assert len(jobs) == 1
    job = jobs[0]
    assert job.source == "stepstone"
    assert job.external_id == "7654321"
    assert job.title == "Data Engineer"
    assert "Kubernetes is a plus" in job.full_text  # full JD text retained
    assert job.url.endswith("7654321-inline.html")
    assert job.raw_ref == "msg-1"


def test_multiple_jobs_emit_one_each():
    html = (
        "<html><body>"
        '<a href="https://www.stepstone.de/jobs/a/111111">Job A</a>'
        '<a href="https://www.stepstone.de/jobs/b/222222">Job B</a>'
        "</body></html>"
    )
    jobs = parse_stepstone_email(_email(html))
    assert {j.external_id for j in jobs} == {"111111", "222222"}
    assert {j.title for j in jobs} == {"Job A", "Job B"}


def test_no_links_falls_back_to_email_id_and_body():
    jobs = parse_stepstone_email(_email("<p>Some text without a job link.</p>", subject="StepStone: Heads up"))
    assert len(jobs) == 1
    assert jobs[0].external_id == "msg-1"  # dedup per email when no listing id
    assert jobs[0].title == "Heads up"
    assert "without a job link" in jobs[0].full_text


def test_dedup_within_email_by_listing_id():
    html = (
        "<html><body>"
        '<a href="https://www.stepstone.de/jobs/a/333333">First link</a>'
        '<a href="https://click.stepstone.de/t?rid=333333">Same job tracked</a>'
        "</body></html>"
    )
    jobs = parse_stepstone_email(_email(html))
    assert len(jobs) == 1
    assert jobs[0].external_id == "333333"


class FakeGmail:
    def __init__(self, messages):
        self._messages = {m.id: m for m in messages}

    def search(self, query, max_results=50):
        return list(self._messages.keys())[:max_results]

    def get_message(self, msg_id):
        return self._messages[msg_id]


def test_scan_fetches_and_parses():
    msg = _email(
        '<a href="https://www.stepstone.de/jobs/x/444444">Backend Engineer</a><p>Go and gRPC.</p>',
        text="Backend Engineer\nGo and gRPC.",
    )
    scan = StepstoneScan(FakeGmail([msg]), query="from:jobs@stepstone.de")
    jobs = scan.fetch_job_descriptions()
    assert len(jobs) == 1
    assert jobs[0].external_id == "444444"
    assert "gRPC" in jobs[0].full_text
