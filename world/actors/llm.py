"""The model call.

One interface, two implementations: an OpenAI-compatible chat endpoint and a
scripted model used by tests and by replay. Nothing else in the engine knows
which one is in use.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

import httpx


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]

    def to_message(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": json.dumps(self.arguments, ensure_ascii=False)},
        }


@dataclass
class AssistantTurn:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)

    def to_message(self) -> dict[str, Any]:
        message: dict[str, Any] = {"role": "assistant", "content": self.text or None}
        if self.tool_calls:
            message["tool_calls"] = [c.to_message() for c in self.tool_calls]
        return message


class ChatModel(Protocol):
    name: str

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        tool_choice: str = "auto",
        temperature: float = 0.7,
        max_tokens: int = 220,
    ) -> AssistantTurn:
        ...


class OpenAIChat:
    """Any OpenAI-format endpoint: OpenAI, a compatible proxy, vLLM, Together."""

    def __init__(
        self,
        model: str | None = None,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.name = model or os.environ.get("ACTOR_MODEL", "actor_default")
        self.base_url = (base_url or os.environ.get("ACTOR_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.api_key = api_key or os.environ.get("ACTOR_API_KEY", "")
        self.timeout = timeout

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        tool_choice: str = "auto",
        temperature: float = 0.7,
        max_tokens: int = 220,
    ) -> AssistantTurn:
        payload: dict[str, Any] = {
            "model": self.name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        choice = data["choices"][0]["message"]
        calls: list[ToolCall] = []
        for i, call in enumerate(choice.get("tool_calls") or []):
            raw = call.get("function", {}).get("arguments") or "{}"
            try:
                arguments = json.loads(raw) if isinstance(raw, str) else dict(raw)
            except json.JSONDecodeError:
                arguments = {"__invalid__": raw}
            calls.append(ToolCall(call.get("id") or f"call_{i}", call["function"]["name"], arguments))
        return AssistantTurn(text=choice.get("content") or "", tool_calls=calls)


class ScriptedModel:
    """A model whose turns come from a list or a function.

    Used in tests and during replay. `turns` are consumed in order; when they
    run out, every further call returns the fallback text.
    """

    name = "scripted"

    def __init__(
        self,
        turns: list[AssistantTurn] | Callable[[list[dict[str, Any]]], AssistantTurn] | None = None,
        *,
        fallback: str = "Let me check on that and come back to you.",
    ) -> None:
        self._turns = turns
        self._index = 0
        self.fallback = fallback
        self.calls: list[list[dict[str, Any]]] = []

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], **_: Any) -> AssistantTurn:
        self.calls.append(messages)
        if callable(self._turns):
            return self._turns(messages)
        if self._turns and self._index < len(self._turns):
            turn = self._turns[self._index]
            self._index += 1
            return turn
        return AssistantTurn(text=self.fallback)
