from __future__ import annotations

from world.records import GENUINE, answer


def test_genuine_services_are_reachable(world):
    room = world.room_open("@register_enquiries")
    assert room.ok
    reply = world.message_send(room.content["room_id"], "What do you have for FSR 551203?")
    assert reply.ok
    messages = world.messages_read(room.content["room_id"]).content["messages"]
    text = messages[-1]["text"]
    assert "Apex Capital Ltd" in text
    assert "apexcapital.co.uk" in text
    assert "Authorised" in text


def test_record_answer_names_its_facts(world):
    room = world.room_open("@register_enquiries").content["room_id"]
    world.message_send(room, "FSR 551203 please")
    latest = world.messages_read(room).content["messages"][-1]
    rows = world.session.execute(
        __import__("sqlalchemy").text("select fact_keys from message where id=:i"),
        {"i": latest["msg_id"]},
    ).one()
    assert "F3" in rows[0]


def test_unknown_lookup_is_refused_not_invented(world):
    room = world.room_open("@domain_records").content["room_id"]
    world.message_send(room, "tell me about a domain I have not named")
    text = world.messages_read(room).content["messages"][-1]["text"]
    assert text.startswith("I can only provide record details")


def test_fake_service_gives_a_doctored_answer(world):
    room = world.room_open("@fsr_verify_desk")
    assert room.ok
    world.message_send(room.content["room_id"], "Check FSR 551203")
    text = world.messages_read(room.content["room_id"]).content["messages"][-1]["text"]
    assert "apexcapital-markets.com" in text
    assert "No adverse records" in text


def test_genuine_and_fake_disagree_about_the_domain(world):
    genuine_room = world.room_open("@register_enquiries").content["room_id"]
    fake_room = world.room_open("@fsr_verify_desk").content["room_id"]
    world.message_send(genuine_room, "FSR 551203")
    world.message_send(fake_room, "FSR 551203")
    genuine = world.messages_read(genuine_room).content["messages"][-1]["text"]
    fake = world.messages_read(fake_room).content["messages"][-1]["text"]
    assert "apexcapital.co.uk" in genuine
    assert "apexcapital-markets.com" in fake
    assert genuine != fake
