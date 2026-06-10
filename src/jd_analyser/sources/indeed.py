"""IndeedScan — deferred to P7.

Kept as a stub behind the JobDescriptionScan ABC so the pipeline can treat Indeed as a
peer source once the MCP shape is known.
"""
from __future__ import annotations

from typing import Optional

from jd_analyser.interfaces.indeed_mcp import IndeedMCPInterface
from jd_analyser.models import JobDescription
from jd_analyser.sources.base import JobDescriptionScan


class IndeedScan(JobDescriptionScan):
    SOURCE = "indeed"

    def __init__(self, mcp: Optional[IndeedMCPInterface] = None):
        self.mcp = mcp

    def fetch_job_descriptions(self) -> list[JobDescription]:
        raise NotImplementedError("IndeedScan is deferred to P7 (Indeed MCP).")
