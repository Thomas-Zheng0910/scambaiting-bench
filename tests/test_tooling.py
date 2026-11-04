from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pytest

from common.tooling import (
    EnumSource,
    SchemaError,
    ToolResult,
    build_tools,
    call_tool,
    tool,
)


@dataclass
class Actor:
    stage: str = "intro"
    revealable: dict[str, list[str]] | None = None

    def __post_init__(self) -> None:
        self.revealable = self.revealable or {"intro": ["a"], "fee": ["b"]}

    @tool("Send a file", enums={"artifact_id": EnumSource(lambda s: s.revealable[s.stage])})
    def send(self, artifact_id: str, note: str = "") -> ToolResult:
        """Send a file.

        Args:
            artifact_id: which file.
            note: a line of chat.

        Returns:
            ToolResult.
        """
        return ToolResult.success({"sent": artifact_id})

    @tool("Ask for money")
    def request(self, kind: Literal["pay", "install"], amount: int | None = None) -> ToolResult:
        """Ask for something."""
        return ToolResult.success(kind)


def test_build_tools_shapes_schema():
    actor = Actor()
    schemas, registry = build_tools([actor.send], actor)
    (schema,) = schemas
    fn = schema["function"]
    assert fn["name"] == "send"
    assert fn["description"] == "Send a file"
    props = fn["parameters"]["properties"]
    assert props["artifact_id"]["enum"] == ["a"]
    assert props["note"]["type"] == "string"
    assert fn["parameters"]["required"] == ["artifact_id"]
    assert set(registry) == {"send"}


def test_enum_tracks_stage():
    actor = Actor(stage="fee")
    schemas, _ = build_tools([actor.send], actor)
    assert schemas[0]["function"]["parameters"]["properties"]["artifact_id"]["enum"] == ["b"]


def test_literal_becomes_enum():
    actor = Actor()
    schemas, _ = build_tools([actor.request], actor)
    prop = schemas[0]["function"]["parameters"]["properties"]["kind"]
    assert prop["enum"] == ["pay", "install"]
    assert prop["type"] == "string"


def test_validate_rejects_out_of_enum():
    actor = Actor()
    _, registry = build_tools([actor.send], actor)
    result = call_tool(registry, "send", {"artifact_id": "zzz"})
    assert not result.ok
    assert "not allowed" in (result.error or "")


def test_validate_rejects_missing_and_unknown_args():
    actor = Actor()
    _, registry = build_tools([actor.send], actor)
    assert not call_tool(registry, "send", {}).ok
    assert not call_tool(registry, "send", {"artifact_id": "a", "extra": 1}).ok
    assert not call_tool(registry, "nope", {}).ok


def test_executes_and_wraps_exceptions():
    class Boom:
        @tool("boom")
        def boom(self) -> ToolResult:
            raise RuntimeError("kaboom")

    _, registry = build_tools([Boom().boom], Boom())
    result = call_tool(registry, "boom", {})
    assert not result.ok
    assert "kaboom" in (result.error or "")


def test_empty_enum_is_an_error():
    actor = Actor(stage="intro")
    actor.revealable["intro"] = []
    with pytest.raises(SchemaError):
        build_tools([actor.send], actor)
