"""EmailNotifier: render a Jinja2 HTML digest and send it via Gmail."""
from __future__ import annotations

from datetime import datetime, timezone
from importlib.resources import files
from typing import Any, Optional

from jinja2 import Environment, FileSystemLoader

from jd_analyser.interfaces.gmail_api import GmailAPIInterface
from jd_analyser.notifier.base import DigestItem, Notifier

_TEMPLATES_DIR = str(files("jd_analyser") / "templates")


class EmailNotifier(Notifier):
    def __init__(self, gmail: GmailAPIInterface, to: str, threshold: int = 60):
        self.gmail = gmail
        self.to = to
        self.threshold = threshold
        self.env = Environment(loader=FileSystemLoader(_TEMPLATES_DIR), autoescape=True)

    def render(self, items: list[DigestItem]) -> str:
        ordered = sorted(items, key=lambda i: i.analysis.match_score, reverse=True)
        template = self.env.get_template("digest.html.j2")
        return template.render(
            items=ordered,
            threshold=self.threshold,
            count=len(ordered),
            generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        )

    def send_digest(self, items: list[DigestItem], subject: Optional[str] = None) -> Optional[Any]:
        if not items:
            return None
        html = self.render(items)
        subject = subject or f"JD digest — {len(items)} new job(s)"
        return self.gmail.send(self.to, subject, html)
