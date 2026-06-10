"""Tests for the analysis layer: JobAnalyzer (mocked LLM) and AnthropicLLM extraction."""
from types import SimpleNamespace

import pytest

from jd_analyser.analyzer import ANALYSIS_SCHEMA, JobAnalyzer
from jd_analyser.interfaces.anthropic_llm import AnthropicLLM
from jd_analyser.models import JobAnalysis, JobDescription, LikeVerdict, RecommendedAction

CANNED = {
    "match_score": 78,
    "summary": "Good fit overall.",
    "pros": ["Python", "SQL"],
    "cons_hard": [],
    "cons_soft": ["No Kubernetes"],
    "like_verdict": "like",
    "like_rationale": "Remote-friendly and product-focused.",
    "cv_suggestions": ["Emphasise data pipelines"],
    "cover_letter": "Sehr geehrte Damen und Herren, ...",
    "recommended_action": "apply",
}


class FakeLLM:
    """Records the prompts/schema it was called with and returns a canned dict."""

    def __init__(self, result):
        self.result = result
        self.calls = []

    def structured(self, *, system, user, schema, tool_name="result"):
        self.calls.append({"system": system, "user": user, "schema": schema, "tool_name": tool_name})
        return self.result


def _job() -> JobDescription:
    return JobDescription(
        source="stepstone",
        external_id="42",
        title="Data Engineer",
        company="ACME",
        full_text="We need strong Python and SQL; Kubernetes is a plus.",
        url="https://www.stepstone.de/job-42",
        location="Berlin",
    )


def test_analyzer_builds_prompt_and_parses_result():
    llm = FakeLLM(CANNED)
    analyzer = JobAnalyzer(llm, profile="10y Python, SQL.", criteria="Wants remote.", exceptions="GCP counts as cloud.")
    result = analyzer.analyse(_job())

    assert isinstance(result, JobAnalysis)
    assert result.match_score == 78
    assert result.like_verdict is LikeVerdict.LIKE
    assert result.recommended_action is RecommendedAction.APPLY

    call = llm.calls[0]
    # Profile, criteria and exceptions are injected into the system prompt.
    assert "10y Python, SQL." in call["system"]
    assert "Wants remote." in call["system"]
    assert "GCP counts as cloud." in call["system"]
    # The JD text reaches the user prompt, and the schema is forwarded.
    assert "Kubernetes is a plus" in call["user"]
    assert call["schema"] is ANALYSIS_SCHEMA
    assert call["tool_name"] == "job_analysis"


def test_analyzer_from_config_reads_files(tmp_path):
    (tmp_path / "profile.md").write_text("My profile", encoding="utf-8")
    (tmp_path / "criteria.md").write_text("My criteria", encoding="utf-8")
    # exceptions.md intentionally absent -> optional
    analyzer = JobAnalyzer.from_config(FakeLLM(CANNED), config_dir=tmp_path)
    assert "My profile" in analyzer.build_system_prompt()
    assert analyzer.exceptions == "(none provided)"


def test_analyzer_from_config_missing_profile_raises(tmp_path):
    (tmp_path / "criteria.md").write_text("c", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="profile.md"):
        JobAnalyzer.from_config(FakeLLM(CANNED), config_dir=tmp_path)


def test_anthropic_llm_extracts_tool_use():
    tool_block = SimpleNamespace(type="tool_use", name="job_analysis", input=CANNED)
    text_block = SimpleNamespace(type="text", text="ignore me")
    fake_response = SimpleNamespace(content=[text_block, tool_block])

    class FakeMessages:
        def create(self, **kwargs):
            FakeMessages.kwargs = kwargs
            return fake_response

    fake_client = SimpleNamespace(messages=FakeMessages())
    llm = AnthropicLLM(api_key="", model="claude-sonnet-4-6", client=fake_client)
    out = llm.structured(system="s", user="u", schema=ANALYSIS_SCHEMA, tool_name="job_analysis")

    assert out == CANNED
    # Forced tool choice is set correctly.
    assert FakeMessages.kwargs["tool_choice"] == {"type": "tool", "name": "job_analysis"}
    assert FakeMessages.kwargs["tools"][0]["input_schema"] is ANALYSIS_SCHEMA


def test_anthropic_llm_requires_key_without_client():
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        AnthropicLLM(api_key="", model="claude-sonnet-4-6")
