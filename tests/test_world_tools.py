from __future__ import annotations

from sqlalchemy import select

from world.models import ObservationRow, RoomRow


def data(result):
    assert result.ok, result.error
    return result.content


def test_feed_list_is_a_snapshot_without_labels(world):
    feed = data(world.feed_list())
    assert feed["count"] >= 10
    first = feed["items"][0]
    assert set(first) == {"item_id", "kind", "author_handle", "title", "snippet", "has_cta"}
    assert "label" not in first and "case_id" not in first


def test_feed_read_hides_internal_fields(world):
    item = data(world.feed_read("fi_inv01_ad"))
    assert item["headline"].startswith("10.4%")
    text = str(item)
    for internal in ("inv01_scam", "judgeable", "case_id", "truth"):
        assert internal not in text


def test_comments_are_gated_by_session(world):
    item = data(world.feed_read("fi_inv01_group_profit"))
    assert item["comments"] == []  # the shill comment is visible from session 2
    world.start_session(2)
    item = data(world.feed_read("fi_inv01_group_profit"))
    assert len(item["comments"]) == 1


def test_unknown_and_future_items_are_errors(world):
    assert not world.feed_read("nope").ok
    assert not world.feed_read("fi_inv01_ad_typo").ok


def test_profile_shows_linked_accounts(world):
    profile = data(world.profile_view("@apex_emma"))
    assert profile["display_name"] == "Emma Carter"
    handles = {a["handle"] for a in profile["linked_accounts"]}
    assert "@apex_emma" not in handles
    assert "emma.carter.wealth" in handles


def test_profile_unknown_is_an_error(world):
    assert not world.profile_view("@nobody").ok


def test_room_open_is_idempotent(world):
    first = data(world.room_open("@apex_emma"))
    second = data(world.room_open("apex_emma"))
    assert first["room_id"] == second["room_id"]
    assert second["created"] is False


def test_room_open_unknown_handle_fails(world):
    assert not world.room_open("@does_not_exist").ok


def test_message_round_trip_and_observation(world):
    room = data(world.room_open("@apex_emma"))["room_id"]
    sent = data(world.message_send(room, "hello"))
    assert sent["seq"] == 1
    messages = data(world.messages_read(room))["messages"]
    assert messages[-1]["text"] == "hello"
    obs = world.session.scalars(
        select(ObservationRow).where(ObservationRow.tool == "message_send")
    ).all()
    assert obs and obs[-1].ref == room


def test_empty_message_rejected(world):
    room = data(world.room_open("@apex_emma"))["room_id"]
    assert not world.message_send(room, "   ").ok


def test_room_join_requires_an_invite(world):
    room_id = "inv01_scam:rm_vip_circle"
    assert not world.room_join(room_id).ok
    world.invite(room_id, "come in")
    assert world.room_join(room_id).ok


def test_attachment_read_returns_text(world):
    att = data(world.attachment_read("at_welcome_pack"))
    assert att["kind"] == "document"
    assert "withdrawals are free" in att["extracted_text"].lower()


def test_attachment_read_unknown(world):
    assert not world.attachment_read("nope").ok


def test_messages_are_not_visible_before_their_session(world):
    room = data(world.room_open("@apex_emma"))["room_id"]
    room_row = world.session.get(RoomRow, room)
    world._append(room_row, "@apex_emma", "future reply", deliver_at_session=3)

    texts = [m["text"] for m in data(world.messages_read(room))["messages"]]
    assert "future reply" not in texts

    world.start_session(3)
    texts = [m["text"] for m in data(world.messages_read(room))["messages"]]
    assert "future reply" in texts


def test_observation_carries_fact_keys(world):
    world.feed_read("fi_inv01_ad")
    obs = world.session.scalars(
        select(ObservationRow).where(ObservationRow.tool == "feed_read")
    ).all()
    assert obs
    assert "F1" in obs[-1].fact_keys
