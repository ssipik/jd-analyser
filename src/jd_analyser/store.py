"""SQLite-backed persistence: dedup of jobs and Gmail messages, plus analysis history.

Sources return *all* fetched jobs; the store decides which are new (``filter_new``) and
holds the analysis results and lifecycle status. A single file DB is plenty for one user.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from jd_analyser.models import JobAnalysis, JobDescription

logger = logging.getLogger("jd_analyser")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    source        TEXT NOT NULL,
    external_id   TEXT NOT NULL,
    url           TEXT,
    title         TEXT,
    company       TEXT,
    location      TEXT,
    full_text     TEXT,
    status        TEXT NOT NULL DEFAULT 'new',   -- new | analysed | notified | error
    score         INTEGER,
    analysis_json TEXT,
    posted_at     TEXT,
    fetched_at    TEXT,
    analysed_at   TEXT,
    notified_at   TEXT,
    PRIMARY KEY (source, external_id)
);

CREATE TABLE IF NOT EXISTS processed_messages (
    message_id   TEXT PRIMARY KEY,
    processed_at TEXT NOT NULL
);
"""


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with closing(self._connect()) as conn:
            conn.executescript(_SCHEMA)
            conn.commit()

    # -- jobs --
    def filter_new(self, jobs: list[JobDescription]) -> list[JobDescription]:
        """Return only the jobs whose (source, external_id) is not already stored.

        Logs every duplicate with the title/company it collided against, since the
        dedup key is a content hash (no stable listing id in StepStone alert emails) —
        without this, a hash collision on a *different* job looks identical to a
        legitimate repeat posting in the logs.
        """
        if not jobs:
            return []
        with closing(self._connect()) as conn:
            existing = {
                (row["source"], row["external_id"]): row
                for row in conn.execute(
                    "SELECT source, external_id, title, company, status, fetched_at FROM jobs"
                )
            }
        new_jobs: list[JobDescription] = []
        for j in jobs:
            match = existing.get((j.source, j.external_id))
            if match is None:
                new_jobs.append(j)
            else:
                logger.info(
                    f"duplicate: {j.title!r} @ {j.company!r} [{j.key}] already stored as "
                    f"{match['title']!r} @ {match['company']!r} "
                    f"(status={match['status']}, fetched_at={match['fetched_at']})"
                )
        return new_jobs

    def save_job(self, job: JobDescription, status: str = "new") -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO jobs
                    (source, external_id, url, title, company, location, full_text,
                     status, posted_at, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.source,
                    job.external_id,
                    job.url,
                    job.title,
                    job.company,
                    job.location,
                    job.full_text,
                    status,
                    _iso(job.posted_at),
                    _iso(job.fetched_at),
                ),
            )
            conn.commit()

    def save_analysis(
        self,
        source: str,
        external_id: str,
        analysis: JobAnalysis,
        status: str = "analysed",
    ) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                UPDATE jobs
                SET analysis_json = ?, score = ?, status = ?, analysed_at = ?
                WHERE source = ? AND external_id = ?
                """,
                (
                    json.dumps(analysis.to_dict(), ensure_ascii=False),
                    analysis.combined_score,
                    status,
                    _now_iso(),
                    source,
                    external_id,
                ),
            )
            conn.commit()

    def set_status(self, source: str, external_id: str, status: str) -> None:
        ts_col = {"notified": "notified_at"}.get(status)
        sets = "status = ?"
        params: list[Any] = [status]
        if ts_col:
            sets += f", {ts_col} = ?"
            params.append(_now_iso())
        params.extend([source, external_id])
        with closing(self._connect()) as conn:
            conn.execute(
                f"UPDATE jobs SET {sets} WHERE source = ? AND external_id = ?", params
            )
            conn.commit()

    def get_job(self, source: str, external_id: str) -> Optional[dict[str, Any]]:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE source = ? AND external_id = ?",
                (source, external_id),
            ).fetchone()
        return dict(row) if row else None

    def get_analysis(self, source: str, external_id: str) -> Optional[JobAnalysis]:
        row = self.get_job(source, external_id)
        if not row or not row.get("analysis_json"):
            return None
        return JobAnalysis.from_dict(json.loads(row["analysis_json"]))

    def get_jobs_by_status(self, status: str) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status = ? ORDER BY score DESC", (status,)
            ).fetchall()
        return [dict(r) for r in rows]

    # -- processed Gmail messages --
    def is_message_processed(self, message_id: str) -> bool:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT 1 FROM processed_messages WHERE message_id = ?", (message_id,)
            ).fetchone()
        return row is not None

    def mark_message_processed(self, message_id: str) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO processed_messages (message_id, processed_at) VALUES (?, ?)",
                (message_id, _now_iso()),
            )
            conn.commit()
