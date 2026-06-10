"""Source layer base: every job source produces normalised JobDescriptions."""
from __future__ import annotations

from abc import ABC, abstractmethod

from jd_analyser.models import JobDescription


class JobDescriptionScan(ABC):
    """A source of jobs. Implementations stay pure: fetch + parse only.

    Dedup, persistence, analysis, and orchestration live outside the scan.
    """

    #: Stable source identifier used in JobDescription.source / dedup keys.
    SOURCE: str = ""

    @abstractmethod
    def fetch_job_descriptions(self) -> list[JobDescription]:
        raise NotImplementedError
