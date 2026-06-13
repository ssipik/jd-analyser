# Plan: JD Analyser — AI agent to scan, analyse & filter job descriptions

## Context

The user wants an AI agent (running on a Linux/WSL box) that automatically pulls job
descriptions from their inbox/services, filters to *new* ones, scores each against their
profile, and emails back an actionable assessment (match score, pros/cons, "would I like
it" verdict, CV tips, cover-letter draft) — so they only spend effort on jobs worth applying to.

**Sources**
- **StepStone** job-suggestion emails in Gmail (pre-filtered by StepStone; the user's criteria
  are stricter). Confirmed: **each alert email contains the full JD as clear text**, so the full
  posting is analysed directly from the email body — no scraping/link-following needed.
- **Indeed** via an Indeed MCP — capabilities/auth still unknown, so it is **deferred to a later
  phase** behind a stub, without blocking the StepStone pipeline.

**Settled design decisions** (from planning discussion)
- LLM interface: **Anthropic API** (`anthropic` Python SDK) with structured tool/JSON output —
  deterministic, simplest deps. Kept swappable behind an `LLMInterface` ABC.
- Output: **Email digest** sent back via Gmail (reuses the Gmail auth we already need).
- JD depth: analyse the **entire** StepStone JD text from the email; Indeed depth TBD.
- Storage/dedup: **SQLite** (Python stdlib `sqlite3`; no install needed).
- Stack: **Python pinned to 3.13.7, managed by `uv`** (assume `uv` is installed; all deps added
  via `uv add`, all commands run via `uv run`). Node is *not* installed — another reason the
  Anthropic API path is preferred over the Agent-SDK/CLI path for the MVP.

## Architecture

Layered, with the user's source/transport separation as the backbone:

```
Transport/Interface  GmailAPIInterface   IndeedMCPInterface   LLMInterface(ABC)→AnthropicLLM
        ▲                    ▲                   ▲                       ▲
Sources           JobDescriptionScan(ABC) → StepstoneScan | IndeedScan(stub)
        │  fetch_job_descriptions() -> list[JobDescription]
        ▼
Pipeline ⇄ JobStore(SQLite)  →  JobAnalyzer (profile+criteria) → JobAnalysis
                                            ▼
                              Notifier(ABC) → EmailNotifier (reuses GmailAPIInterface.send)
```

Flow per run: for each source → `fetch_job_descriptions()` → `JobStore.filter_new()` →
`JobAnalyzer.analyse()` → `JobStore.save()` → `EmailNotifier.send_digest()`.
Scans stay *pure* (fetch + parse only); dedup/state/orchestration live outside them.

### Key components
- **`models.py`** — `JobDescription` dataclass (`source, external_id, url, title, company,
  location, full_text, posted_at, fetched_at, raw_ref`) and `JobAnalysis` dataclass
  (`match_score:int 0-100, summary, pros[], cons_hard[], cons_soft[], like_verdict,
  like_rationale, cv_suggestions[], cover_letter, recommended_action`).
- **`interfaces/gmail_api.py` — `GmailAPIInterface`**: OAuth2 desktop flow; methods
  `search(query)`, `get_message(id)`, `send(to, subject, html)`, `mark_processed(id)` (Gmail
  label e.g. `JD-Analyser/Processed`). Reusable for any email source *and* the notifier.
  Scopes: `gmail.modify` + `gmail.send`. Token cached in `credentials/token.json`, auto-refreshed.
- **`interfaces/indeed_mcp.py` — `IndeedMCPInterface`**: thin wrapper; **stub** until MCP is known.
- **`interfaces/llm.py` — `LLMInterface` (ABC)** + **`anthropic_llm.py` — `AnthropicLLM`**:
  wraps the `anthropic` client; structured output via tool-use (`tools=[{name, input_schema}]`,
  `tool_choice` forced) → parsed `JobAnalysis`. Model configurable; default `claude-sonnet-4-6`
  (quality/cost balance), `claude-opus-4-8` opt-in for max quality.
- **`sources/base.py` — `JobDescriptionScan` (ABC)**: `fetch_job_descriptions() -> list[JobDescription]`.
- **`sources/stepstone.py` — `StepstoneScan`**: composes an injected `GmailAPIInterface`; searches
  by StepStone sender/subject, parses each message body (handle one-*or-many* JDs per email),
  extracts `external_id` from the listing URL (numeric id / query param), builds `JobDescription`.
- **`sources/indeed.py` — `IndeedScan`**: stub raising `NotImplementedError` for now.
- **`store.py` — `JobStore`**: SQLite. Tables: `jobs` (unique on `source+external_id`: url, title,
  company, status[new|analysed|notified|error], analysis JSON, score, timestamps) and
  `processed_messages` (Gmail message ids already parsed). `filter_new()`, `save_*()`.
- **`analyzer.py` — `JobAnalyzer`**: loads `config/profile.md`, `config/criteria.md`,
  `config/exceptions.md`; builds the prompt; calls `LLMInterface`; returns `JobAnalysis`.
- **`notifier/email_notifier.py` — `EmailNotifier`**: renders a Jinja2 HTML digest
  (`templates/digest.html.j2`) sorted by score desc (threshold configurable), one section per
  job with pros/cons, CV tips and cover-letter draft; sends via `GmailAPIInterface.send`.
- **`pipeline.py` + `__main__.py`** — orchestrator + CLI: `run`, `dump-samples`, `--dry-run`
  (write report to disk instead of emailing), `--limit N`, `--no-llm`.

### Project layout
```
jd-analyser/
  pyproject.toml          # managed by uv; deps: anthropic, google-api-python-client,
  uv.lock                 #   google-auth-oauthlib, google-auth-httplib2, jinja2,
  .python-version         #   beautifulsoup4, python-dotenv; dev: pytest. Pinned to 3.13.7.
  .env                    # ANTHROPIC_API_KEY, GMAIL_QUERY, SCORE_THRESHOLD, MODEL, paths
  .gitignore              # .env, credentials/, data/, .venv/, __pycache__
  README.md               # setup + run instructions
  config/  profile.md  criteria.md  exceptions.md   # user-provided later
  credentials/  client_secret.json  token.json      # gitignored
  data/  jobs.db                                     # gitignored
  src/jd_analyser/  (modules above)  templates/digest.html.j2
  tests/  fixtures/stepstone_sample.eml  test_*.py
```

## Build phases
- **P0 — Scaffold**: `uv init` the project and `uv python pin 3.13.7`; add all deps via `uv add`
  (anthropic, google-api-python-client, google-auth-oauthlib, google-auth-httplib2, jinja2,
  beautifulsoup4, python-dotenv) + `uv add --dev pytest`; create layout, `.env`/`.gitignore`,
  `models.py` dataclasses. All later commands run via `uv run`.
- **P1 — Gmail transport + samples**: `GmailAPIInterface` (auth/search/get/send/label) + CLI
  `dump-samples` to capture *real* StepStone emails — drives the parser against reality.
- **P2 — StepStone source**: `StepstoneScan` parsing full JD(s) → `JobDescription`; unit-tested
  against the captured `.eml` fixture.
- **P3 — Store**: `JobStore` SQLite dedup + history (in-memory db tests).
- **P4 — Analysis**: `LLMInterface`/`AnthropicLLM`, `JobAnalyzer`, `JobAnalysis` tool-use schema;
  tested with a mocked LLM (assert prompt carries profile+JD; parse canned JSON).
- **P5 — Notifier**: `EmailNotifier` + Jinja2 digest template via Gmail send.

### Deferred to later (out of current scope)
- **P6 — Pipeline + scheduling**: orchestrate the components end-to-end; `--dry-run/--limit/--no-llm`;
  cron (`0 8 * * * uv run python -m jd_analyser run`) or systemd timer; logging to file.
  *(Done 2026-06-12 — `pipeline.py` + `run` command, status-driven/resumable; scheduling still open.)*
- **P6.5 — request.md prompt integration** *(agreed & built 2026-06-13; salary wording still to be
  tuned by the user in request.md — config-only change)*: `config/request.md` replaces the built-in
  system template + `criteria.md`/`exceptions.md` (both retired, examples deleted) as the analysis
  prompt. Decisions:
  - **Multi-language profiles confirmed**: user maintains both → `config/profile.en.md` +
    `config/profile.de.md`; loader change in `JobAnalyzer.from_config`; model matches the profile
    to the JD language (English fallback + note).
  - **No `recommended_action`** in the new output — the user decides himself (drop from schema).
  - New output fields (language, tone, fit_score + combined_score, salary range/ask, structured
    old→new CV edits) require `ANALYSIS_SCHEMA` + `JobAnalysis` + digest template to change in
    lockstep.
  - **Salary instruction needs tuning** (user wants to think about it): current text bases the
    estimate on the JD range (treated as conservative) or ~80-85k current salary; the
    direction/meaning of the "recommended ask" is still ambiguous — revisit wording before wiring.
- **P7 — Indeed**: implement `IndeedMCPInterface` + `IndeedScan` once the MCP shape is known.
- **P8 — Source-onboarding agent** *(agreed 2026-06-11; resume only after the current version
  — P6, then P7 — is done)*: an agentic flow for adding new job sources (LinkedIn etc.),
  tiered by how much already exists:
  - **Tier 0 — known source**: implementation exists → agent only configures + validates it.
  - **Tier 1 — new source, known pattern**: clone the proven skeleton (email-alert scan à la
    StepStone, or MCP à la Indeed) and generate only the new parser/field-mapping.
  - **Tier 2 — new source, novel transport**: supervised from-scratch attempt.

  Up front, a research step surveys the integration options (API / MCP / email alerts / other)
  and presents a recommendation the **user** chooses from — official API > email alerts >
  scraping, with ToS problems flagged (e.g. LinkedIn forbids scraping and has no public
  job-search API, so its viable path is email alerts).

  **Form: start as a dev-loop Claude Code skill** (e.g. `/add-source <board>`) rather than an
  in-app agent — it reuses CLAUDE.md context and the test suite, and the human is the review
  gate. Promote to an in-app version (Claude Agent SDK) only if runtime self-service is ever
  actually needed.

  Hard requirements regardless of form:
  1. **Verification gate** — a generated source must pass the unit suite *and* a live smoke
     test (parse real captured samples / fetch one real listing into sane `JobDescription`s)
     before activation; until then it is quarantined (nothing analysed or notified from it).
  2. **Human diff review before install** — generated code runs with Gmail tokens & API keys.
  3. **Registry** — `config/sources.yaml` mapping source name → implementation, read by the
     deterministic pipeline; the agent's entire output is "new module + registry entry".
  4. **Rot loop** — a source that starts yielding zero jobs or parse errors is flagged for the
     agent to re-derive; recurring repair is where the agent earns its keep.

  Highest-leverage variant: a **parser-deriving agent** over the email-alert path (subscribe to
  any board's alert emails → `dump-samples` → agent derives `parse_X_email` + tests from the
  captured HTML). This generalises to every board that can send email and also de-fragilises
  today's hand-tuned `parse_stepstone_email`.

## Prerequisites the user must supply
1. **Google Cloud OAuth client** (Desktop) for Gmail API → `credentials/client_secret.json`
   (enable Gmail API; scopes `gmail.modify`, `gmail.send`). First run does a one-time browser
   consent (on WSL, copy-paste the local-server URL if a browser doesn't auto-open).
2. **`ANTHROPIC_API_KEY`** in `.env`.
3. **`config/profile.md`, `config/criteria.md`, `config/exceptions.md`** (CV/profile, "would I
   like it" criteria, and exception notes). Can be filled after scaffolding.
4. One **sample StepStone alert email** is needed to finalise the parser — captured automatically
   by the P1 `dump-samples` command (so no manual export required).

## Verification (per component, P0–P5)
- **Unit** (`uv run pytest`): StepStone parser vs `.eml` fixture; `JobStore` dedup (re-running the
  same input adds nothing new); `JobAnalyzer` with a mocked `LLMInterface`.
- **Gmail (P1)**: `uv run python -m jd_analyser dump-samples` → completes OAuth and saves real
  StepStone emails to disk for inspection; verify a `JD-Analyser/Processed` label can be applied.
- **Source (P2)**: run `StepstoneScan` against the captured fixture → inspect the `JobDescription`
  objects (correct `external_id`, full JD text, one-or-many per email).
- **Analysis (P4)**: run `AnthropicLLM`/`JobAnalyzer` once on a sample JD → inspect the parsed
  `JobAnalysis` (score, pros/cons, like-verdict, CV tips, cover letter).
- **Notifier (P5)**: render `digest.html.j2` to an HTML file and eyeball it; send one test email
  to yourself via `GmailAPIInterface.send`.

*End-to-end run, idempotency double-run, live digest, and scheduling are validated in deferred P6.*
