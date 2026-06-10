# jd-analyser

An AI agent that scans job descriptions from your inbox, filters to the *new* ones,
scores each against your profile, and emails back an actionable assessment — match
score, pros/cons, a "would I like it" verdict, CV tips, and a cover-letter draft.

## Status

Built incrementally (see `plans/`):

- **P0 Scaffold** ✅ — uv project (Python 3.13.7), domain models, settings, CLI skeleton.
- **P1 Gmail transport + `dump-samples`** — read StepStone alerts, send the digest.
- **P2 `StepstoneScan`** — parse full JDs from alert emails.
- **P3 `JobStore`** — SQLite dedup + history.
- **P4 Analysis** — `AnthropicLLM` + `JobAnalyzer` (structured `JobAnalysis`).
- **P5 `EmailNotifier`** — Jinja2 HTML digest via Gmail.
- *Deferred:* P6 pipeline + scheduling, P7 Indeed (via MCP).

## Setup

```bash
uv sync                     # create the venv from the lockfile
cp .env.example .env        # then fill in ANTHROPIC_API_KEY etc.
cp config/profile.example.md   config/profile.md
cp config/criteria.example.md  config/criteria.md
cp config/exceptions.example.md config/exceptions.md
```

Gmail access needs a Google Cloud **OAuth client (Desktop)** with the Gmail API enabled
(scopes `gmail.modify`, `gmail.send`); download it to `credentials/client_secret.json`.
The first run opens a browser for one-time consent and caches a token in
`credentials/token.json`.

## Usage

```bash
uv run python -m jd_analyser --help
uv run pytest
```

## Architecture

```
interfaces/  GmailAPIInterface · IndeedMCPInterface · LLMInterface→AnthropicLLM   (transport)
sources/     JobDescriptionScan(ABC) → StepstoneScan · IndeedScan                 (sources)
store.py     JobStore (SQLite)                                                    (dedup/history)
analyzer.py  JobAnalyzer (profile+criteria → JobAnalysis)                         (analysis)
notifier/    Notifier(ABC) → EmailNotifier                                        (output)
```

Sources stay pure (fetch + parse → `list[JobDescription]`); dedup, analysis, and
orchestration live outside them.
