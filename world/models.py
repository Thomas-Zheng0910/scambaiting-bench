"""SQLAlchemy models for the world database.

One row per world object. Everything the investigator can observe is a row in
one of these tables; everything the counterpart "knows" is either a row here or
an entry in the case JSON that the loader did not need to materialise.

Postgres in production, SQLite in tests. Only generic column types are used, so
the same schema runs on both.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class CaseRow(Base):
    __tablename__ = "case"

    case_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    family: Mapped[str] = mapped_column(String(32))
    truth: Mapped[str] = mapped_column(String(16))  # scam | legitimate
    version: Mapped[str] = mapped_column(String(32), default="1.0.0")
    summary: Mapped[str] = mapped_column(Text, default="")
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class AccountRow(Base):
    __tablename__ = "account"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    counterpart_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    surface: Mapped[str] = mapped_column(String(16))  # feed | messenger
    handle: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(96))
    role_label: Mapped[str] = mapped_column(String(96), default="")
    bio: Mapped[str] = mapped_column(Text, default="")
    headline: Mapped[str] = mapped_column(String(160), default="")
    avatar: Mapped[str] = mapped_column(String(160), default="")
    joined_label: Mapped[str] = mapped_column(String(32), default="")


class CounterpartRow(Base):
    __tablename__ = "counterpart"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(32))
    persona_id: Mapped[str] = mapped_column(String(64))
    policy: Mapped[dict[str, Any]] = mapped_column(JSON)
    truth_awareness: Mapped[str] = mapped_column(String(16))


class RoomRow(Base):
    __tablename__ = "room"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(16))  # dm | group
    title: Mapped[str] = mapped_column(String(160), default="")
    invite_only: Mapped[bool] = mapped_column(Boolean, default=False)
    members: Mapped[list[str]] = mapped_column(JSON, default=list)
    joined: Mapped[list[str]] = mapped_column(JSON, default=list)
    read_up_to: Mapped[int] = mapped_column(Integer, default=0)
    created_in_session: Mapped[int] = mapped_column(Integer, default=1)

    messages: Mapped[list["MessageRow"]] = relationship(back_populates="room", order_by="MessageRow.seq")


class MessageRow(Base):
    __tablename__ = "message"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("room.id"), index=True)
    case_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    counterpart_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sender: Mapped[str] = mapped_column(String(96))
    text: Mapped[str] = mapped_column(Text)
    seq: Mapped[int] = mapped_column(Integer)
    deliver_at_session: Mapped[int] = mapped_column(Integer, default=1, index=True)
    deliver_at_stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    visible: Mapped[bool] = mapped_column(Boolean, default=True)
    edited: Mapped[bool] = mapped_column(Boolean, default=False)
    attachments: Mapped[list[str]] = mapped_column(JSON, default=list)
    fact_keys: Mapped[list[str]] = mapped_column(JSON, default=list)
    obtainable_keys: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[_dt.datetime] = mapped_column(default=_dt.datetime.utcnow)

    room: Mapped[RoomRow] = relationship(back_populates="messages")

    __table_args__ = (UniqueConstraint("room_id", "seq", name="uq_message_room_seq"),)


class FeedItemRow(Base):
    __tablename__ = "feed_item"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    author_handle: Mapped[str] = mapped_column(String(96), index=True)
    author_name: Mapped[str] = mapped_column(String(96), default="")
    author_type: Mapped[str] = mapped_column(String(16), default="person")  # person | page | group
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    visible_from_session: Mapped[int] = mapped_column(Integer, default=1)
    position: Mapped[int] = mapped_column(Integer, default=0, index=True)
    label: Mapped[str | None] = mapped_column(String(16), nullable=True)


class AttachmentRow(Base):
    __tablename__ = "attachment"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # document | photo
    filename: Mapped[str] = mapped_column(String(160), default="")
    text: Mapped[str] = mapped_column(Text, default="")
    caption: Mapped[str] = mapped_column(String(400), default="")
    fact_keys: Mapped[list[str]] = mapped_column(JSON, default=list)
    obtainable_keys: Mapped[list[str]] = mapped_column(JSON, default=list)
    visible_from_stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    decisive: Mapped[bool] = mapped_column(Boolean, default=False)


class FactRow(Base):
    __tablename__ = "fact"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(32), index=True)
    case_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    statement: Mapped[str] = mapped_column(Text)
    carrier: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    carriers: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    available: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    weight: Mapped[str] = mapped_column(String(16), default="moderate")
    requires: Mapped[list[str]] = mapped_column(JSON, default=list)

    __table_args__ = (UniqueConstraint("case_id", "key", name="uq_fact_case_key"),)


class RecordRow(Base):
    __tablename__ = "record_entry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String(64), index=True)
    service: Mapped[str] = mapped_column(String(32), index=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    fact_keys: Mapped[list[str]] = mapped_column(JSON, default=list)


class EventRow(Base):
    __tablename__ = "event"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(64), index=True)
    trigger: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    action: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    fired: Mapped[bool] = mapped_column(Boolean, default=False)
    fired_in_session: Mapped[int | None] = mapped_column(Integer, nullable=True)


class CounterpartStateRow(Base):
    __tablename__ = "counterpart_state"

    counterpart_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    stage: Mapped[str] = mapped_column(String(32), default="intro")
    silent: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_session: Mapped[int] = mapped_column(Integer, default=1)


class RunRow(Base):
    __tablename__ = "run"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    feed_id: Mapped[str] = mapped_column(String(64), default="pilot_v1")
    seed: Mapped[int] = mapped_column(Integer, default=1)
    current_session: Mapped[int] = mapped_column(Integer, default=0)
    ended: Mapped[bool] = mapped_column(Boolean, default=False)
    end_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    round: Mapped[int] = mapped_column(Integer, default=0)
    world_calls: Mapped[int] = mapped_column(Integer, default=0)
    harness_calls: Mapped[int] = mapped_column(Integer, default=0)
    submitted: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    flags: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    started_at: Mapped[_dt.datetime] = mapped_column(default=_dt.datetime.utcnow)


class ObservationRow(Base):
    __tablename__ = "observation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    session: Mapped[int] = mapped_column(Integer)
    round: Mapped[int] = mapped_column(Integer)
    call_index: Mapped[int] = mapped_column(Integer, default=0)
    tool: Mapped[str] = mapped_column(String(32))
    ref: Mapped[str] = mapped_column(String(96), default="")
    fact_keys: Mapped[list[str]] = mapped_column(JSON, default=list)
    session_ref: Mapped[str] = mapped_column(String(64), default="")


class StateChangeRow(Base):
    __tablename__ = "state_change"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    session: Mapped[int] = mapped_column(Integer)
    round: Mapped[int] = mapped_column(Integer, default=0)
    table_name: Mapped[str] = mapped_column(String(32))
    row_id: Mapped[str] = mapped_column(String(64))
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    cause: Mapped[str] = mapped_column(String(64), default="")
