from __future__ import annotations

from copy import deepcopy

import pytest

from harness.context import trim_history
from world.actors.llm import AssistantTurn, ToolCall


HEAD = [
    {"role": "system", "content": "mission"},
    {"role": "user", "content": "session brief"},
]
OMITTED = {"role": "system", "content": "(earlier turns omitted)"}


def tool_round(prefix: str, count: int) -> list[dict]:
    calls = [ToolCall(f"{prefix}-{i}", "feed_list", {}) for i in range(count)]
    return [AssistantTurn(tool_calls=calls).to_message()] + [
        {"role": "tool", "tool_call_id": call.id, "content": "{}"} for call in calls
    ]


def assert_complete_tool_groups(messages: list[dict]) -> None:
    pending: set[str] = set()
    for message in messages:
        if message["role"] == "tool":
            assert message["tool_call_id"] in pending
            pending.remove(message["tool_call_id"])
        else:
            assert not pending
            pending = {call["id"] for call in message.get("tool_calls", [])}
    assert not pending


@pytest.mark.parametrize("keep", [1, 2, 3])
def test_trimming_inside_a_batch_retains_its_call_and_all_results(keep):
    latest = tool_round("latest", 3)
    messages = HEAD + tool_round("old", 1) + latest
    original = deepcopy(messages)

    trimmed = trim_history(messages, keep=keep)

    assert trimmed == HEAD + [OMITTED] + latest
    assert_complete_tool_groups(trimmed)
    assert messages == original


def test_default_window_does_not_split_a_mixed_size_tool_round():
    rounds = [tool_round(str(i), 2 if i == 1 else 1) for i in range(13)]
    messages = HEAD + [message for group in rounds for message in group]

    trimmed = trim_history(messages)

    assert trimmed == HEAD + [OMITTED] + messages[4:]
    assert_complete_tool_groups(trimmed)


def test_a_single_oversized_tool_round_is_kept_without_an_omission_marker():
    messages = HEAD + tool_round("large", 30)

    assert trim_history(messages) == messages
    assert_complete_tool_groups(trim_history(messages))


def test_repeated_trimming_keeps_one_marker_and_complete_groups():
    first = trim_history(HEAD + tool_round("old", 1) + tool_round("middle", 3), keep=2)
    latest = tool_round("latest", 3)

    trimmed = trim_history(first + latest, keep=2)

    assert trimmed == HEAD + [OMITTED] + latest
    assert_complete_tool_groups(trimmed)


def test_trimming_at_a_round_boundary_preserves_the_requested_window():
    latest = tool_round("latest", 2)
    messages = HEAD + tool_round("old", 1) + latest

    assert trim_history(messages, keep=3) == HEAD + [OMITTED] + latest


def test_short_and_text_only_histories_are_preserved_as_expected():
    short = HEAD + tool_round("short", 1)
    assert trim_history(short) == short
    text_turns = [{"role": "assistant", "content": str(i)} for i in range(4)]
    assert trim_history(HEAD + text_turns, keep=2) == HEAD + [OMITTED] + text_turns[-2:]


@pytest.mark.parametrize("keep", [0, -1])
def test_history_window_must_be_positive(keep):
    with pytest.raises(ValueError, match="positive"):
        trim_history(HEAD, keep=keep)
