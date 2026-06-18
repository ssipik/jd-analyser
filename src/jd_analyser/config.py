"""Centralised settings and project paths, loaded from a `.env` file.

Every component pulls runtime configuration from `Settings.load()` so secrets and
tunables live in one place (the `.env`), never hard-coded.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# src/jd_analyser/config.py -> parents[2] is the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
CREDENTIALS_DIR = PROJECT_ROOT / "credentials"
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = PROJECT_ROOT / "log"

DEFAULT_MODEL = "claude-sonnet-4-6"
# Local MLflow server for tracing every Anthropic API call. Tracing fails soft: if the
# server is unreachable the pipeline still runs (traces are just dropped).
DEFAULT_MLFLOW_TRACKING_URI = "http://localhost:5000"
DEFAULT_MLFLOW_EXPERIMENT = "jd-analyser"
# Real StepStone alert sender (confirmed from captured samples); both single-job mails
# and digests come from this address — the source's filter separates them. Capped to the
# last 7 days so a scan never trawls the whole mailbox.
DEFAULT_GMAIL_QUERY = "from:info@jobagent.stepstone.de newer_than:7d"


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str
    model: str
    gmail_query: str
    score_threshold: int
    notify_to: str
    db_path: Path
    client_secret_path: Path
    token_path: Path
    mlflow_tracing: bool
    mlflow_tracking_uri: str
    mlflow_experiment: str

    @classmethod
    def load(cls) -> "Settings":
        # override=True so the .env is authoritative: a stale ANTHROPIC_API_KEY (or any
        # other var) already exported in the shell must not silently shadow it.
        load_dotenv(PROJECT_ROOT / ".env", override=True)
        return cls(
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            model=os.getenv("MODEL", DEFAULT_MODEL),
            gmail_query=os.getenv("GMAIL_QUERY", DEFAULT_GMAIL_QUERY),
            score_threshold=int(os.getenv("SCORE_THRESHOLD", "60")),
            notify_to=os.getenv("NOTIFY_TO", ""),
            db_path=Path(os.getenv("DB_PATH", str(DATA_DIR / "jobs.db"))),
            client_secret_path=Path(
                os.getenv("GMAIL_CLIENT_SECRET", str(CREDENTIALS_DIR / "client_secret.json"))
            ),
            token_path=Path(os.getenv("GMAIL_TOKEN", str(CREDENTIALS_DIR / "token.json"))),
            mlflow_tracing=os.getenv("MLFLOW_TRACING", "true").lower() not in ("0", "false", "no"),
            mlflow_tracking_uri=os.getenv("MLFLOW_TRACKING_URI", DEFAULT_MLFLOW_TRACKING_URI),
            mlflow_experiment=os.getenv("MLFLOW_EXPERIMENT", DEFAULT_MLFLOW_EXPERIMENT),
        )
