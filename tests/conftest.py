from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from world.actors.engine import CounterpartEngine
from world.actors.llm import ScriptedModel
from world.loader import load_into
from world.models import Base
from world.service import World

CASES = Path(__file__).resolve().parent.parent / "cases"


@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        load_into(s, CASES, "pilot_v1")
        yield s


@pytest.fixture()
def world(session):
    w = World(session=session, run_id="test-run")
    w.start_run("pilot_v1", 1)
    w.start_session(1)
    return w


@pytest.fixture()
def stub_actor():
    def _make(turns):
        return CounterpartEngine(ScriptedModel(turns))

    return _make
