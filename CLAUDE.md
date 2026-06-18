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
uv run python -m jd_analyser --help       # CLI overview
uv run python -m jd_analyser dump-samples # capture real StepStone emails to data/samples/
uv run python -m jd_analyser run --dry-run            # scan + dedup report, change nothing
uv run python -m jd_analyser run --limit 1 --no-email # analyse one job, skip the digest
uv run python -m jd_analyser run          # full pipeline: scan → analyse → email digest
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
  analysis, and orchestration deliberately live *outside* them. Filtering
  (`is_single_job_email`) and parsing (`parse_single_job_email`) are pure module functions
  split from the I/O class, tuned against real captures in `data/samples/`: only StepStone's
  single-job "persona" mails are processed (full JD in the body); "Stepstone Daily Jobs"
  digests are skipped. Email links are opaque tracking URLs, so `external_id` is a content
  hash of title+company, not a listing id.
- **`pipeline.py`** — `run_pipeline(scans, store, analyzer, notifier)`, the P6 orchestrator.
  Status-driven and resumable: the analysis pass picks up everything still `new` (also
  leftovers from `--no-llm`/crashed runs), the notify pass digests everything `analysed`;
  re-running never re-bills the LLM. All components injectable for tests.
- **`store.py`** — `JobStore`, a single-file SQLite DB. Sources return *all* jobs; the store
  decides which are new (`filter_new`) and owns the lifecycle `status`:
  `new → analysed → notified` (or `error`). Also dedups Gmail messages (`processed_messages`).
- **`analyzer.py`** — `JobAnalyzer` builds the system prompt from the user's
  `config/request.md` (instructions + criteria + gap rules, authored by the user) plus the
  CV profiles in both languages (`profile.en.md` required, `profile.de.md` optional; the
  model matches the profile to the JD's language), calls `LLMInterface.structured()` with
  `ANALYSIS_SCHEMA`, and returns a `JobAnalysis` (language, tone, fit_score + combined_score,
  pros/gaps, like-verdict, salary range/ask, old→new CV edits, cover letter — deliberately
  **no** recommended action; the user decides). **The schema and `JobAnalysis` must stay in
  lockstep** — change one, change the other (and `from_dict`/`to_dict` and the digest template).
- **`notifier/`** — `Notifier` (ABC) → `EmailNotifier` renders `templates/digest.html.j2`
  (Jinja2, autoescaped) and sends via the Gmail transport. `DigestItem` pairs a job with its
  analysis. `SCORE_THRESHOLD` only controls digest highlighting, not what gets analysed.

`Settings.load()` ([config.py](src/jd_analyser/config.py)) is the single source of runtime
config, read from `.env`; project paths (`CONFIG_DIR`, `CREDENTIALS_DIR`, `DATA_DIR`) are
derived there too. Pull config through `Settings`, never hard-code secrets or paths.

- **`tracing.py`** — `enable_tracing(uri, experiment)` points MLflow at the tracking server
  and calls `mlflow.anthropic.autolog()`, which patches the Anthropic SDK so **every**
  `messages.create` (prompt, tools, response, tokens, latency) is captured as a trace —
  including failed calls. `cmd_run` enables it before building `AnthropicLLM` when
  `MLFLOW_TRACING` is on (default; URI `http://localhost:5000`, experiment `jd-analyser`).
  It is idempotent and **fails soft**: an unreachable server never breaks the pipeline.

## Build status — what is NOT wired yet

Phases P0–P6 are built (the `run` pipeline included; StepStone parsing is tuned against real
captures and no longer provisional). Still open:

- **Scheduling** (the cron/systemd half of P6): nothing triggers `run` automatically yet;
  the plan suggests `0 8 * * * uv run python -m jd_analyser run`. Logging goes to stdout.
- **P7 (Indeed)**: `IndeedScan` / `IndeedMCPInterface` raise `NotImplementedError` by design.
- New subcommands register in [cli.py](src/jd_analyser/cli.py) via `set_defaults(handler=...)`.
- StepStone email layouts can drift: if titles/companies start looking wrong, re-run
  `dump-samples` and retune `parse_single_job_email` / `is_single_job_email` against the
  fresh captures (that's how the "Hot job" badge variant was handled).

## Running live requires user-supplied secrets (all gitignored)

These are not in the repo and tests don't need them, but `dump-samples` / live analysis do:
1. `credentials/client_secret.json` — a Google Cloud **Desktop OAuth client** with the Gmail
   API enabled (scopes `gmail.modify` + `gmail.send`). First run opens a browser and caches
   `credentials/token.json`.
2. `.env` with `ANTHROPIC_API_KEY` (copy `.env.example`).
3. `config/request.md` (analysis instructions + personal criteria; copy `request.example.md`)
   and `config/profile.en.md` (CV; copy `profile.example.md`) — both required by
   `JobAnalyzer.from_config`. `config/profile.de.md` is optional (used for German JDs).
   The former `criteria.md`/`exceptions.md` are retired — their content lives in `request.md`.

## Testing conventions

Tests inject fakes rather than mocking transports: a `FakeLLM` records prompts/schema and
returns a canned dict; a `FakeGmail` serves prepared `EmailMessage`s. Keep the parse/transport
split intact so new logic stays testable without network or credentials.
