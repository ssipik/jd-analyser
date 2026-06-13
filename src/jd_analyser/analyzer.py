"""JobAnalyzer: score a JobDescription against the user's request.md spec and profiles.

The system prompt is the user's own ``config/request.md`` (instructions + criteria + gap
rules) followed by the CV profiles in both languages; the model picks the profile matching
the JD's language. Output is forced through ANALYSIS_SCHEMA via tool-use. **The schema and
`JobAnalysis` must stay in lockstep** — change one, change the other (and the digest
template that renders the fields).
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
        "language": {
            "type": "string",
            "enum": ["en", "de", "other"],
            "description": "Language of the job description.",
        },
        "tone": {
            "type": "string",
            "description": "Tone of the JD, e.g. 'formal' or 'casual'; steers the cover letter.",
        },
        "profile_used": {
            "type": "string",
            "enum": ["en", "de"],
            "description": "Which user profile language was matched against the JD. If no "
            "profile in the JD's language exists, use the English one and note it in the summary.",
        },
        "fit_score": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100,
            "description": "How well the user profile matches the JD's hard and soft "
            "requirements, applying the gap rules and DISREGARDING personal preferences.",
        },
        "combined_score": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100,
            "description": "How well the user profile AND the personal preference criteria "
            "match the JD.",
        },
        "summary": {"type": "string", "description": "Two or three sentences on overall fit."},
        "pros": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Strong points in the user profile for this specific JD.",
        },
        "cons_hard": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Hard gaps (needed by the JD, likely disqualifying).",
        },
        "cons_soft": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Soft gaps (nice-to-have / closeable per the gap rules).",
        },
        "like_verdict": {
            "type": "string",
            "enum": ["like", "neutral", "dislike"],
            "description": "Whether the user would WANT this job per the criteria "
            "(independent of whether they qualify).",
        },
        "like_rationale": {"type": "string"},
        "salary_range": {
            "type": "string",
            "description": "Expected annual gross salary range; base it on the JD's own range "
            "when stated, otherwise estimate and say so.",
        },
        "salary_ask": {
            "type": "string",
            "description": "Recommended salary to ask for, per the salary instructions.",
        },
        "cv_edits": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "old": {"type": "string", "description": "Exact existing sentence from the CV."},
                    "new": {"type": "string", "description": "Truthful replacement sentence."},
                },
                "required": ["old", "new"],
            },
            "description": "Exact edits to the CV version matching the JD's language "
            "(old sentence -> new sentence). Truthful changes only; keep the existing tone.",
        },
        "cover_letter": {
            "type": "string",
            "description": "Tailored cover-letter draft in the JD's language.",
        },
    },
    "required": [
        "language",
        "tone",
        "profile_used",
        "fit_score",
        "combined_score",
        "summary",
        "pros",
        "cons_hard",
        "cons_soft",
        "like_verdict",
        "like_rationale",
        "salary_range",
        "salary_ask",
        "cv_edits",
        "cover_letter",
    ],
}

_SYSTEM_TEMPLATE = """\
{request}

=== USER PROFILE (English) ===
{profile_en}

=== USER PROFILE (German) ===
{profile_de}
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
    def __init__(self, llm: LLMInterface, request: str, profile_en: str, profile_de: str = ""):
        self.llm = llm
        self.request = request.strip()
        self.profile_en = profile_en.strip()
        self.profile_de = profile_de.strip() or "(not provided — use the English profile)"

    @classmethod
    def from_config(cls, llm: LLMInterface, config_dir: Path = CONFIG_DIR) -> "JobAnalyzer":
        config_dir = Path(config_dir)
        request = _require_file(config_dir / "request.md")
        profile_en = _require_file(config_dir / "profile.en.md")
        de_path = config_dir / "profile.de.md"
        profile_de = de_path.read_text(encoding="utf-8") if de_path.exists() else ""
        return cls(llm, request, profile_en, profile_de)

    def build_system_prompt(self) -> str:
        return _SYSTEM_TEMPLATE.format(
            request=self.request, profile_en=self.profile_en, profile_de=self.profile_de
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
        example = path.with_name(path.name.replace(".md", ".example.md"))
        hint = f" Copy {example.name} and fill it in." if example.exists() else ""
        raise FileNotFoundError(f"Missing {path.name} at {path}.{hint}")
    return path.read_text(encoding="utf-8")
