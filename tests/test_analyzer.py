"""Tests for the analysis layer: JobAnalyzer (mocked LLM) and AnthropicLLM extraction."""
from types import SimpleNamespace

import pytest

from jd_analyser.analyzer import ANALYSIS_SCHEMA, JobAnalyzer
from jd_analyser.interfaces.anthropic_llm import AnthropicLLM
from jd_analyser.models import JobAnalysis, JobDescription, LikeVerdict

CANNED = {
    "language": "de",
    "tone": "formal",
    "profile_used": "de",
    "fit_score": 72,
    "combined_score": 78,
    "summary": "Good fit overall.",
    "pros": ["Python", "SQL"],
    "cons_hard": [],
    "cons_soft": ["No Kubernetes"],
    "like_verdict": "like",
    "like_rationale": "Hybrid in Düsseldorf, active dev role.",
    "salary_range": "65.000-80.000 €",
    "salary_ask": "78.000 €",
    "cv_edits": [{"old": "Worked with data.", "new": "Built ML pipelines on GCP."}],
    "cover_letter": "Sehr geehrte Damen und Herren, ...",
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
    analyzer = JobAnalyzer(
        llm, request="REQUEST SPEC", profile_en="EN PROFILE", profile_de="DE PROFIL"
    )
    result = analyzer.analyse(_job())

    assert isinstance(result, JobAnalysis)
    assert result.fit_score == 72
    assert result.combined_score == 78
    assert result.language == "de"
    assert result.profile_used == "de"
    assert result.cv_edits == [{"old": "Worked with data.", "new": "Built ML pipelines on GCP."}]
    assert result.like_verdict is LikeVerdict.LIKE

    call = llm.calls[0]
    # request.md content and both profiles are injected into the system prompt.
    assert "REQUEST SPEC" in call["system"]
    assert "EN PROFILE" in call["system"]
    assert "DE PROFIL" in call["system"]
    # The JD text reaches the user prompt, and the schema is forwarded.
    assert "Kubernetes is a plus" in call["user"]
    assert call["schema"] is ANALYSIS_SCHEMA
    assert call["tool_name"] == "job_analysis"


def test_analyzer_without_german_profile_notes_fallback():
    analyzer = JobAnalyzer(FakeLLM(CANNED), request="R", profile_en="EN PROFILE")
    assert "(not provided" in analyzer.build_system_prompt()


def test_analyzer_from_config_reads_files(tmp_path):
    (tmp_path / "request.md").write_text("My request spec", encoding="utf-8")
    (tmp_path / "profile.en.md").write_text("My EN profile", encoding="utf-8")
    (tmp_path / "profile.de.md").write_text("Mein DE Profil", encoding="utf-8")
    analyzer = JobAnalyzer.from_config(FakeLLM(CANNED), config_dir=tmp_path)
    prompt = analyzer.build_system_prompt()
    assert "My request spec" in prompt
    assert "My EN profile" in prompt
    assert "Mein DE Profil" in prompt


def test_analyzer_from_config_german_profile_optional(tmp_path):
    (tmp_path / "request.md").write_text("Spec", encoding="utf-8")
    (tmp_path / "profile.en.md").write_text("EN profile", encoding="utf-8")
    analyzer = JobAnalyzer.from_config(FakeLLM(CANNED), config_dir=tmp_path)
    assert "(not provided" in analyzer.build_system_prompt()


@pytest.mark.parametrize("missing", ["request.md", "profile.en.md"])
def test_analyzer_from_config_missing_required_raises(tmp_path, missing):
    files = {"request.md": "spec", "profile.en.md": "profile"}
    files.pop(missing)
    for name, content in files.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    with pytest.raises(FileNotFoundError, match=missing):
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
