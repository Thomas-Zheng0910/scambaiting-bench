from __future__ import annotations

from sqlalchemy import select

from world.actors.engine import CounterpartEngine
from world.actors.llm import AssistantTurn, ScriptedModel, ToolCall
from world.models import CounterpartStateRow, MessageRow


def say(text: str) -> ScriptedModel:
    return ScriptedModel([AssistantTurn(text=text)])


def test_stage_progresses_from_intro_to_invite_group(world, stub_actor):
    room = world.room_open("@apex_emma").content["room_id"]
    world.engine = stub_actor([AssistantTurn(text="Happy to help.")])
    world.message_send(room, "I'm interested, how do I join?")

    state = world.session.get(CounterpartStateRow, "inv01_scam:mentor")
    assert state.stage == "invite_group"


def test_emit_fires_the_group_invite(world, stub_actor):
    room = world.room_open("@apex_emma").content["room_id"]
    world.engine = stub_actor([AssistantTurn(text="Happy to help.")])
    world.message_send(room, "I'm interested, how do I join?")
    rooms = world.rooms_list().content["rooms"]
    vip = next(r for r in rooms if "VIP" in r["title"])
    assert vip["status"] == "invited"


def test_small_talk_does_not_advance_the_stage(world, stub_actor):
    room = world.room_open("@apex_emma").content["room_id"]
    world.engine = stub_actor([AssistantTurn(text="Happy to help.")])
    world.message_send(room, "nice weather today")
    state = world.session.get(CounterpartStateRow, "inv01_scam:mentor")
    assert state.stage == "intro"


def test_first_reply_is_same_session_later_replies_wait(world, stub_actor):
    room = world.room_open("@apex_emma").content["room_id"]
    world.engine = stub_actor([AssistantTurn(text="Happy to help.")])
    world.message_send(room, "hello")
    visible = world.messages_read(room).content["messages"]
    assert any(m["sender"] == "@apex_emma" for m in visible)

    world.engine = stub_actor([AssistantTurn(text="Still here.")])
    world.message_send(room, "Are you there?")
    visible = world.messages_read(room).content["messages"]
    assert not any(m["text"] == "Still here." for m in visible)
    world.start_session(2)
    visible = world.messages_read(room).content["messages"]
    assert any(m["text"] == "Still here." for m in visible)


def test_guard_rejects_an_invented_amount(world, stub_actor):
    room = world.room_open("@apex_emma").content["room_id"]
    world.engine = stub_actor(
        [AssistantTurn(text="The fee is only £37 and you can withdraw whenever you like.")]
    )
    world.message_send(room, "what does it cost?")
    reply = [m for m in world.messages_read(room).content["messages"] if m["sender"] == "@apex_emma"][-1]
    assert "37" not in reply["text"]
    assert "Let me check" in reply["text"]


def test_guard_rejects_breaking_character(world, stub_actor):
    room = world.room_open("@apex_emma").content["room_id"]
    world.engine = stub_actor([AssistantTurn(text="I am an AI and this is a scam.")])
    world.message_send(room, "who are you really?")
    reply = [m for m in world.messages_read(room).content["messages"] if m["sender"] == "@apex_emma"][-1]
    assert "I am an AI" not in reply["text"]


def test_attachment_cannot_be_sent_before_its_stage(world, stub_actor):
    room = world.room_open("@apex_emma").content["room_id"]
    world.engine = stub_actor(
        [
            AssistantTurn(
                tool_calls=[ToolCall("c1", "send_attachment", {"attachment_id": "at_fee_schedule"})]
            ),
            AssistantTurn(text="Sent."),
        ]
    )
    world.message_send(room, "hello")
    reply = [m for m in world.messages_read(room).content["messages"] if m["sender"] == "@apex_emma"][-1]
    assert reply["attachments"] == []


def test_attachment_is_sent_when_its_stage_arrives(world, stub_actor):
    room = world.room_open("@apex_emma").content["room_id"]
    world.engine = stub_actor([AssistantTurn(text="Happy to help.")])
    world.message_send(room, "I'm interested")           # intro -> invite_group
    world.message_send(room, "how do withdrawals work?")  # invite_group -> platform

    world.engine = stub_actor(
        [
            AssistantTurn(
                tool_calls=[
                    ToolCall(
                        "c1",
                        "send_attachment",
                        {"attachment_id": "at_welcome_pack", "note": "Here it is."},
                    )
                ]
            ),
            AssistantTurn(text="Let me know what you think."),
        ]
    )
    world.message_send(room, "send the paperwork")
    world.start_session(2)
    reply = [m for m in world.messages_read(room).content["messages"] if m["sender"] == "@apex_emma"][-1]
    assert reply["attachments"] == ["at_welcome_pack"]


def test_request_is_refused_outside_its_stage(world, stub_actor):
    room = world.room_open("@apex_emma").content["room_id"]
    world.engine = stub_actor(
        [
            AssistantTurn(tool_calls=[ToolCall("c1", "request", {"kind": "R3", "amount": 480})]),
            AssistantTurn(text="Okay."),
        ]
    )
    world.message_send(room, "hello")
    # No request metadata is recorded because R3 is only allowed at `fee`.
    stored = world.session.scalars(select(MessageRow).where(MessageRow.sender == "@apex_emma")).all()
    assert stored
    assert all("request" not in (m.fact_keys or []) for m in stored)
