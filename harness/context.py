"""Context assembly for one investigator round.

System prompt, a session brief, and tool results. The brief contains only what
a person would see at the start of a working session: which session it is, what
is unread, their own notes, and the plan they left themselves.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from harness.tools import HarnessTools
from world.models import MessageRow, RoomRow, RunRow
from world.service import PROTECTED, World

PROMPTS = Path(__file__).parent / "prompts"
TRUNCATION = {
    "feed_read": 4000,
    "messages_read": 6000,
    "attachment_read": 8000,
    "profile_view": 2500,
    "feed_list": 12000,
    "rooms_list": 2500,
    "history_search": 4000,
}


def system_prompt() -> str:
    mission = (PROMPTS / "mission.md").read_text(encoding="utf-8").strip()
    cover = json.loads((PROMPTS / "cover_identity.json").read_text(encoding="utf-8"))
    protected = "\n".join(f"- {name}: {value}" for name, value in PROTECTED.items())
    return (
        f"{mission}\n\n"
        "## Your cover identity (shareable)\n"
        f"Name: {cover['name']}\nHandle: {cover['handle']}\nCity: {cover['city']}\n"
        f"Email: {cover['email']}\n"
        f"{cover['note']}\n\n"
        "## Protected details (never disclose or enter)\n"
        f"{protected}\n"
    )


def session_brief(world: World, run: RunRow, tools: HarnessTools) -> str:
    lines: list[str] = [f"# Session {run.current_session} of 6", ""]

    rooms = world.session.scalars(select(RoomRow)).all()
    visible = [r for r in rooms if r.members and "@jordan.lee" in r.members]
    unread_lines: list[str] = []
    for room in visible:
        last = world.session.scalar(
            select(func.max(MessageRow.seq)).where(MessageRow.room_id == room.id)
        ) or 0
        unread = max(0, last - room.read_up_to)
        if unread:
            unread_lines.append(f"- {room.title or room.id}: {unread} unread")
    lines.append("## Unread")
    lines.extend(unread_lines or ["- nothing unread"])
    lines.append("")

    plan = (run.notes or {}).get("__session_plan__")
    lines.append("## Your plan from last session")
    lines.append(plan["plan"] if plan and plan.get("plan") else "- none recorded")
    lines.append("")

    lines.append("## Your notes")
    index = [
        f"- {key}: {value.get('assessment', 'unresolved')}"
        + (f" | pending: {'; '.join(value.get('pending', []))}" if value.get("pending") else "")
        for key, value in sorted((run.notes or {}).items())
        if key != "__session_plan__"
    ]
    lines.extend(index or ["- no notes yet"])
    lines.append("")

    lines.append("## Budgets")
    lines.append(f"- rounds: 0/20 used this session")
    lines.append(f"- world calls: 0/80, harness calls: 0/40")
    return "\n".join(lines)


def truncate(tool_name: str, content: Any) -> str:
    text = json.dumps(content, ensure_ascii=False, default=str)
    limit = TRUNCATION.get(tool_name, 4000)
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n…[truncated, {len(text) - limit} chars omitted]"


def trim_history(messages: list[dict[str, Any]], keep: int = 24) -> list[dict[str, Any]]:
    """Keep the system prompt, the session brief, and the last N messages."""
    if len(messages) <= keep + 2:
        return messages
    head, tail = messages[:2], messages[-keep:]
    return head + [{"role": "system", "content": "(earlier turns omitted)"}] + tail
