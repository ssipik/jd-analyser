"""Domain models shared across sources, storage, analysis, and notification.

`JobDescription` is the common contract every source must produce; `JobAnalysis`
is the structured assessment the LLM returns for each one.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LikeVerdict(str, Enum):
    """Whether the user would *want* this job, per their criteria."""

    LIKE = "like"
    NEUTRAL = "neutral"
    DISLIKE = "dislike"


@dataclass
class JobDescription:
    """Normalised job posting produced by every source (source-agnostic DTO)."""

    source: str  # e.g. "stepstone" | "indeed"
    external_id: str  # stable id within the source; used as the dedup key
    title: str
    company: str
    full_text: str
    url: str = ""
    location: str = ""
    posted_at: Optional[datetime] = None
    fetched_at: datetime = field(default_factory=_utcnow)
    raw_ref: str = ""  # provenance, e.g. the Gmail message id this JD came from
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        """Globally unique key across sources."""
        return f"{self.source}:{self.external_id}"


# FUTURE: JobAnalysis largely mirrors analyzer.ANALYSIS_SCHEMA and adds to_dict/from_dict
# boilerplate. Since the LLM already returns structured JSON, this could be dropped in favour
# of passing the validated dict around directly. Kept for now. (JobDescription stays — it's the
# source-agnostic DTO contract, not LLM-derived.)
@dataclass
class JobAnalysis:
    """Structured assessment of a JobDescription, per the user's config/request.md spec.

    No recommended_action by design: the user decides apply/skip themselves.
    """

    language: str  # JD language: "en" | "de" | "other"
    tone: str  # e.g. "formal" / "casual"; steers the cover letter
    profile_used: str  # which profile language was matched: "en" | "de"
    fit_score: int  # 0-100, profile vs JD requirements, preferences excluded
    combined_score: int  # 0-100, profile AND preference criteria
    summary: str
    pros: list[str]  # strong points in the user profile for this JD
    cons_hard: list[str]  # hard gaps (likely disqualifying)
    cons_soft: list[str]  # soft gaps (nice-to-have / closeable)
    like_verdict: LikeVerdict
    like_rationale: str
    salary_range: str  # expected annual gross range
    salary_ask: str  # recommended ask
    cv_edits: list[dict[str, str]]  # exact edits: {"old": ..., "new": ...}
    cover_letter: str

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable dict (enums flattened to their string values)."""
        d = asdict(self)
        d["like_verdict"] = self.like_verdict.value
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "JobAnalysis":
        return cls(
            language=d.get("language", ""),
            tone=d.get("tone", ""),
            profile_used=d.get("profile_used", ""),
            fit_score=int(d["fit_score"]),
            combined_score=int(d["combined_score"]),
            summary=d.get("summary", ""),
            pros=list(d.get("pros", [])),
            cons_hard=list(d.get("cons_hard", [])),
            cons_soft=list(d.get("cons_soft", [])),
            like_verdict=LikeVerdict(d.get("like_verdict", "neutral")),
            like_rationale=d.get("like_rationale", ""),
            salary_range=d.get("salary_range", ""),
            salary_ask=d.get("salary_ask", ""),
            cv_edits=[dict(e) for e in d.get("cv_edits", [])],
            cover_letter=d.get("cover_letter", ""),
        )
