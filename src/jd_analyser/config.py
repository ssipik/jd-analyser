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

DEFAULT_MODEL = "claude-sonnet-4-6"
# StepStone job-suggestion sender(s); refined once we inspect a real sample (P2).
DEFAULT_GMAIL_QUERY = "from:jobs@stepstone.de OR from:jobsuche@stepstone.de"


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

    @classmethod
    def load(cls) -> "Settings":
        load_dotenv(PROJECT_ROOT / ".env")
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
        )
