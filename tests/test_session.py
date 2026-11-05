from __future__ import annotations

import json

import pytest

from harness.dispatch import HARNESS_CALL_LIMIT, WORLD_CALL_LIMIT, Dispatcher
from harness.session import run_episode, run_session
from harness.tools import HarnessTools
from harness.trace import Trace
from world.actors.llm import AssistantTurn, ScriptedModel, ToolCall


@pytest.fixture()
def harness(world, tmp_path):
    tools = HarnessTools(run_id=world.run_id, world=world)
    dispatcher = Dispatcher(world, tools)
    trace = Trace(tmp_path / "replay.jsonl", {})
    yield tools, dispatcher, trace, tools.run
    trace.close()


def calls(name, arguments, count):
    return [ToolCall(f"{name}-{i}", name, arguments) for i in range(count)]


@pytest.mark.parametrize(
    ("name", "arguments", "limit", "counter", "reason"),
    [
        ("feed_list", {}, WORLD_CALL_LIMIT, "world_calls", "world_call_limit"),
        ("notes", {"op": "list"}, HARNESS_CALL_LIMIT, "harness_calls", "harness_call_limit"),
    ],
)
@pytest.mark.parametrize("extra_calls", [0, 1])
def test_call_budget_stops_the_session_without_another_model_turn(
    world, harness, name, arguments, limit, counter, reason, extra_calls
):
    tools, dispatcher, trace, run = harness
    model = ScriptedModel([
        AssistantTurn(tool_calls=calls(name, arguments, limit + extra_calls)),
        AssistantTurn(tool_calls=[ToolCall("late", "flag_item", {
            "item_id": "fi_inv01_ad", "verdict": "scam",
        })]),
    ])

    outcome = run_session(model, world, tools, dispatcher, trace, run, 1, max_rounds=3)

    assert outcome.reason == reason
    assert outcome.rounds == 1
    assert outcome.calls == limit
    assert len(model.calls) == 1
    assert getattr(run, counter) == limit
    assert len(dispatcher.log) == limit
    assert not run.flags
    assert not run.ended
    records = [json.loads(line) for line in trace.path.read_text().splitlines()]
    assert records[-1] == {"type": "session_end", "session": 1, "reason": reason}
    assert len([r for r in records if r["type"] == "call"]) == limit


@pytest.mark.parametrize(
    ("name", "arguments", "limit", "reason"),
    [
        ("feed_list", {}, WORLD_CALL_LIMIT, "world_call_limit"),
        ("notes", {"op": "list"}, HARNESS_CALL_LIMIT, "harness_call_limit"),
    ],
)
def test_hitting_either_budget_skips_other_tool_types_in_the_same_batch(
    world, harness, name, arguments, limit, reason
):
    tools, dispatcher, trace, run = harness
    # This would mutate notes or create observations if dispatched after the limit.
    late_call = (
        ToolCall("late", "notes", {"op": "upsert", "case_key": "late", "fields": {"claims": ["late"]}})
        if name == "feed_list"
        else ToolCall("late", "feed_list", {})
    )
    model = ScriptedModel([AssistantTurn(tool_calls=calls(name, arguments, limit) + [late_call])])

    outcome = run_session(model, world, tools, dispatcher, trace, run, 1, max_rounds=1)

    assert outcome.reason == reason
    assert outcome.calls == limit
    assert [entry["tool"] for entry in dispatcher.log] == [name] * limit
    assert (run.world_calls, run.harness_calls) == (
        (limit, 0) if name == "feed_list" else (0, limit)
    )
    assert "late" not in (run.notes or {})


@pytest.mark.parametrize("reason", ["out_of_ideas", "submitted"])
def test_end_session_stops_the_rest_of_a_batch(world, harness, reason):
    tools, dispatcher, trace, run = harness
    model = ScriptedModel([AssistantTurn(tool_calls=[
        ToolCall("end", "end_session", {"reason": reason, "plan": "read replies"}),
        ToolCall("late", "flag_item", {"item_id": "fi_inv01_ad", "verdict": "scam"}),
        ToolCall("late-world", "feed_list", {}),
    ])])

    outcome = run_session(model, world, tools, dispatcher, trace, run, 1)

    assert outcome.reason == reason
    assert outcome.calls == 1
    assert len(model.calls) == 1
    assert [entry["tool"] for entry in dispatcher.log] == ["end_session"]
    assert not run.flags
    assert run.world_calls == 0
    assert run.notes["__session_plan__"]["plan"] == "read replies"
    assert run.ended == (reason == "submitted")


def test_explicit_end_reason_wins_when_the_same_call_uses_the_last_budget(world, harness):
    tools, dispatcher, trace, run = harness
    model = ScriptedModel([AssistantTurn(tool_calls=[
        *calls("notes", {"op": "list"}, HARNESS_CALL_LIMIT - 1),
        ToolCall("end", "end_session", {"reason": "blocked"}),
        ToolCall("late", "feed_list", {}),
    ])])

    outcome = run_session(model, world, tools, dispatcher, trace, run, 1)

    assert outcome.reason == "blocked"
    assert outcome.calls == HARNESS_CALL_LIMIT
    assert run.world_calls == 0


@pytest.mark.parametrize(
    ("name", "arguments", "limit", "reason"),
    [
        ("feed_read", {"item_id": "missing"}, WORLD_CALL_LIMIT, "world_call_limit"),
        ("notes", {"op": "get"}, HARNESS_CALL_LIMIT, "harness_call_limit"),
    ],
)
def test_failed_tool_calls_still_exhaust_the_budget(world, harness, name, arguments, limit, reason):
    tools, dispatcher, trace, run = harness
    model = ScriptedModel([AssistantTurn(tool_calls=calls(name, arguments, limit))])

    outcome = run_session(model, world, tools, dispatcher, trace, run, 1, max_rounds=3)

    assert outcome.reason == reason
    assert outcome.calls == limit
    assert len(model.calls) == 1
    assert all(not entry["ok"] for entry in dispatcher.log)


def test_text_only_turns_still_consume_the_round_budget(world, harness):
    tools, dispatcher, trace, run = harness
    model = ScriptedModel()

    outcome = run_session(model, world, tools, dispatcher, trace, run, 1, max_rounds=2)

    assert outcome.reason == "round_limit"
    assert outcome.rounds == len(model.calls) == 2
    assert outcome.calls == 0
    assert not run.ended


@pytest.mark.parametrize(
    ("name", "arguments", "limit", "reason"),
    [
        ("feed_list", {}, WORLD_CALL_LIMIT, "world_call_limit"),
        ("notes", {"op": "list"}, HARNESS_CALL_LIMIT, "harness_call_limit"),
    ],
)
def test_episode_continues_with_fresh_budgets_after_a_limit(
    world, harness, name, arguments, limit, reason
):
    tools, dispatcher, trace, run = harness
    model = ScriptedModel([
        AssistantTurn(tool_calls=calls(name, arguments, limit)),
        AssistantTurn(tool_calls=[
            ToolCall("read", "feed_list", {}),
            ToolCall("end", "end_session", {"reason": "out_of_ideas"}),
            ToolCall("late", "flag_item", {"item_id": "fi_inv01_ad", "verdict": "scam"}),
        ]),
    ])

    outcomes = run_episode(model, world, tools, dispatcher, trace, run, sessions=2, max_rounds=3)

    assert [outcome.reason for outcome in outcomes] == [reason, "out_of_ideas"]
    assert [outcome.calls for outcome in outcomes] == [limit, 2]
    assert len(model.calls) == 2
    assert (run.world_calls, run.harness_calls) == (1, 1)
    assert not run.flags
    assert run.ended and run.end_reason == "session_limit"


def test_explicit_session_end_does_not_block_tools_in_the_next_session(world, harness):
    tools, dispatcher, trace, run = harness
    model = ScriptedModel([
        AssistantTurn(tool_calls=[ToolCall("end-1", "end_session", {"reason": "blocked"})]),
        AssistantTurn(tool_calls=[
            ToolCall("read", "feed_list", {}),
            ToolCall("end-2", "end_session", {"reason": "out_of_ideas"}),
        ]),
    ])

    outcomes = run_episode(model, world, tools, dispatcher, trace, run, sessions=2)

    assert [outcome.reason for outcome in outcomes] == ["blocked", "out_of_ideas"]
    assert [outcome.calls for outcome in outcomes] == [1, 2]
    assert len(model.calls) == 2
