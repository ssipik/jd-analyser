"""Tests for the StepStone filter/parser split and StepstoneScan flow.

Fixtures mirror the real email structure captured in data/samples/ (2026-06): single-job
persona mails carry an <h1> marker, the title in the first <strong>, company/location in
the following <span>s, and an "I'm interested" tracking link; "Stepstone Daily Jobs"
digests are filtered out entirely.
"""
import pytest

from jd_analyser.interfaces.gmail_api import EmailMessage
from jd_analyser.sources.stepstone import (
    StepstoneScan,
    extract_stepstone_listing_id,
    is_single_job_email,
    parse_single_job_email,
)

PERSONA_SENDER = "Emma Jacobs from Stepstone <info@jobagent.stepstone.de>"
DIGEST_SENDER = "Stepstone Daily Jobs <info@jobagent.stepstone.de>"

SINGLE_HTML = (
    "<html><body>"
    "<h1>New Job Opportunity based on your recent search</h1>"
    "<table><tr><td><div><strong>Data Engineer (m/w/d) Platf...</strong></div></td></tr>"
    "<tr><td><span>ACME GmbH</span></td></tr>"
    "<tr><td><span>Berlin</span></td></tr></table>"
    '<a href="https://click.stepstone.de/f/a/OPAQUE-TRACKING~~/">I’m\xa0interested</a>'
    "<h2>Ihre Aufgaben</h2><p>We need Python and SQL. Kubernetes is a plus.</p>"
    "</body></html>"
)
SINGLE_TEXT = (
    "Hi Valentin,\nThis job matches your skills.\n\nData Engineer (m/w/d) Platf...\n\n"
    "ACME GmbH\nBerlin\n\nI'm interested\nhttps://click.stepstone.de/f/a/OPAQUE-TRACKING~~/\n\n"
    "Ihre Aufgaben\nWe need Python and SQL. Kubernetes is a plus.\n"
)
DIGEST_HTML = (
    "<html><body><h1>Picked for you!</h1>"
    "<strong>Job A</strong><span>Company A</span>"
    "<strong>Job B</strong><span>Company B</span>"
    "</body></html>"
)


def _email(
    html: str = "",
    text: str = "",
    subject: str = "Your chances are good for this role",
    sender: str = PERSONA_SENDER,
    msg_id: str = "msg-1",
) -> EmailMessage:
    return EmailMessage(
        id=msg_id,
        thread_id="t1",
        subject=subject,
        sender=sender,
        date="Tue, 10 Jun 2026 08:00:00 +0000",
        snippet="...",
        text=text,
        html=html,
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


# --- filter ----------------------------------------------------------------------------


def test_filter_keeps_single_job_email():
    assert is_single_job_email(_email(html=SINGLE_HTML, text=SINGLE_TEXT))


def test_filter_drops_digest_by_sender_name():
    assert not is_single_job_email(
        _email(html=DIGEST_HTML, sender=DIGEST_SENDER, subject="New job opportunities for you")
    )


def test_filter_drops_html_without_single_job_heading():
    assert not is_single_job_email(_email(html=DIGEST_HTML))


def test_filter_without_html_requires_exactly_one_apply_cta():
    assert is_single_job_email(_email(text=SINGLE_TEXT))
    assert not is_single_job_email(_email(text="No call to action here."))
    assert not is_single_job_email(_email(text="I'm interested\nI'm interested\n"))


# --- parser ----------------------------------------------------------------------------


def test_parse_extracts_fields_from_job_card():
    job = parse_single_job_email(_email(html=SINGLE_HTML, text=SINGLE_TEXT))
    assert job.source == "stepstone"
    assert job.title == "Data Engineer (m/w/d) Platf"  # truncation ellipsis stripped
    assert job.company == "ACME GmbH"
    assert job.location == "Berlin"
    assert job.url == "https://click.stepstone.de/f/a/OPAQUE-TRACKING~~/"
    assert "Kubernetes is a plus" in job.full_text  # full body retained for the analyser
    assert job.raw_ref == "msg-1"


def test_parse_skips_badge_strong_before_title():
    html = SINGLE_HTML.replace(
        "<strong>Data Engineer (m/w/d) Platf...</strong>",
        "<strong>Hot job</strong></div><div><strong>Data Engineer (m/w/d) Platf...</strong>",
    )
    job = parse_single_job_email(_email(html=html, text=SINGLE_TEXT))
    assert job.title == "Data Engineer (m/w/d) Platf"  # badge ignored
    assert job.company == "ACME GmbH"


def test_parse_dedup_id_is_stable_across_resends():
    first = parse_single_job_email(_email(html=SINGLE_HTML, text=SINGLE_TEXT, msg_id="msg-1"))
    resent = parse_single_job_email(_email(html=SINGLE_HTML, text=SINGLE_TEXT, msg_id="msg-2"))
    assert first.external_id == resent.external_id  # same job, different email
    other = parse_single_job_email(
        _email(html=SINGLE_HTML.replace("ACME GmbH", "Other AG"), text=SINGLE_TEXT)
    )
    assert other.external_id != first.external_id


def test_parse_unknown_layout_falls_back_to_message_id():
    job = parse_single_job_email(
        _email(html="<html><body><h1>New Job Opportunity</h1><p>Odd layout.</p></body></html>")
    )
    assert job.external_id == "msg-1"  # dedup per email when no job card found
    assert job.title == "(unknown title)"
    assert "Odd layout" in job.full_text


def test_parse_returns_none_for_empty_body():
    assert parse_single_job_email(_email()) is None


# --- scan ------------------------------------------------------------------------------


class FakeGmail:
    def __init__(self, messages):
        self._messages = {m.id: m for m in messages}

    def search(self, query, max_results=50):
        return list(self._messages.keys())[:max_results]

    def get_message(self, msg_id):
        return self._messages[msg_id]


def test_scan_parses_singles_and_skips_digests():
    single = _email(html=SINGLE_HTML, text=SINGLE_TEXT, msg_id="msg-single")
    digest = _email(html=DIGEST_HTML, sender=DIGEST_SENDER, msg_id="msg-digest")
    scan = StepstoneScan(FakeGmail([single, digest]), query="from:info@jobagent.stepstone.de")
    jobs = scan.fetch_job_descriptions()
    assert len(jobs) == 1
    assert jobs[0].title == "Data Engineer (m/w/d) Platf"
    assert jobs[0].raw_ref == "msg-single"
