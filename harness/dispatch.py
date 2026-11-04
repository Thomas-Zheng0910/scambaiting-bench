"""One place where a tool call becomes an effect.

The dispatcher owns the two budgets, routes each call to the world or to the
harness, and hands the result to the trace. Nothing else in the harness calls a
tool directly.
"""

from __future__ import annotations

import json
from typing import Any

from common.tooling import ToolResult, build_tools, call_tool
from harness.tools import HarnessTools
from world.app import world_registry
from world.models import RunRow
from world.service import World

WORLD_CALL_LIMIT = 80
HARNESS_CALL_LIMIT = 40


class Dispatcher:
    def __init__(self, world: World, tools: HarnessTools) -> None:
        self.world = world
        self.tools = tools
        self.world_schemas, self.world_registry = world_registry(world)
        methods = [
            tools.flag_item,
            tools.notes,
            tools.history_search,
            tools.end_session,
            tools.submit_case_table,
        ]
        self.harness_schemas, self.harness_registry = build_tools(methods, tools)
        self.log: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ setup
    def schemas(self) -> list[dict[str, Any]]:
        return [*self.world_schemas, *self.harness_schemas]

    def run_row(self) -> RunRow:
        row = self.world.session.get(RunRow, self.tools.run_id)
        if row is None:
            raise RuntimeError("run missing")
        return row

    # ------------------------------------------------------------------ calls
    def call(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        is_world = name in self.world_registry
        is_harness = name in self.harness_registry
        if not is_world and not is_harness:
            return ToolResult.failure(f"unknown tool {name}")

        run = self.run_row()
        if is_world and run.world_calls >= WORLD_CALL_LIMIT:
            return ToolResult.failure("world-call budget exhausted for this session")
        if is_harness and run.harness_calls >= HARNESS_CALL_LIMIT:
            return ToolResult.failure("harness-call budget exhausted for this session")

        registry = self.world_registry if is_world else self.harness_registry
        result = call_tool(registry, name, arguments)

        if is_world:
            run.world_calls += 1
        else:
            run.harness_calls += 1
        self.world.session.flush()

        self.log.append(
            {
                "session": run.current_session,
                "round": run.round,
                "tool": name,
                "arguments": arguments,
                "ok": result.ok,
                "result": result.to_json(),
            }
        )
        return result

    def reset_session_budgets(self) -> None:
        run = self.run_row()
        run.world_calls = 0
        run.harness_calls = 0
        self.world.session.flush()

    def dumps_log(self) -> str:
        return "\n".join(json.dumps(entry, ensure_ascii=False) for entry in self.log)
