"""FastAPI surface for one run.

Two namespaces:

- `POST /tool/{name}` — the investigator's world tools. This is the only way
  the harness touches world state.
- `POST /admin/...` — session control, used by the runner, never by the agent.

The same `World` object backs both the HTTP app and the in-process calls the
tests make, so there is one implementation of every tool.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from common.tooling import build_tools, call_tool
from world.service import World

WORLD_TOOL_NAMES = [
    "feed_list",
    "feed_read",
    "profile_view",
    "rooms_list",
    "messages_read",
    "attachment_read",
    "room_open",
    "room_join",
    "message_send",
]


class ToolRequest(BaseModel):
    arguments: dict[str, Any] = {}


class SessionRequest(BaseModel):
    session: int


class EndSessionRequest(BaseModel):
    reason: str = "agent_ended"


def world_registry(world: World) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    methods = [getattr(world, name) for name in WORLD_TOOL_NAMES]
    return build_tools(methods, world)


def create_app(world: World) -> FastAPI:
    app = FastAPI(title="scambaiting-bench world", version="0.1.0")
    schemas, registry = world_registry(world)
    app.state.world = world
    app.state.schemas = schemas
    app.state.registry = registry

    @app.get("/health")
    def health() -> dict[str, Any]:
        run = world._run()  # noqa: SLF001 - admin view
        return {"ok": True, "run": run.id, "session": run.current_session, "ended": run.ended}

    @app.get("/admin/schemas")
    def tool_schemas() -> dict[str, Any]:
        return {"tools": schemas}

    @app.post("/tool/{name}")
    def invoke(name: str, body: ToolRequest) -> dict[str, Any]:
        if name not in registry:
            raise HTTPException(status_code=404, detail=f"unknown tool {name}")
        return call_tool(registry, name, body.arguments).to_json()

    @app.post("/admin/start_session")
    def start_session(body: SessionRequest) -> dict[str, Any]:
        return world.start_session(body.session)

    @app.post("/admin/end_session")
    def end_session(body: EndSessionRequest) -> dict[str, Any]:
        return world.end_session(body.reason)

    return app


def serve() -> None:  # pragma: no cover - manual entry point
    """Run one world over HTTP: `python -m world.app`."""
    import os
    from pathlib import Path

    import uvicorn
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from world.loader import load_into
    from world.models import Base

    cases = Path(os.environ.get("CASES_DIR", "cases"))
    feed = os.environ.get("FEED_ID", "pilot_v1")
    db_url = os.environ.get("DATABASE_URL", "sqlite:///world.db")

    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    session = Session(engine)
    load_into(session, cases, feed)

    world = World(session=session, run_id=os.environ.get("RUN_ID", "http"))
    world.start_run(feed, int(os.environ.get("SEED", "1")))
    uvicorn.run(create_app(world), host="127.0.0.1", port=int(os.environ.get("PORT", "8000")))


if __name__ == "__main__":  # pragma: no cover
    serve()
