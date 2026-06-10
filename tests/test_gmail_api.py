"""Unit tests for the pure Gmail MIME helpers (no credentials/network needed)."""
import base64
import email

from jd_analyser.interfaces.gmail_api import (
    build_raw_message,
    extract_bodies,
    parse_message,
)


def _b64(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("utf-8")


def test_extract_bodies_multipart_alternative():
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {"mimeType": "text/plain", "body": {"data": _b64("hello plain")}},
            {"mimeType": "text/html", "body": {"data": _b64("<p>hello html</p>")}},
        ],
    }
    text, html = extract_bodies(payload)
    assert "hello plain" in text
    assert "<p>hello html</p>" in html


def test_extract_bodies_nested_and_ignores_attachments():
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {
                "mimeType": "multipart/alternative",
                "parts": [{"mimeType": "text/plain", "body": {"data": _b64("nested text")}}],
            },
            {"mimeType": "application/pdf", "body": {"attachmentId": "x"}},  # no data -> ignored
        ],
    }
    text, html = extract_bodies(payload)
    assert text.strip() == "nested text"
    assert html == ""


def test_parse_message_reads_headers_and_body():
    api_msg = {
        "id": "abc",
        "threadId": "t1",
        "snippet": "snip",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "New jobs for you"},
                {"name": "From", "value": "StepStone <jobs@stepstone.de>"},
                {"name": "Date", "value": "Tue, 10 Jun 2026 08:00:00 +0000"},
            ],
            "mimeType": "text/html",
            "body": {"data": _b64("<p>job</p>")},
        },
    }
    msg = parse_message(api_msg)
    assert msg.id == "abc"
    assert msg.thread_id == "t1"
    assert msg.subject == "New jobs for you"
    assert "jobs@stepstone.de" in msg.sender
    assert msg.snippet == "snip"
    assert "<p>job</p>" in msg.html


def test_build_raw_message_roundtrips():
    raw = build_raw_message("me@example.com", "Hi Subject", "<b>body</b>")
    mime_bytes = base64.urlsafe_b64decode(raw.encode("utf-8"))
    msg = email.message_from_bytes(mime_bytes)
    assert msg["to"] == "me@example.com"
    assert msg["subject"] == "Hi Subject"
    assert msg.get_content_type() == "text/html"
    assert msg.get_payload(decode=True).decode("utf-8") == "<b>body</b>"
