"""`bench run` — assemble a world, run an investigator, score it.

Two agents are available:
  --agent scripted   the deterministic G1 solver (no model)
  --agent llm        any OpenAI-format tool-calling model, configured by env

The actor (counterpart) always needs a model unless `--actor scripted` is set,
which is what the smoke tests use.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from harness.agents.scripted import scripted_episode
from harness.dispatch import Dispatcher
from harness.session import run_episode
from harness.tools import HarnessTools
from harness.trace import Trace
from scoring.judge import pick_judge
from scoring.metrics import score_run
from scoring.report import write_results
from world.actors.engine import CounterpartEngine
from world.actors.llm import OpenAIChat, ScriptedModel
from world.loader import load_into
from world.models import Base, RunRow
from world.service import World

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "cases"
RUNS = ROOT / "runs"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bench")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="run one episode")
    run_p.add_argument("--feed", default="pilot_v1")
    run_p.add_argument("--run-id", default=None)
    run_p.add_argument("--seed", type=int, default=1)
    run_p.add_argument("--agent", choices=["scripted", "llm"], default="scripted")
    run_p.add_argument("--actor", choices=["scripted", "llm"], default="scripted")
    run_p.add_argument("--sessions", type=int, default=6)
    run_p.add_argument("--out", default=None)
    run_p.add_argument("--db", default=None, help="SQLAlchemy URL; default is a file per run")

    lint_p = sub.add_parser("lint", help="validate case files")
    lint_p.add_argument("paths", nargs="*")

    replay_p = sub.add_parser("replay", help="render a run transcript")
    replay_p.add_argument("run_id")
    replay_p.add_argument("--dir", default=None)
    replay_p.add_argument("--reveal", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "lint":
        return _lint(args.paths)
    if args.command == "replay":
        return _replay(args)
    return _run(args)


def _run(args: argparse.Namespace) -> int:
    run_id = args.run_id or f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"
    out_dir = Path(args.out) if args.out else RUNS / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    db_url = args.db or os.environ.get("DATABASE_URL") or f"sqlite:///{out_dir / 'world.db'}"
    engine = create_engine(db_url)
    if args.db is None and os.environ.get("DATABASE_URL"):
        # A shared database holds exactly one run: rebuild it.
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session = Session(engine)

    loaded = load_into(session, CASES, args.feed)
    world = World(session=session, run_id=run_id)
    run = world.start_run(args.feed, args.seed)

    actor_model = (
        ScriptedModel(
            lambda messages: _scripted_actor(messages),
            fallback="Happy to help. Which part would you like me to explain?",
        )
        if args.actor == "scripted"
        else OpenAIChat()
    )
    world.engine = CounterpartEngine(actor_model)

    tools = HarnessTools(run_id=run_id, world=world)
    dispatcher = Dispatcher(world, tools)

    trace = Trace(
        out_dir / "replay.jsonl",
        {
            "run_id": run_id,
            "feed": args.feed,
            "feed_id": loaded.feed_id,
            "seed": args.seed,
            "agent": args.agent,
            "actor": args.actor,
            "instances": loaded.case_ids,
            "sessions": args.sessions,
        },
    )

    if args.agent == "scripted":
        scripted_episode(world, tools, dispatcher, trace, run, sessions=args.sessions)
    else:
        model = OpenAIChat(model=os.environ.get("INVESTIGATOR_MODEL", "investigator"))
        run_episode(model, world, tools, dispatcher, trace, run, sessions=args.sessions)

    session.commit()
    scores = score_run(world, run, pick_judge())
    session.commit()
    result = {
        "run_id": run_id,
        "feed": args.feed,
        "seed": args.seed,
        "agent": args.agent,
        "actor": args.actor,
        "models": {
            "investigator": os.environ.get("INVESTIGATOR_MODEL", "scripted" if args.agent == "scripted" else ""),
            "actor": os.environ.get("ACTOR_MODEL", "scripted" if args.actor == "scripted" else ""),
        },
        "instances": loaded.case_ids,
        "submission": run.submitted,
        "scores": scores.to_json(),
        "budget_hits": {
            "session_round_limit": 20,
            "world_calls": 80,
            "harness_calls": 40,
        },
    }
    (out_dir / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    write_results(out_dir, result)

    trace.close()
    print(json.dumps({"run_id": run_id, "out": str(out_dir), "scores": result["scores"]}, indent=2))
    return 0


def _scripted_actor(messages: list[dict[str, Any]]) -> Any:
    from world.actors.llm import AssistantTurn

    last = str(messages[-1]["content"]).lower() if messages else ""
    if "payment" in last or "payments go" in last:
        return AssistantTurn(
            text="It goes to a client-funds account at our payment processor, held by Apex Client Trust."
        )
    if "registered" in last or "registration" in last:
        return AssistantTurn(text="We're registered as Apex Capital Ltd, FSR 551203.")
    if False:
        return AssistantTurn(
            text="It goes to a client-funds account at our payment processor, held by Apex Client Trust."
        )
    return AssistantTurn(text="Happy to help. Which part would you like me to explain?")


def _replay(args: argparse.Namespace) -> int:
    from view.replay import write_html

    run_dir = Path(args.dir) if args.dir else RUNS / args.run_id
    log = run_dir / "replay.jsonl"
    if not log.exists():
        print(f"no replay log at {log}")
        return 1
    out = write_html(log, reveal=args.reveal)
    print(str(out))
    return 0


def _lint(paths: list[str]) -> int:
    from world.schema import CaseIn, LintError, lint_case

    targets = [Path(p) for p in paths] or sorted(CASES.glob("*.json"))
    failures = 0
    for path in targets:
        if not path.is_file():
            print(f"MISSING {path}")
            failures += 1
            continue
        try:
            case = CaseIn.model_validate_json(path.read_text(encoding="utf-8"))
            problems = lint_case(case)
        except Exception as exc:  # noqa: BLE001 - lint prints, never raises
            print(f"FAIL    {path.name}: {exc}")
            failures += 1
            continue
        if problems:
            failures += 1
            print(f"FAIL    {path.name}")
            for problem in problems:
                print(f"  - {problem}")
        else:
            print(f"ok      {path.name}  ({case.case_id}, {case.truth})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
