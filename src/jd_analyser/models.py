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


class RecommendedAction(str, Enum):
    """Suggested next step given match + fit."""

    APPLY = "apply"
    MAYBE = "maybe"
    SKIP = "skip"


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
    """Structured assessment of a JobDescription against the user's profile."""

    match_score: int  # 0-100
    summary: str
    pros: list[str]  # requirements the user fulfils
    cons_hard: list[str]  # hard gaps (likely disqualifying)
    cons_soft: list[str]  # soft gaps (nice-to-have / closeable)
    like_verdict: LikeVerdict
    like_rationale: str
    cv_suggestions: list[str]
    cover_letter: str
    recommended_action: RecommendedAction

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable dict (enums flattened to their string values)."""
        d = asdict(self)
        d["like_verdict"] = self.like_verdict.value
        d["recommended_action"] = self.recommended_action.value
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "JobAnalysis":
        return cls(
            match_score=int(d["match_score"]),
            summary=d.get("summary", ""),
            pros=list(d.get("pros", [])),
            cons_hard=list(d.get("cons_hard", [])),
            cons_soft=list(d.get("cons_soft", [])),
            like_verdict=LikeVerdict(d.get("like_verdict", "neutral")),
            like_rationale=d.get("like_rationale", ""),
            cv_suggestions=list(d.get("cv_suggestions", [])),
            cover_letter=d.get("cover_letter", ""),
            recommended_action=RecommendedAction(d.get("recommended_action", "maybe")),
        )
