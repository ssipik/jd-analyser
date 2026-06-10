"""Indeed MCP transport — placeholder.

Deferred to P7. The MCP's capabilities and auth are unknown until we can inspect a real
response, so this is a stub that documents the intended seam.
"""
from __future__ import annotations

from typing import Any


class IndeedMCPInterface:
    def __init__(self, *args: Any, **kwargs: Any):
        self._args = args
        self._kwargs = kwargs

    def fetch(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("Indeed MCP transport is not implemented yet (P7).")
