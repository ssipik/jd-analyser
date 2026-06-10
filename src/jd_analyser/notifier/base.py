"""Notifier abstraction: deliver analysed results to the user."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from jd_analyser.models import JobAnalysis, JobDescription


@dataclass
class DigestItem:
    """A job paired with its analysis, ready for rendering."""

    job: JobDescription
    analysis: JobAnalysis


class Notifier(ABC):
    @abstractmethod
    def send_digest(self, items: list[DigestItem]) -> Any:
        """Deliver a digest of analysed jobs. No-op when there is nothing to send."""
        raise NotImplementedError
