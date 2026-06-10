"""Gmail transport: read alert emails, send the digest, label processed messages.

Reusable across any email-based source *and* by the notifier. The MIME-parsing and
message-building helpers are kept as pure module functions so they can be unit-tested
without credentials or network access.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Read + modify (labels) and send. gmail.modify covers read & label changes.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]
PROCESSED_LABEL = "JD-Analyser/Processed"


@dataclass
class EmailMessage:
    """A decoded email — the output contract of any email transport."""

    id: str
    thread_id: str
    subject: str
    sender: str
    date: str
    snippet: str
    text: str  # decoded text/plain body
    html: str  # decoded text/html body


# --- pure helpers (no service/network) -------------------------------------------------


def _decode_b64url(data: str) -> str:
    return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="replace")


def extract_bodies(payload: dict[str, Any]) -> tuple[str, str]:
    """Walk a Gmail message payload and return (plain_text, html) bodies."""
    text_parts: list[str] = []
    html_parts: list[str] = []

    def walk(part: dict[str, Any]) -> None:
        mime = part.get("mimeType", "")
        sub_parts = part.get("parts")
        if sub_parts:
            for p in sub_parts:
                walk(p)
            return
        data = part.get("body", {}).get("data")
        if not data:
            return
        decoded = _decode_b64url(data)
        if mime == "text/plain":
            text_parts.append(decoded)
        elif mime == "text/html":
            html_parts.append(decoded)

    walk(payload)
    return "\n".join(text_parts), "\n".join(html_parts)


def parse_message(api_msg: dict[str, Any]) -> EmailMessage:
    """Convert a Gmail API ``messages.get(format='full')`` response into an EmailMessage."""
    payload = api_msg.get("payload", {})
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
    text, html = extract_bodies(payload)
    return EmailMessage(
        id=api_msg.get("id", ""),
        thread_id=api_msg.get("threadId", ""),
        subject=headers.get("subject", ""),
        sender=headers.get("from", ""),
        date=headers.get("date", ""),
        snippet=api_msg.get("snippet", ""),
        text=text,
        html=html,
    )


def build_raw_message(to: str, subject: str, html: str) -> str:
    """Build a base64url-encoded MIME message body for ``messages.send``."""
    message = MIMEText(html, "html", "utf-8")
    message["to"] = to
    message["subject"] = subject
    return base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")


# --- transport -------------------------------------------------------------------------


class GmailAPIInterface:
    """Authenticated Gmail access: search, fetch, send, and label."""

    def __init__(self, client_secret_path: Path, token_path: Path):
        self.client_secret_path = Path(client_secret_path)
        self.token_path = Path(token_path)
        self._service: Optional[Any] = None
        self._processed_label_id: Optional[str] = None

    # -- auth/service --
    def _load_credentials(self) -> Credentials:
        creds: Optional[Credentials] = None
        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
        if creds and creds.valid:
            return creds
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not self.client_secret_path.exists():
                raise FileNotFoundError(
                    f"Missing Google OAuth client secret at {self.client_secret_path}. "
                    "Create a Desktop OAuth client (Gmail API enabled) and download it there."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(self.client_secret_path), SCOPES)
            creds = flow.run_local_server(port=0)
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(creds.to_json())
        return creds

    @property
    def service(self) -> Any:
        if self._service is None:
            self._service = build(
                "gmail", "v1", credentials=self._load_credentials(), cache_discovery=False
            )
        return self._service

    # -- operations --
    def search(self, query: str, max_results: int = 50) -> list[str]:
        """Return message ids matching a Gmail search query (newest first)."""
        ids: list[str] = []
        page_token: Optional[str] = None
        while len(ids) < max_results:
            resp = (
                self.service.users()
                .messages()
                .list(
                    userId="me",
                    q=query,
                    maxResults=min(500, max_results - len(ids)),
                    pageToken=page_token,
                )
                .execute()
            )
            ids.extend(m["id"] for m in resp.get("messages", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return ids[:max_results]

    def get_message(self, msg_id: str) -> EmailMessage:
        api_msg = (
            self.service.users()
            .messages()
            .get(userId="me", id=msg_id, format="full")
            .execute()
        )
        return parse_message(api_msg)

    def send(self, to: str, subject: str, html: str) -> dict[str, Any]:
        body = {"raw": build_raw_message(to, subject, html)}
        return self.service.users().messages().send(userId="me", body=body).execute()

    def ensure_label(self, name: str = PROCESSED_LABEL) -> str:
        labels = self.service.users().labels().list(userId="me").execute().get("labels", [])
        for label in labels:
            if label["name"] == name:
                return label["id"]
        created = (
            self.service.users()
            .labels()
            .create(
                userId="me",
                body={
                    "name": name,
                    "labelListVisibility": "labelShow",
                    "messageListVisibility": "show",
                },
            )
            .execute()
        )
        return created["id"]

    def mark_processed(self, msg_id: str) -> None:
        if self._processed_label_id is None:
            self._processed_label_id = self.ensure_label()
        self.service.users().messages().modify(
            userId="me", id=msg_id, body={"addLabelIds": [self._processed_label_id]}
        ).execute()
