"""StepstoneScan: turn StepStone alert emails into JobDescriptions.

Tuned against real captures in ``data/samples/``. StepStone sends two email types, both
from ``info@jobagent.stepstone.de``:

- **Single-job mails** (persona display name such as "Emma Jacobs from Stepstone";
  ``<h1>New Job Opportunity based on your recent search</h1>``): one job card plus the
  *full* job description as clear text. These are the only mails worth analysing.
- **Digests** (display name "Stepstone Daily Jobs"; ``<h1>Picked for you!</h1>``):
  multiple teaser cards without descriptions. Skipped entirely.

Filtering (`is_single_job_email`) and parsing (`parse_single_job_email`) are separate pure
functions so each can be unit-tested without Gmail access; `StepstoneScan` composes them.

All links in these emails are opaque ``click.stepstone.de`` tracking URLs with no listing
id, so dedup uses a content hash of title+company instead. `extract_stepstone_listing_id`
is kept for canonical stepstone.de URLs (e.g. after resolving a tracking redirect later).
"""
from __future__ import annotations

import hashlib
import re
from typing import Optional

from bs4 import BeautifulSoup

from jd_analyser.interfaces.gmail_api import EmailMessage, GmailAPIInterface
from jd_analyser.models import JobDescription
from jd_analyser.sources.base import JobDescriptionScan

SOURCE = "stepstone"

# Markers observed in real captures (see module docstring).
_DIGEST_SENDER_NAME = "stepstone daily jobs"
_SINGLE_JOB_HEADING = "new job opportunity"
_APPLY_CTA = "i'm interested"
# Badge <strong>s that can precede the real title in the job card.
_TITLE_BADGES = {"hot job", "strong fit"}

# Ordered most-specific first. StepStone listing ids are typically 5-9 digits. Only
# meaningful for canonical stepstone.de URLs — the opaque tracking links in alert emails
# never carry an id (and their random blobs could false-match), so don't run this on them.
_LISTING_ID_PATTERNS = [
    re.compile(r"--(\d{5,})-inline", re.I),  # ...--Title-City-Company--1234567-inline.html
    re.compile(r"[?&](?:rid|listingId|cid|id)=(\d{5,})", re.I),
    re.compile(r"/(\d{6,})(?:[/?#-]|$)"),  # .../jobs/.../1234567
]


def extract_stepstone_listing_id(url: str) -> Optional[str]:
    """Pull the stable listing id out of a canonical StepStone job URL, if present."""
    for pattern in _LISTING_ID_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1)
    return None


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    lines = (line.strip() for line in soup.get_text("\n").splitlines())
    return "\n".join(line for line in lines if line)


def _norm(s: str) -> str:
    """Lowercase, unify apostrophes/NBSP, collapse whitespace — for marker comparisons."""
    return " ".join(s.replace("’", "'").replace("\xa0", " ").lower().split())


def _content_id(title: str, company: str) -> str:
    """Stable dedup id derived from content, since email URLs carry no listing id."""
    basis = f"{_norm(title)}|{_norm(company)}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def is_single_job_email(msg: EmailMessage) -> bool:
    """Keep only single-job mails (full JD in the body); drop digests and anything else.

    Deterministic criteria from captured samples: the digest sender display name is an
    immediate reject; otherwise the single-job ``<h1>`` must be present. Mails without an
    HTML part fall back to requiring exactly one apply CTA in the text body.
    """
    if _DIGEST_SENDER_NAME in msg.sender.lower():
        return False
    if msg.html:
        h1 = BeautifulSoup(msg.html, "html.parser").find("h1")
        return h1 is not None and _norm(h1.get_text()).startswith(_SINGLE_JOB_HEADING)
    return _norm(msg.text or "").count(_APPLY_CTA) == 1


def parse_single_job_email(msg: EmailMessage) -> Optional[JobDescription]:
    """Extract the one JobDescription from a single-job mail (filter with is_single_job_email).

    Job-card layout from real captures: title in the first ``<strong>`` that is not a
    badge (some variants lead with a "Hot job" badge; StepStone may truncate the title
    with an ellipsis), then company and location as the next non-empty ``<span>``s, and
    an "I'm interested" apply link. The full JD is the whole body text, so the analyser
    never depends on the extracted fields.
    """
    full_text = (msg.text or "").strip() or _html_to_text(msg.html or "")
    if not full_text:
        return None

    title = company = location = url = ""
    if msg.html:
        soup = BeautifulSoup(msg.html, "html.parser")
        apply_link = next(
            (a for a in soup.find_all("a", href=True) if _norm(a.get_text()) == _APPLY_CTA),
            None,
        )
        if apply_link:
            url = apply_link["href"]
        strong = next(
            (s for s in soup.find_all("strong") if _norm(s.get_text()) not in _TITLE_BADGES),
            None,
        )
        if strong:
            title = strong.get_text(" ", strip=True).rstrip(".…").strip()
            spans = [t for s in strong.find_all_next("span") if (t := s.get_text(" ", strip=True))]
            company = spans[0] if spans else ""
            location = spans[1] if len(spans) > 1 else ""

    if not title:
        # Unexpected layout: keep the mail analysable, dedup per message.
        return JobDescription(
            source=SOURCE,
            external_id=msg.id,
            title="(unknown title)",
            company=company,
            full_text=full_text,
            url=url,
            location=location,
            raw_ref=msg.id,
        )

    return JobDescription(
        source=SOURCE,
        external_id=_content_id(title, company),
        title=title,
        company=company,
        full_text=full_text,
        url=url,
        location=location,
        raw_ref=msg.id,
    )


class StepstoneScan(JobDescriptionScan):
    SOURCE = SOURCE

    def __init__(self, gmail: GmailAPIInterface, query: str, max_messages: int = 25):
        self.gmail = gmail
        self.query = query
        self.max_messages = max_messages

    def fetch_job_descriptions(self) -> list[JobDescription]:
        jobs: list[JobDescription] = []
        for message_id in self.gmail.search(self.query, max_results=self.max_messages):
            msg = self.gmail.get_message(message_id)
            if not is_single_job_email(msg):
                continue
            job = parse_single_job_email(msg)
            if job is not None:
                jobs.append(job)
        return jobs
