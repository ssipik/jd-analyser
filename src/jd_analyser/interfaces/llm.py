"""LLM transport abstraction.

The analysis engine is swappable behind this ABC: the MVP uses the Anthropic Messages
API (`AnthropicLLM`); an Agent-SDK/subscription implementation can be added later without
touching `JobAnalyzer`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMInterface(ABC):
    @abstractmethod
    def structured(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        tool_name: str = "result",
    ) -> dict[str, Any]:
        """Return a dict conforming to ``schema`` for the given system/user prompts."""
        raise NotImplementedError
