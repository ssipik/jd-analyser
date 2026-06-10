# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An AI agent that reads StepStone job-alert emails from a Gmail inbox, keeps only the
*new* postings, scores each against the user's profile via the Anthropic API, and emails
back an HTML digest (match score, pros/cons, like-verdict, CV tips, cover-letter draft).

## Commands

```bash
uv sync                                   # create/refresh the venv from uv.lock
uv run pytest                             # full suite (pure units, no network/credentials)
uv run pytest tests/test_stepstone.py     # one file
uv run pytest tests/test_analyzer.py::test_analyzer_builds_prompt_and_parses_result   # one test
uv run python -m jd_analyser --help       # CLI; `dump-samples` is the only live subcommand
uv run python -m jd_analyser dump-samples # capture real StepStone emails to data/samples/
```

Python is pinned to **3.13.7** (`.python-version`); dependency management is **uv** only —
there is no pip/requirements path. There is no linter/formatter configured.

## Architecture

A layered pipeline with swappable seams. Data flows
`sources → store (dedup) → analyzer → notifier`, and two **transports** (`interfaces/`)
sit underneath. Every layer speaks in the two DTOs from [models.py](src/jd_analyser/models.py):
`JobDescription` (what sources produce; `key = source:external_id` is the dedup identity)
and `JobAnalysis` (the structured LLM verdict).

- **`interfaces/`** — transports, each hidden behind an ABC so implementations swap without
  touching callers. `LLMInterface` → `AnthropicLLM` (uses **forced tool-use** to guarantee
  schema-valid JSON, not text parsing). `GmailAPIInterface` does search/get/send/label; its
  MIME parsing and message-building are **pure module functions** (`extract_bodies`,
  `parse_message`, `build_raw_message`) so they unit-test without credentials. `IndeedMCPInterface`
  is a deferred stub.
- **`sources/`** — `JobDescriptionScan` (ABC) → `StepstoneScan`, `IndeedScan` (stub). Sources
  stay **pure**: fetch + parse → `list[JobDescription]`, nothing else. Dedup, persistence,
  analysis, and orchestration deliberately live *outside* them. Parsing helpers are pure
  functions split from the I/O class for the same testability reason.
- **`store.py`** — `JobStore`, a single-file SQLite DB. Sources return *all* jobs; the store
  decides which are new (`filter_new`) and owns the lifecycle `status`:
  `new → analysed → notified` (or `error`). Also dedups Gmail messages (`processed_messages`).
- **`analyzer.py`** — `JobAnalyzer` builds the system prompt from the user's
  profile/criteria/exceptions, calls `LLMInterface.structured()` with `ANALYSIS_SCHEMA`, and
  returns a `JobAnalysis`. **The schema and `JobAnalysis` must stay in lockstep** — change one,
  change the other (and `from_dict`/`to_dict`).
- **`notifier/`** — `Notifier` (ABC) → `EmailNotifier` renders `templates/digest.html.j2`
  (Jinja2, autoescaped) and sends via the Gmail transport. `DigestItem` pairs a job with its
  analysis. `SCORE_THRESHOLD` only controls digest highlighting, not what gets analysed.

`Settings.load()` ([config.py](src/jd_analyser/config.py)) is the single source of runtime
config, read from `.env`; project paths (`CONFIG_DIR`, `CREDENTIALS_DIR`, `DATA_DIR`) are
derived there too. Pull config through `Settings`, never hard-code secrets or paths.

## Build status — what is NOT wired yet

Phases P0–P5 are built; **P6 (end-to-end pipeline + scheduling) and P7 (Indeed via MCP) are
not**. Consequences for anyone working here:

- The CLI exposes only `dump-samples`. There is **no `run` command** that strings
  scan→store→analyse→notify together yet — that orchestration is P6 and still needs writing.
  New subcommands register in [cli.py](src/jd_analyser/cli.py) via `set_defaults(handler=...)`.
- **`StepstoneScan` is provisional.** Listing-id extraction from URLs is solid and tested, but
  title/company/`full_text` association is a best-effort guess that **must be retuned against a
  real captured email** (`dump-samples` → inspect `data/samples/` → tune `parse_stepstone_email`).
  Don't treat the current parsing of those fields as ground truth.
- `IndeedScan` / `IndeedMCPInterface` raise `NotImplementedError` by design.

## Running live requires user-supplied secrets (all gitignored)

These are not in the repo and tests don't need them, but `dump-samples` / live analysis do:
1. `credentials/client_secret.json` — a Google Cloud **Desktop OAuth client** with the Gmail
   API enabled (scopes `gmail.modify` + `gmail.send`). First run opens a browser and caches
   `credentials/token.json`.
2. `.env` with `ANTHROPIC_API_KEY` (copy `.env.example`).
3. `config/profile.md`, `config/criteria.md`, `config/exceptions.md` (copy the `*.example.md`).
   `profile.md` and `criteria.md` are required by `JobAnalyzer.from_config`; `exceptions.md`
   is optional.

## Testing conventions

Tests inject fakes rather than mocking transports: a `FakeLLM` records prompts/schema and
returns a canned dict; a `FakeGmail` serves prepared `EmailMessage`s. Keep the parse/transport
split intact so new logic stays testable without network or credentials.
