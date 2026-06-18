#!/usr/bin/env python3
"""PreToolUse hook: block the agent from reading the .env file.

Wired in .claude/settings.local.json with matcher "Bash|Read|Grep". For each
tool, scan only the field(s) that designate WHAT is being read, so that
searching source code for the string "dotenv" is not mistaken for reading the
.env file itself:

    Bash  -> the full command string (unavoidably coarse)
    Read  -> file_path
    Grep  -> path + glob ONLY (never the search pattern)

Denies by emitting a PreToolUse permission decision on stdout.

This is a guardrail against casual/accidental access, NOT a security boundary:
substring matching on a shell command is defeated by indirection (cat .e*,
runtime-built paths, symlinks created via indirection, ...). A real boundary
needs privilege separation. The static deny rules in settings.local.json
remain as a backstop.
"""
import json
import re
import sys

PATTERN = re.compile(r"(\.env([^A-Za-z0-9_]|$)|dotenv)", re.IGNORECASE)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return  # unparseable input -> don't interfere; deny rules still apply

    tool = data.get("tool_name", "")
    ti = data.get("tool_input") or {}

    if tool == "Bash":
        target = ti.get("command", "") or ""
    elif tool == "Read":
        target = str(ti.get("file_path", "") or "")
    elif tool == "Grep":
        # path/glob designate the file(s) being read; the search pattern does not
        target = f"{ti.get('path', '') or ''} {ti.get('glob', '') or ''}"
    else:
        target = ""

    if PATTERN.search(target):
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": "Access to .env is blocked by .claude/deny-env-access.py",
            }
        }))


if __name__ == "__main__":
    main()
