"""Anthropic Messages API implementation of LLMInterface.

Uses forced tool-use to guarantee structured JSON output matching the caller's schema.
A client can be injected for testing; otherwise one is built from the API key.
"""
from __future__ import annotations

from typing import Any, Optional

from jd_analyser.interfaces.llm import LLMInterface


class AnthropicLLM(LLMInterface):
    def __init__(
        self,
        api_key: str,
        model: str,
        max_tokens: int = 4096,
        client: Optional[Any] = None,
    ):
        if client is not None:
            self.client = client
        else:
            if not api_key:
                raise ValueError(
                    "ANTHROPIC_API_KEY is not set. Add it to your .env before running analysis."
                )
            from anthropic import Anthropic

            self.client = Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    def structured(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        tool_name: str = "result",
    ) -> dict[str, Any]:
        tool = {
            "name": tool_name,
            "description": "Return the structured analysis result.",
            "input_schema": schema,
        }
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            tools=[tool],
            tool_choice={"type": "tool", "name": tool_name},
            messages=[{"role": "user", "content": user}],
        )
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
                return dict(block.input)
        raise RuntimeError("Model did not return the expected tool_use block.")
