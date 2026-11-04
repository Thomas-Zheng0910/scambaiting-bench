"""Reading a counterpart policy: stages, knowledge, strategy, tools.

Pure functions over the policy dict stored on the counterpart row. No model
calls, no database access; this is the part of the engine that must be
deterministic, so it is kept separate from generation.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass
class Policy:
    raw: dict[str, Any]

    # ---------------------------------------------------------------- stages
    @property
    def stage_machine(self) -> dict[str, dict[str, Any]]:
        return self.raw.get("stage_machine") or {}

    def start_stage(self) -> str:
        for stage in self.stage_machine:
            if not any(stage in node.get("on", {}).values() for node in self.stage_machine.values()):
                return stage
        return next(iter(self.stage_machine), "intro")

    def stage_order(self) -> list[str]:
        """BFS order from the start stage, so `known_info` can accumulate."""
        machine = self.stage_machine
        if not machine:
            return ["intro"]
        start = self.start_stage()
        seen: list[str] = []
        queue = deque([start])
        while queue:
            stage = queue.popleft()
            if stage in seen:
                continue
            seen.append(stage)
            for target in machine.get(stage, {}).get("on", {}).values():
                if target not in seen:
                    queue.append(target)
        for stage in machine:
            if stage not in seen:
                seen.append(stage)
        return seen

    def transition(self, stage: str, intent: str) -> str:
        node = self.stage_machine.get(stage, {})
        return node.get("on", {}).get(intent, stage)

    def emits(self, stage: str) -> list[str]:
        return list(self.stage_machine.get(stage, {}).get("emits", []))

    # ------------------------------------------------------------- knowledge
    def known_fact_keys(self, stage: str) -> list[str]:
        known = self.raw.get("known_info") or {}
        order = self.stage_order()
        if stage not in order:
            return []
        keys: list[str] = []
        for name in order[: order.index(stage) + 1]:
            keys.extend(known.get(name, []))
        return keys

    def strategy_for(self, stage: str) -> dict[str, Any]:
        return (self.raw.get("strategy") or {}).get(stage, {})

    def off_limits(self) -> list[str]:
        return list(self.raw.get("off_limits") or [])

    def style(self) -> str:
        return str(self.raw.get("style", ""))

    def max_sentences(self) -> int:
        return int(self.raw.get("max_sentences", 3))

    def behaviour(self, trigger: str) -> str:
        return str((self.raw.get("behaviour") or {}).get(trigger, ""))

    # --------------------------------------------------------------- requests
    def request_kinds(self, stage: str) -> list[str]:
        return list((self.raw.get("request_kinds") or {}).get(stage, []))

    def payee_ids(self) -> list[str]:
        return list((self.raw.get("payees") or {}).keys())

    def payee_name(self, payee_id: str) -> str:
        return str((self.raw.get("payees") or {}).get(payee_id, payee_id))

    # ------------------------------------------------------------------ tools
    def activity_plan(self) -> list[dict[str, Any]]:
        return list(self.raw.get("activity_plan") or [])

    def templates(self) -> list[dict[str, Any]]:
        return list(self.raw.get("templates") or [])

    def template_for(self, stage: str) -> dict[str, Any] | None:
        for template in self.templates():
            if template.get("stage") == stage:
                return template
        return None

    def contradicts(self, stage: str) -> list[str]:
        return list(self.strategy_for(stage).get("contradicts") or [])

    def forbid(self) -> list[str]:
        return list((self.raw.get("guard") or {}).get("forbid") or [])

    def reply_mode(self) -> dict[str, Any]:
        return dict(self.raw.get("reply_mode") or {})

    def truth_awareness(self) -> str:
        return str(self.raw.get("truth_awareness", "legit"))


def sentence_count(text: str) -> int:
    import re

    parts = [p for p in re.split(r"(?<=[.!?])\s+", text.strip()) if p]
    return len(parts)


def truncate_sentences(text: str, limit: int) -> str:
    import re

    parts = [p for p in re.split(r"(?<=[.!?])\s+", text.strip()) if p]
    if len(parts) <= limit:
        return text.strip()
    return " ".join(parts[:limit]).strip()
