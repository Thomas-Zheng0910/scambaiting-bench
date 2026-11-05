"""The session loop.

One assistant turn per round. Tool calls are executed and their results go back
into context. A round with no tool calls still costs a round: thinking is not
free, and letting a model burn rounds by talking gives it no advantage.

Budgets end the session, never the run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from harness.context import session_brief, system_prompt, trim_history, truncate
from harness.dispatch import Dispatcher
from harness.trace import Trace
from world.actors.llm import ChatModel
from world.models import RunRow
from world.service import World

MAX_ROUNDS = 20
SESSIONS = 6


@dataclass
class SessionOutcome:
    session: int
    rounds: int
    reason: str
    calls: int


def run_session(
    model: ChatModel,
    world: World,
    tools: Any,
    dispatcher: Dispatcher,
    trace: Trace,
    run: RunRow,
    session_no: int,
    *,
    max_rounds: int = MAX_ROUNDS,
) -> SessionOutcome:
    started = world.start_session(session_no)
    dispatcher.reset_session_budgets()
    tools._ended = False  # noqa: SLF001 - the runner owns the flag
    tools._end_reason = None  # noqa: SLF001
    trace.session_start(session_no, started.get("events_fired", []))

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt()},
        {"role": "user", "content": session_brief(world, run, tools)},
    ]

    rounds = 0
    calls = 0
    stop_reason: str | None = None
    while rounds < max_rounds:
        stop_reason = tools.end_reason or dispatcher.budget_exhausted_reason()
        if stop_reason:
            break

        run.round = rounds
        world.round_no = rounds
        world.call_index = 0

        turn = model.complete(messages, dispatcher.schemas())
        trace.model(
            session_no,
            rounds,
            turn.text,
            [{"name": c.name, "arguments": c.arguments} for c in turn.tool_calls],
        )
        messages.append(turn.to_message())
        rounds += 1

        if turn.tool_calls:
            for call in turn.tool_calls:
                result = dispatcher.call(call.name, call.arguments)
                calls += 1
                trace.tool(session_no, rounds, call.name, call.arguments, result.ok, result.to_json())
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": truncate(call.name, result.to_json()),
                    }
                )
                stop_reason = tools.end_reason or dispatcher.budget_exhausted_reason()
                if stop_reason:
                    # Later calls in this batch must have no effects. This
                    # context is discarded when the next session starts.
                    break

        if stop_reason:
            break
        messages = trim_history(messages)

    reason = stop_reason or ("round_limit" if rounds >= max_rounds else "agent_ended")
    world.end_session(reason)
    trace.session_end(session_no, reason)
    return SessionOutcome(session_no, rounds, reason, calls)


def run_episode(
    model: ChatModel,
    world: World,
    tools: Any,
    dispatcher: Dispatcher,
    trace: Trace,
    run: RunRow,
    *,
    sessions: int = SESSIONS,
    max_rounds: int = MAX_ROUNDS,
) -> list[SessionOutcome]:
    outcomes: list[SessionOutcome] = []
    for session_no in range(1, sessions + 1):
        if run.ended:
            break
        outcome = run_session(
            model, world, tools, dispatcher, trace, run, session_no, max_rounds=max_rounds
        )
        outcomes.append(outcome)
        if tools.ended:
            # end_session ends the session; the run continues to the next one
            tools._ended = False  # noqa: SLF001
    if not run.ended:
        world.end_run("session_limit")
    return outcomes
