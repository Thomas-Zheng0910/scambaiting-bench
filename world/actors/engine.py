"""The counterpart engine: one turn, from an investigator message to a reply.

Deterministic except for the model call:

    intent -> stage -> prompt -> tool loop -> guard -> delivery

Stage transitions, tool availability, enums, attachment visibility and delivery
timing are all computed from the case data. A model change changes wording, not
substance.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

from sqlalchemy import select

from common.text import overlap
from common.tooling import build_tools, call_tool
from world.actors import guard as guard_mod
from world.actors.intents import DEFAULT_LABELS, Intent, classify
from world.actors.llm import AssistantTurn, ChatModel
from world.actors.policy import Policy, truncate_sentences
from world.actors.prompts import TurnContext, build_messages
from world.actors.tools import ActorContext, ActorTools, TurnOutcome
from world.models import (
    AccountRow,
    AttachmentRow,
    CaseRow,
    CounterpartRow,
    CounterpartStateRow,
    EventRow,
    FactRow,
    MessageRow,
    RoomRow,
)

MAX_TOOL_ITERATIONS = 4
FALLBACK = "Let me check on that and come back to you."


class CounterpartEngine:
    def __init__(self, model: ChatModel, *, max_tool_iterations: int = MAX_TOOL_ITERATIONS) -> None:
        self.model = model
        self.max_tool_iterations = max_tool_iterations

    # ------------------------------------------------------------------ entry
    def on_message(self, world: Any, room_id: str, message: MessageRow) -> list[MessageRow]:
        room = world.session.get(RoomRow, room_id)
        if room is None or not room.case_id:
            return []

        resolved = _resolve_counterpart(world, room)
        if resolved is None:
            return []
        counterpart, account = resolved

        state = world.session.get(CounterpartStateRow, counterpart.id)
        if state is None:
            policy0 = Policy(counterpart.policy)
            state = CounterpartStateRow(
                counterpart_id=counterpart.id, stage=policy0.start_stage(), updated_session=world.session_no
            )
            world.session.add(state)
            world.session.flush()
        if state.silent:
            return []

        policy = Policy(counterpart.policy)
        labels = sorted(
            {label for node in policy.stage_machine.values() for label in node.get("on", {})}
            | set(DEFAULT_LABELS)
        )
        intent = classify(message.text, labels)

        previous_stage = state.stage
        new_stage = policy.transition(previous_stage, intent.label)
        state.stage = new_stage
        state.updated_session = world.session_no
        world.session.flush()

        self._release_stage_messages(world, counterpart.id, policy, new_stage)
        if new_stage != previous_stage:
            self._fire_emits(world, counterpart.case_id, policy, new_stage)

        turn = self._generate(world, room, counterpart, account, policy, new_stage, intent)
        return [turn] if turn is not None else []

    # ------------------------------------------------------------- generation
    def _generate(
        self,
        world: Any,
        room: RoomRow,
        counterpart: CounterpartRow,
        account: AccountRow,
        policy: Policy,
        stage: str,
        intent: Intent,
    ) -> MessageRow | None:
        case = world.session.get(CaseRow, counterpart.case_id)
        raw = case.raw if case else {}

        transcript = self._transcript(world, room.id)
        ctx = ActorContext(
            stage=stage,
            request_kinds=policy.request_kinds(stage),
            attachment_ids=self._attachments_at(world, counterpart.case_id, policy, stage),
            attachment_labels=self._attachment_labels(world, counterpart.case_id, policy, stage),
            room_ids=self._room_ids(world, counterpart.case_id),
            handles=self._handles(world, counterpart.case_id),
            payees=policy.payee_ids(),
            last_message_id=self._last_message_id(world, room.id, counterpart.id),
        )
        tools_impl = ActorTools(ctx)
        tool_methods = [
            tools_impl.send_attachment,
            tools_impl.request,
            tools_impl.invite_to_room,
            tools_impl.move_to_messenger,
            tools_impl.edit_last_message,
            tools_impl.go_silent,
            tools_impl.leave_room,
        ]
        schemas, registry = build_tools(tool_methods, tools_impl, strict=False)

        tc = TurnContext(
            name=account.display_name,
            role_label=account.role_label or counterpart.role,
            policy=policy,
            stage=stage,
            known=self._known_statements(world, counterpart.case_id, policy, stage),
            off_limits=policy.off_limits(),
            strategy=policy.strategy_for(stage),
            transcript=transcript,
            attachments=[
                {"id": aid, "label": ctx.attachment_labels.get(aid, aid)} for aid in ctx.attachment_ids
            ],
            payable_to={p: policy.payee_name(p) for p in policy.payee_ids()},
        )
        messages = build_messages(tc)

        turn = self._run_tool_loop(messages, schemas, registry, policy)
        text = (turn.text or "").strip()
        outcome = ctx.outcome

        if not text:
            text = self._template_text(policy, stage)
        if outcome.note and outcome.note not in text:
            text = f"{outcome.note} {text}".strip()

        verdict = self._guard(text, raw, policy)
        if not verdict.ok:
            retry = messages + [
                {"role": "system", "content": f"Your reply was rejected ({verdict.reason}). Rewrite it, in character, without that problem."},
            ]
            turn = self._run_tool_loop(retry, schemas, registry, policy)
            text = (turn.text or "").strip()
            verdict = self._guard(text, raw, policy)
            if not verdict.ok:
                candidate = self._template_text(policy, stage)
                text = candidate if self._guard(candidate, raw, policy).ok else FALLBACK

        if not text:
            text = FALLBACK

        text = truncate_sentences(text, policy.max_sentences())

        fact_keys = list(self._template_keys(policy, stage))
        fact_keys.extend(self._mentioned_facts(world, counterpart.case_id, text))
        obtainable_keys = guard_mod.obtainable_leaks(text, raw.get("obtainable", []))
        if outcome.attachments:
            for aid in outcome.attachments:
                attachment = world.session.get(AttachmentRow, aid)
                if attachment:
                    fact_keys.extend(attachment.fact_keys)
                    obtainable_keys.extend(attachment.obtainable_keys)

        deliver = self._delivery_session(world, room, counterpart, policy)

        msg = world._append(
            room,
            sender=account.handle,
            text=text,
            counterpart_id=counterpart.id,
            deliver_at_session=deliver,
            attachments=list(dict.fromkeys(outcome.attachments)),
            fact_keys=sorted(set(fact_keys)),
            obtainable_keys=sorted(set(obtainable_keys)),
        )
        msg_meta = {
            "intent": intent.to_json(),
            "stage": stage,
            "tools": outcome.log,
            "request": outcome.request,
            "leak": obtainable_keys,
            "guard_ok": verdict.ok,
        }
        self._record_turn(world, msg, msg_meta)

        if outcome.invited_room:
            world.invite(outcome.invited_room, "Adding you to the group now.")
        if outcome.edited:
            self._apply_edit(world, room.id, counterpart.id, outcome.edited)
        if outcome.silent:
            self._set_silent(world, counterpart.id)
        if outcome.left_room:
            self._leave(world, room, account.handle)

        return msg

    def _run_tool_loop(
        self,
        messages: list[dict[str, Any]],
        schemas: list[dict[str, Any]],
        registry: dict[str, Any],
        policy: Policy,
    ) -> AssistantTurn:
        conversation = list(messages)
        for _ in range(self.max_tool_iterations):
            turn = self.model.complete(
                conversation,
                schemas,
                tool_choice="auto",
                temperature=float(policy.raw.get("llm", {}).get("temperature", 0.7)),
                max_tokens=int(policy.raw.get("llm", {}).get("max_tokens", 220)),
            )
            if not turn.tool_calls:
                return turn
            conversation.append(turn.to_message())
            for call in turn.tool_calls:
                result = call_tool(registry, call.name, call.arguments)
                conversation.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result.to_json(), ensure_ascii=False),
                    }
                )
        # Tool-only turn: force a text completion.
        return self.model.complete(conversation, [], tool_choice="none", temperature=0.7, max_tokens=220)

    # ---------------------------------------------------------------- helpers
    def _guard(self, text: str, raw: dict[str, Any], policy: Policy) -> guard_mod.GuardVerdict:
        return guard_mod.check(
            text,
            entities=guard_mod.EntityTable.from_case(raw),
            sentence_limit=policy.max_sentences(),
            forbid=policy.forbid(),
        )

    def _template_text(self, policy: Policy, stage: str) -> str:
        template = policy.template_for(stage)
        return str(template.get("fixed", FALLBACK)) if template else FALLBACK

    def _template_keys(self, policy: Policy, stage: str) -> list[str]:
        template = policy.template_for(stage)
        return list(template.get("fact_keys", [])) if template else []

    def _mentioned_facts(self, world: Any, case_id: str, text: str) -> list[str]:
        """Facts the reply actually states, judged by deterministic overlap.

        This is what makes an observation of a message independent of whether
        the model happened to use the authored template.
        """
        facts = world.session.scalars(
            select(FactRow).where(FactRow.case_id == case_id, FactRow.kind == "claim")
        ).all()
        return [f.key for f in facts if overlap(text, f.statement) >= 0.55]

    def _known_statements(
        self, world: Any, case_id: str, policy: Policy, stage: str
    ) -> list[str]:
        keys = policy.known_fact_keys(stage)
        if not keys:
            return []
        facts = world.session.scalars(
            select(FactRow).where(FactRow.case_id == case_id, FactRow.key.in_(keys))
        ).all()
        by_key = {f.key: f.statement for f in facts}
        return [by_key[k] for k in keys if k in by_key]

    def _transcript(self, world: Any, room_id: str, limit: int = 12) -> list[dict[str, str]]:
        rows = world.session.scalars(
            select(MessageRow)
            .where(MessageRow.room_id == room_id)
            .where(MessageRow.deliver_at_session <= world.session_no)
            .order_by(MessageRow.seq.desc())
            .limit(limit)
        ).all()
        return [{"sender": r.sender, "text": r.text} for r in reversed(rows)]

    def _attachments_at(self, world: Any, case_id: str, policy: Policy, stage: str) -> list[str]:
        order = policy.stage_order()
        if stage not in order:
            return []
        reached = set(order[: order.index(stage) + 1])
        rows = world.session.scalars(
            select(AttachmentRow).where(AttachmentRow.case_id == case_id)
        ).all()
        return [
            r.id
            for r in rows
            if r.visible_from_stage is None or r.visible_from_stage in reached
        ]

    def _attachment_labels(self, world: Any, case_id: str, policy: Policy, stage: str) -> dict[str, str]:
        rows = world.session.scalars(select(AttachmentRow).where(AttachmentRow.case_id == case_id)).all()
        ids = set(self._attachments_at(world, case_id, policy, stage))
        return {r.id: r.filename or r.caption or r.id for r in rows if r.id in ids}

    def _room_ids(self, world: Any, case_id: str) -> list[str]:
        rows = world.session.scalars(select(RoomRow).where(RoomRow.case_id == case_id)).all()
        return [r.id for r in rows]

    def _handles(self, world: Any, case_id: str) -> list[str]:
        rows = world.session.scalars(
            select(AccountRow).where(AccountRow.case_id == case_id, AccountRow.surface == "messenger")
        ).all()
        return [r.handle for r in rows]

    def _last_message_id(self, world: Any, room_id: str, counterpart_id: str) -> str | None:
        rows = world.session.scalars(
            select(MessageRow)
            .where(MessageRow.room_id == room_id, MessageRow.counterpart_id == counterpart_id)
            .order_by(MessageRow.seq.desc())
            .limit(1)
        ).all()
        return rows[0].id if rows else None

    def _delivery_session(
        self, world: Any, room: RoomRow, counterpart: CounterpartRow, policy: Policy
    ) -> int:
        mode = policy.reply_mode()
        first = not self._has_replied(world, room.id, counterpart.id)
        if first and int(mode.get("in_session_after_calls", 0)) > 0:
            return world.session_no
        if mode.get("later", "next_session") == "same_session":
            return world.session_no
        return world.session_no + 1

    def _has_replied(self, world: Any, room_id: str, counterpart_id: str) -> bool:
        return (
            world.session.scalar(
                select(MessageRow.id)
                .where(MessageRow.room_id == room_id, MessageRow.counterpart_id == counterpart_id)
                .limit(1)
            )
            is not None
        )

    def _release_stage_messages(self, world: Any, counterpart_id: str, policy: Policy, stage: str) -> None:
        order = policy.stage_order()
        if stage not in order:
            return
        reached = set(order[: order.index(stage) + 1])
        rows = world.session.scalars(
            select(MessageRow).where(
                MessageRow.counterpart_id == counterpart_id,
                MessageRow.deliver_at_stage.is_not(None),
            )
        ).all()
        for row in rows:
            if row.deliver_at_stage in reached and row.deliver_at_session > world.session_no:
                row.deliver_at_session = world.session_no
        world.session.flush()

    def _fire_emits(self, world: Any, case_id: str, policy: Policy, stage: str) -> None:
        for name in policy.emits(stage):
            event = world.session.scalar(
                select(EventRow).where(EventRow.id == f"{case_id}:{name}", EventRow.fired.is_(False))
            )
            if event is not None:
                world.fire_event(event)

    def _apply_edit(self, world: Any, room_id: str, counterpart_id: str, new_text: str) -> None:
        rows = world.session.scalars(
            select(MessageRow)
            .where(MessageRow.room_id == room_id, MessageRow.counterpart_id == counterpart_id)
            .order_by(MessageRow.seq.desc())
            .limit(1)
        ).all()
        if rows:
            rows[0].text = new_text
            rows[0].edited = True
            world.session.flush()

    def _set_silent(self, world: Any, counterpart_id: str) -> None:
        state = world.session.get(CounterpartStateRow, counterpart_id)
        if state:
            state.silent = True
            world.session.flush()

    def _leave(self, world: Any, room: RoomRow, handle: str) -> None:
        room.members = [m for m in room.members if m != handle]
        world.session.flush()

    def _record_turn(self, world: Any, msg: MessageRow, meta: dict[str, Any]) -> None:
        world._state("message", msg.id, None, {"meta": meta}, "counterpart")


def _resolve_counterpart(world: Any, room: RoomRow) -> tuple[CounterpartRow, AccountRow] | None:
    accounts = world.session.scalars(
        select(AccountRow).where(AccountRow.handle.in_(room.members))
    ).all()
    candidates = [a for a in accounts if a.counterpart_id]
    if not candidates:
        return None
    cps = []
    for account in candidates:
        cp = world.session.get(CounterpartRow, account.counterpart_id)
        if cp is not None:
            cps.append((cp, account))
    if not cps:
        return None
    lead = [pair for pair in cps if pair[0].role != "shill"] or cps
    return lead[0]
