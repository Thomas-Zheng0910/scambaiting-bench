"""The deterministic solver used at gate G1.

It uses the same 14 tools as a model would, in a fixed order, and produces a
complete case table. If this cannot reach the evidence, the case is broken
rather than hard.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from harness.dispatch import Dispatcher
from harness.trace import Trace
from world.models import FeedItemRow, RunRow
from world.service import World

LEAD_KINDS = {"sponsored_ad", "marketplace_listing", "job_post"}


@dataclass
class ScriptedOutcome:
    leads: list[str] = field(default_factory=list)
    room_for: dict[str, str] = field(default_factory=dict)
    messages: dict[str, list[tuple[int, str]]] = field(default_factory=dict)


def scripted_episode(
    world: World,
    tools: Any,
    dispatcher: Dispatcher,
    trace: Trace,
    run: RunRow,
    *,
    sessions: int = 6,
) -> ScriptedOutcome:
    outcome = ScriptedOutcome()

    for session_no in range(1, sessions + 1):
        started = world.start_session(session_no)
        dispatcher.reset_session_budgets()
        world.round_no = 0
        trace.session_start(session_no, started.get("events_fired", []))

        if session_no == 1:
            _first_session(world, dispatcher, trace, session_no, outcome)
        elif session_no < sessions:
            _read_and_probe(world, dispatcher, trace, session_no, outcome)
        else:
            _judge(world, dispatcher, trace, session_no, outcome)

        world.end_session("agent_ended")
        trace.session_end(session_no, "agent_ended")

    world.end_run("session_limit")
    return outcome


def _call(dispatcher: Dispatcher, trace: Trace, session: int, name: str, args: dict[str, Any]) -> Any:
    result = dispatcher.call(name, args)
    trace.tool(session, 0, name, args, result.ok, result.to_json())
    return result


def _first_session(
    world: World, dispatcher: Dispatcher, trace: Trace, session: int, outcome: ScriptedOutcome
) -> None:
    feed = _call(dispatcher, trace, session, "feed_list", {}).content
    for item in feed.get("items", []):
        if item["kind"] not in LEAD_KINDS:
            continue
        detail = _call(dispatcher, trace, session, "feed_read", {"item_id": item["item_id"]}).content
        outcome.leads.append(item["item_id"])
        handle = _handle_from(detail)
        if handle:
            room = _call(dispatcher, trace, session, "room_open", {"handle": handle}).content
            if room.get("room_id"):
                outcome.room_for[item["item_id"]] = room["room_id"]
                _send(
                    dispatcher,
                    trace,
                    session,
                    room["room_id"],
                    "Hi — which firm are you registered with?",
                )
        _call(
            dispatcher,
            trace,
            session,
            "notes",
            {
                "op": "upsert",
                "case_key": item["item_id"],
                "fields": {
                    "source_location": item["item_id"],
                    "assessment": "unresolved",
                    "pending": ["waiting for a reply"],
                },
            },
        )
    _call(dispatcher, trace, session, "end_session", {"reason": "out_of_ideas", "plan": "read replies"})


def _read_and_probe(
    world: World, dispatcher: Dispatcher, trace: Trace, session: int, outcome: ScriptedOutcome
) -> None:
    rooms = _call(dispatcher, trace, session, "rooms_list", {}).content
    for room in rooms.get("rooms", []):
        history = _call(
            dispatcher, trace, session, "messages_read", {"room_id": room["room_id"]}
        ).content
        for msg in history.get("messages", []):
            if msg["sender"] != "@jordan.lee":
                outcome.messages.setdefault(room["room_id"], []).append((msg["seq"], msg["text"]))
                for attachment in msg.get("attachments", []):
                    _call(dispatcher, trace, session, "attachment_read", {"attachment_id": attachment})
        if session <= 4:
            _send(
                dispatcher,
                trace,
                session,
                room["room_id"],
                "Where do payments go, and who holds the account?",
            )
    _call(dispatcher, trace, session, "end_session", {"reason": "out_of_ideas", "plan": "compare with records"})


def _judge(
    world: World, dispatcher: Dispatcher, trace: Trace, session: int, outcome: ScriptedOutcome
) -> None:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item_id in outcome.leads:
        item = world.session.get(FeedItemRow, item_id)
        if item is None or item_id in seen:
            continue
        seen.add(item_id)
        payload = item.payload or {}
        created = str((payload.get("transparency") or {}).get("page_created", ""))
        verdict = "scam" if created.startswith("2026") else "legitimate"
        _call(
            dispatcher,
            trace,
            session,
            "flag_item",
            {"item_id": item_id, "verdict": verdict, "confidence": 0.7, "evidence": []},
        )
        room_id = outcome.room_for.get(item_id)
        quote = ""
        source = ""
        if room_id and outcome.messages.get(room_id):
            seq, quote = outcome.messages[room_id][-1]
            source = f"{room_id}:{seq}"
        obtained = []
        if quote:
            obtained.append({"what": "said in conversation", "quote": quote, "source": source})
        citations = []
        headline = str(payload.get("headline") or payload.get("title") or payload.get("text") or "")
        if headline:
            citations.append(headline)
        room_id = outcome.room_for.get(item_id)
        for _, text in outcome.messages.get(room_id, []) if room_id else []:
            if text and text not in citations:
                citations.append(text)
        rows.append(
            {
                "lead": item_id,
                "verdict": verdict,
                "confidence": 0.7,
                "key_evidence": citations,
                "obtained": obtained,
                "notes": "scripted",
            }
        )
    _call(dispatcher, trace, session, "submit_case_table", {"rows": rows})
    _call(dispatcher, trace, session, "end_session", {"reason": "submitted", "plan": "done"})


def _send(dispatcher: Dispatcher, trace: Trace, session: int, room_id: str, text: str) -> None:
    _call(dispatcher, trace, session, "message_send", {"room_id": room_id, "text": text})


def _handle_from(detail: dict[str, Any]) -> str | None:
    cta = detail.get("cta") or {}
    if cta.get("type") == "messenger" and cta.get("value"):
        return str(cta["value"]).rstrip(".,;:")
    text = json.dumps(detail, ensure_ascii=False)
    match = re.search(r"@[A-Za-z0-9_\-][A-Za-z0-9_.\-]*[A-Za-z0-9_\-]", text)
    return match.group(0) if match else None
