"""Tests for EmailNotifier: rendering, score ordering, and send behaviour."""
from jd_analyser.models import JobAnalysis, JobDescription, LikeVerdict
from jd_analyser.notifier.base import DigestItem
from jd_analyser.notifier.email_notifier import EmailNotifier


class FakeGmail:
    def __init__(self):
        self.sent = []

    def send(self, to, subject, html):
        self.sent.append({"to": to, "subject": subject, "html": html})
        return {"id": "sent-1"}


def _item(ext, score, title) -> DigestItem:
    job = JobDescription(
        source="stepstone",
        external_id=ext,
        title=title,
        company="ACME",
        full_text="...",
        url=f"https://www.stepstone.de/job-{ext}",
        location="Berlin",
    )
    analysis = JobAnalysis(
        language="de",
        tone="formal",
        profile_used="de",
        fit_score=score - 10,
        combined_score=score,
        summary="Summary line.",
        pros=["Python"],
        cons_hard=["Needs PhD"],
        cons_soft=["No k8s"],
        like_verdict=LikeVerdict.LIKE,
        like_rationale="Remote ok.",
        salary_range="60.000-75.000 €",
        salary_ask="72.000 €",
        cv_edits=[{"old": "Did data.", "new": "Built pipelines."}],
        cover_letter="Dear team,\nI am writing...",
    )
    return DigestItem(job=job, analysis=analysis)


def test_render_contains_fields_and_orders_by_score():
    notifier = EmailNotifier(FakeGmail(), to="me@example.com", threshold=60)
    html = notifier.render([_item("1", 40, "Low Job"), _item("2", 90, "High Job")])
    # Both jobs and their key fields are present.
    assert "High Job" in html and "Low Job" in html
    assert "90% combined" in html and "40% combined" in html
    assert "80% fit" in html  # fit_score badge
    assert "Python" in html  # pro
    assert "Needs PhD" in html  # hard gap
    assert "72.000" in html  # salary ask
    assert "Built pipelines." in html  # cv edit (new sentence)
    assert "Dear team," in html  # cover letter preserved
    # Highest score appears first in the document.
    assert html.index("High Job") < html.index("Low Job")


def test_send_digest_sends_via_gmail():
    gmail = FakeGmail()
    notifier = EmailNotifier(gmail, to="me@example.com", threshold=60)
    result = notifier.send_digest([_item("1", 75, "A Job")])
    assert result == {"id": "sent-1"}
    assert len(gmail.sent) == 1
    assert gmail.sent[0]["to"] == "me@example.com"
    assert "A Job" in gmail.sent[0]["html"]
    assert "1 new job" in gmail.sent[0]["subject"]


def test_send_digest_empty_does_nothing():
    gmail = FakeGmail()
    notifier = EmailNotifier(gmail, to="me@example.com")
    assert notifier.send_digest([]) is None
    assert gmail.sent == []
