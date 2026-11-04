"""The seven tools a counterpart can call.

Every argument that names a world object is an enum resolved from the current
turn's context, so a counterpart cannot attach a file that does not exist or
request money at a stage where asking is not allowed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from common.tooling import EnumSource, ToolResult, tool


@dataclass
class TurnOutcome:
    attachments: list[str] = field(default_factory=list)
    note: str = ""
    request: dict[str, Any] | None = None
    invited_room: str | None = None
    move_to: str | None = None
    edited: str | None = None
    silent: bool = False
    left_room: bool = False
    log: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ActorContext:
    """What the tools may see. Built once per turn, immutable in practice."""

    stage: str
    request_kinds: list[str]
    attachment_ids: list[str]
    attachment_labels: dict[str, str]
    room_ids: list[str]
    handles: list[str]
    payees: list[str]
    last_message_id: str | None
    outcome: TurnOutcome = field(default_factory=TurnOutcome)


class ActorTools:
    def __init__(self, ctx: ActorContext) -> None:
        self.ctx = ctx

    @tool(
        "Send a document or photo to the client",
        enums={
            "attachment_id": EnumSource(lambda t: t.ctx.attachment_ids),
        },
    )
    def send_attachment(self, attachment_id: str, note: str = "") -> ToolResult:
        """Attach a file you have for this client.

        Args:
            attachment_id: which file to send.
            note: one line of chat to accompany it.
        """
        if attachment_id not in self.ctx.attachment_ids:
            return ToolResult.failure(f"you cannot send {attachment_id} at this stage")
        self.ctx.outcome.attachments.append(attachment_id)
        if note:
            self.ctx.outcome.note = note
        self.ctx.outcome.log.append({"tool": "send_attachment", "attachment_id": attachment_id})
        label = self.ctx.attachment_labels.get(attachment_id, attachment_id)
        return ToolResult.success({"sent": attachment_id, "label": label})

    @tool(
        "Ask the client for something: money, documents, a call, an install",
        enums={
            "kind": EnumSource(lambda t: t.ctx.request_kinds),
            "payee_id": EnumSource(lambda t: t.ctx.payees),
        },
    )
    def request(
        self,
        kind: str,
        amount: int | None = None,
        payee_id: str | None = None,
    ) -> ToolResult:
        """Make a concrete request.

        Args:
            kind: the request type code (R1-R16).
            amount: an amount in whole pounds, if money is involved.
            payee_id: who receives the money, if money is involved.
        """
        if kind not in self.ctx.request_kinds:
            return ToolResult.failure(f"{kind} is not something you would ask for yet")
        if payee_id is not None and payee_id not in self.ctx.payees:
            return ToolResult.failure(f"unknown payee {payee_id}")
        self.ctx.outcome.request = {"kind": kind, "amount": amount, "payee_id": payee_id}
        self.ctx.outcome.log.append(
            {"tool": "request", "kind": kind, "amount": amount, "payee_id": payee_id}
        )
        return ToolResult.success({"requested": kind})

    @tool(
        "Invite the client into a private group",
        enums={"room_id": EnumSource(lambda t: t.ctx.room_ids)},
    )
    def invite_to_room(self, room_id: str) -> ToolResult:
        """Add the client to a group room.

        Args:
            room_id: the room to invite them to.
        """
        if room_id not in self.ctx.room_ids:
            return ToolResult.failure(f"unknown room {room_id}")
        self.ctx.outcome.invited_room = room_id
        self.ctx.outcome.log.append({"tool": "invite_to_room", "room_id": room_id})
        return ToolResult.success({"invited": room_id})

    @tool(
        "Ask the client to continue on a different account",
        enums={"handle": EnumSource(lambda t: t.ctx.handles)},
    )
    def move_to_messenger(self, handle: str) -> ToolResult:
        """Point the client at another one of your accounts.

        Args:
            handle: the handle to continue with.
        """
        if handle not in self.ctx.handles:
            return ToolResult.failure(f"unknown handle {handle}")
        self.ctx.outcome.move_to = handle
        self.ctx.outcome.log.append({"tool": "move_to_messenger", "handle": handle})
        return ToolResult.success({"moved_to": handle})

    @tool("Edit the last message you sent")
    def edit_last_message(self, new_text: str) -> ToolResult:
        """Replace the text of your most recent message.

        Args:
            new_text: the corrected message.
        """
        if not self.ctx.last_message_id:
            return ToolResult.failure("you have not sent a message yet")
        self.ctx.outcome.edited = new_text
        self.ctx.outcome.log.append({"tool": "edit_last_message"})
        return ToolResult.success({"edited": self.ctx.last_message_id})

    @tool("Stop replying")
    def go_silent(self) -> ToolResult:
        """Stop responding from now on."""
        self.ctx.outcome.silent = True
        self.ctx.outcome.log.append({"tool": "go_silent"})
        return ToolResult.success({"silent": True})

    @tool("Leave the conversation")
    def leave_room(self) -> ToolResult:
        """Leave the room permanently."""
        self.ctx.outcome.left_room = True
        self.ctx.outcome.log.append({"tool": "leave_room"})
        return ToolResult.success({"left": True})
