"""StepstoneScan: turn StepStone alert emails into JobDescriptions.

PROVISIONAL PARSER. The listing-id extraction from URLs is solid and tested, but the
title/company/full-text association depends on StepStone's exact email layout, which must
be confirmed against a real capture (``jd-analyser dump-samples``). Tune `parse_stepstone_email`
once a real sample is in `data/samples/`. The function and its helpers are pure so they can
be unit-tested without Gmail access.
"""
from __future__ import annotations

import re
from typing import Optional

from bs4 import BeautifulSoup

from jd_analyser.interfaces.gmail_api import EmailMessage, GmailAPIInterface
from jd_analyser.models import JobDescription
from jd_analyser.sources.base import JobDescriptionScan

SOURCE = "stepstone"

# Ordered most-specific first. StepStone listing ids are typically 5-9 digits.
_LISTING_ID_PATTERNS = [
    re.compile(r"--(\d{5,})-inline", re.I),  # ...--Title-City-Company--1234567-inline.html
    re.compile(r"[?&](?:rid|listingId|cid|id)=(\d{5,})", re.I),
    re.compile(r"/(\d{6,})(?:[/?#-]|$)"),  # .../jobs/.../1234567
]


def extract_stepstone_listing_id(url: str) -> Optional[str]:
    """Pull the stable listing id out of a StepStone job URL, if present."""
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


def _job_links(html: str) -> list[tuple[str, str, str]]:
    """Return unique (url, anchor_text, listing_id) for StepStone job links in the HTML."""
    soup = BeautifulSoup(html, "html.parser")
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        listing_id = extract_stepstone_listing_id(anchor["href"])
        if listing_id and listing_id not in seen:
            seen.add(listing_id)
            out.append((anchor["href"], anchor.get_text(" ", strip=True), listing_id))
    return out


def _clean_subject(subject: str) -> str:
    s = re.sub(r"^\s*stepstone\s*[:|-]\s*", "", subject, flags=re.I)
    return s.strip()


def parse_stepstone_email(msg: EmailMessage) -> list[JobDescription]:
    """Best-effort extraction of JobDescription(s) from one StepStone alert email.

    NOTE (provisional): single-job emails carry the full JD as clear text per the user, so
    we use the whole body as `full_text`. Multi-job emails fall back to per-link teaser text.
    Refine title/company/full_text association after inspecting a real sample.
    """
    body_text = (msg.text or "").strip() or _html_to_text(msg.html or "")
    links = _job_links(msg.html) if msg.html else []
    subject_title = _clean_subject(msg.subject)

    if not links:
        if not body_text:
            return []
        return [
            JobDescription(
                source=SOURCE,
                external_id=msg.id,  # no listing id found -> dedup per email
                title=subject_title or "(unknown title)",
                company="",
                full_text=body_text,
                url="",
                raw_ref=msg.id,
            )
        ]

    if len(links) == 1:
        url, anchor, listing_id = links[0]
        return [
            JobDescription(
                source=SOURCE,
                external_id=listing_id,
                title=anchor or subject_title or "(unknown title)",
                company="",
                full_text=body_text,
                url=url,
                raw_ref=msg.id,
            )
        ]

    # Multiple jobs in one email — teaser per link until the real layout is known.
    return [
        JobDescription(
            source=SOURCE,
            external_id=listing_id,
            title=anchor or "(unknown title)",
            company="",
            full_text=anchor or body_text,
            url=url,
            raw_ref=msg.id,
        )
        for url, anchor, listing_id in links
    ]


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
            jobs.extend(parse_stepstone_email(msg))
        return jobs
