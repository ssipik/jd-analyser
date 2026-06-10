"""JobAnalyzer: score a JobDescription against the user's profile, criteria & exceptions.

Builds the prompt, calls the swappable LLMInterface with a forced JSON schema, and
returns a structured JobAnalysis. The schema mirrors `JobAnalysis` exactly.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from jd_analyser.config import CONFIG_DIR
from jd_analyser.interfaces.llm import LLMInterface
from jd_analyser.models import JobAnalysis, JobDescription

ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "match_score": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100,
            "description": "How well the candidate's profile matches the job's hard and soft "
            "requirements (0-100), honouring the exceptions.",
        },
        "summary": {"type": "string", "description": "Two or three sentences on overall fit."},
        "pros": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Concrete requirements the candidate clearly fulfils.",
        },
        "cons_hard": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Hard gaps that are likely disqualifying.",
        },
        "cons_soft": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Soft / closeable gaps (nice-to-haves).",
        },
        "like_verdict": {
            "type": "string",
            "enum": ["like", "neutral", "dislike"],
            "description": "Whether the candidate would WANT this job per their criteria "
            "(independent of whether they qualify).",
        },
        "like_rationale": {"type": "string"},
        "cv_suggestions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Specific, honest tweaks to the CV to better match THIS job. "
            "Never fabricate qualifications.",
        },
        "cover_letter": {
            "type": "string",
            "description": "A concise, tailored cover-letter draft in the JD's language.",
        },
        "recommended_action": {"type": "string", "enum": ["apply", "maybe", "skip"]},
    },
    "required": [
        "match_score",
        "summary",
        "pros",
        "cons_hard",
        "cons_soft",
        "like_verdict",
        "like_rationale",
        "cv_suggestions",
        "cover_letter",
        "recommended_action",
    ],
}

_SYSTEM_TEMPLATE = """\
You are a meticulous career assistant helping ONE specific candidate decide whether to \
apply to a job. Be honest and concrete; never invent qualifications the candidate does not have.

=== CANDIDATE PROFILE ===
{profile}

=== CANDIDATE CRITERIA (what makes a role enjoyable for them) ===
{criteria}

=== EXCEPTIONS / CLARIFICATIONS (override a naive reading of the profile) ===
{exceptions}

Scoring guidance:
- match_score reflects fit against the job's hard AND soft requirements, honouring the exceptions.
- Separate "can I get it" (match/pros/cons) from "do I want it" (like_verdict per the criteria).
- cv_suggestions must be truthful tweaks (rephrasing, emphasis, ordering) — no fabrication.
- Write the cover_letter in the same language as the job description.
"""

_USER_TEMPLATE = """\
Assess this job posting for the candidate.

Title: {title}
Company: {company}
Location: {location}
URL: {url}

--- JOB DESCRIPTION ---
{full_text}
"""


class JobAnalyzer:
    def __init__(self, llm: LLMInterface, profile: str, criteria: str, exceptions: str = ""):
        self.llm = llm
        self.profile = profile.strip()
        self.criteria = criteria.strip()
        self.exceptions = exceptions.strip() or "(none provided)"

    @classmethod
    def from_config(cls, llm: LLMInterface, config_dir: Path = CONFIG_DIR) -> "JobAnalyzer":
        config_dir = Path(config_dir)
        profile = _require_file(config_dir / "profile.md")
        criteria = _require_file(config_dir / "criteria.md")
        exceptions_path = config_dir / "exceptions.md"
        exceptions = exceptions_path.read_text(encoding="utf-8") if exceptions_path.exists() else ""
        return cls(llm, profile, criteria, exceptions)

    def build_system_prompt(self) -> str:
        return _SYSTEM_TEMPLATE.format(
            profile=self.profile, criteria=self.criteria, exceptions=self.exceptions
        )

    def build_user_prompt(self, job: JobDescription) -> str:
        return _USER_TEMPLATE.format(
            title=job.title,
            company=job.company,
            location=job.location or "(unspecified)",
            url=job.url or "(none)",
            full_text=job.full_text,
        )

    def analyse(self, job: JobDescription) -> JobAnalysis:
        data = self.llm.structured(
            system=self.build_system_prompt(),
            user=self.build_user_prompt(job),
            schema=ANALYSIS_SCHEMA,
            tool_name="job_analysis",
        )
        return JobAnalysis.from_dict(data)


def _require_file(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path.name} at {path}. Copy {path.name.replace('.md', '.example.md')} "
            "and fill it in."
        )
    return path.read_text(encoding="utf-8")
