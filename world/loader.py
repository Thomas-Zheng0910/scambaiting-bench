"""Case JSON -> world rows.

The loader is the only writer of authored content. It validates every case with
the pydantic schema, lints cross-references, and then inserts rows. It never
runs at request time.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from world.models import (
    AccountRow,
    AttachmentRow,
    CaseRow,
    CounterpartRow,
    EventRow,
    FactRow,
    FeedItemRow,
    MessageRow,
    RecordRow,
    RoomRow,
)
from world.records import genuine_accounts
from world.schema import CaseIn, FeedFileIn, LintError, lint_case

INVESTIGATOR_HANDLE = "@jordan.lee"
INVESTIGATOR_NAME = "Jordan Lee"


@dataclass
class LoadedFeed:
    feed_id: str
    seed: int
    case_ids: list[str]
    item_order: list[str]


def load_feed(cases_dir: Path, feed_id: str) -> LoadedFeed:
    """Validate every case in a feed and return its metadata without writing."""
    feed_path = cases_dir / "feeds" / f"{feed_id}.json"
    if not feed_path.exists():
        raise FileNotFoundError(feed_path)
    feed = FeedFileIn.model_validate_json(feed_path.read_text())

    cases: list[CaseIn] = []
    for case_id in feed.instances:
        path = cases_dir / f"{case_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"{case_id}: {path} missing")
        case = CaseIn.model_validate_json(path.read_text())
        problems = lint_case(case)
        if problems:
            raise LintError(case_id, problems)
        if case_id not in (case.case_id, case.case_id.replace("_", ".")):
            raise LintError(case_id, [f"file name does not match case_id {case.case_id!r}"])
        cases.append(case)

    filler_path = cases_dir / "filler.json"
    filler = CaseIn.model_validate_json(filler_path.read_text()) if filler_path.exists() else None

    order = _assemble_order(cases, filler, feed.seed, feed.order_constraints)
    return LoadedFeed(feed.feed_id, feed.seed, list(feed.instances), order)


def load_into(session: Session, cases_dir: Path, feed_id: str) -> LoadedFeed:
    """Write a feed's cases into an empty world."""
    loaded = load_feed(cases_dir, feed_id)

    for account in genuine_accounts():
        session.add(account)

    for case_id in loaded.case_ids:
        case = CaseIn.model_validate_json((cases_dir / f"{case_id}.json").read_text())
        _insert_case(session, case)

    filler_path = cases_dir / "filler.json"
    if filler_path.exists():
        filler = CaseIn.model_validate_json(filler_path.read_text())
        _insert_case(session, filler)

    _apply_order(session, loaded.item_order, loaded.seed)
    session.flush()
    return loaded


def _insert_case(session: Session, case: CaseIn) -> None:
    session.add(
        CaseRow(
            case_id=case.case_id,
            family=case.family,
            truth=case.truth,
            version=case.version,
            summary=case.summary,
            raw=case.model_dump(mode="json"),
        )
    )

    for cp in case.counterparts:
        session.add(
            CounterpartRow(
                id=f"{case.case_id}:{cp.id}",
                case_id=case.case_id,
                role=cp.role,
                persona_id=cp.id,
                policy=cp.policy.model_dump(mode="json"),
                truth_awareness=cp.policy.truth_awareness,
            )
        )
        for acct in cp.accounts:
            session.add(
                AccountRow(
                    id=f"{case.case_id}:{cp.id}:{acct.handle}",
                    case_id=case.case_id,
                    counterpart_id=f"{case.case_id}:{cp.id}",
                    surface=acct.surface,
                    handle=acct.handle,
                    display_name=cp.persona.name,
                    role_label=acct.role_label or cp.persona.headline,
                    bio=cp.persona.bio,
                    headline=cp.persona.headline,
                    avatar=cp.persona.avatar,
                    joined_label=acct.joined_label,
                )
            )

    for item in case.feed_items:
        author = item.author or {}
        handle = str(author.get("handle") or author.get("name") or "unknown")
        payload = item.model_dump(mode="json")
        payload.pop("author", None)
        payload.pop("visible", None)
        session.add(
            FeedItemRow(
                id=item.id,
                case_id=case.case_id,
                kind=item.kind,
                author_handle=handle,
                author_name=str(author.get("name") or handle),
                author_type=str(author.get("type") or "person"),
                payload=payload,
                visible_from_session=int((item.visible or {}).get("from_session", 1)),
                label=item.label
                if item.label is not None
                else (
                    None
                    if case.case_id == "filler" or not item.judgeable
                    else ("scam" if case.truth == "scam" else "legitimate")
                ),
            )
        )

    for att in case.attachments:
        session.add(
            AttachmentRow(
                id=att.id,
                case_id=case.case_id,
                kind=att.kind,
                filename=att.filename,
                text=att.text,
                caption=att.caption,
                fact_keys=list(att.fact_keys),
                obtainable_keys=list(att.obtainable_keys),
                visible_from_stage=att.visible_from_stage,
                decisive=att.decisive,
            )
        )

    for fact in case.facts:
        session.add(
            FactRow(
                key=fact.key,
                case_id=case.case_id,
                kind=fact.kind,
                statement=fact.statement,
                carrier=fact.carrier,
                carriers=list(fact.carriers),
                available=dict(fact.available),
                weight=fact.weight,
                requires=list(fact.requires),
            )
        )

    for record in case.records:
        session.add(
            RecordRow(
                case_id=case.case_id,
                service=record.service,
                data=dict(record.data),
                fact_keys=list(record.fact_keys),
            )
        )

    for event in case.events:
        session.add(
            EventRow(
                id=f"{case.case_id}:{event.id}",
                case_id=case.case_id,
                trigger=dict(event.trigger),
                action=event.action,
                payload=dict(event.payload),
            )
        )

    for svc in case.fake_services:
        session.add(
            AccountRow(
                id=f"{case.case_id}:fake:{svc.handle.lstrip('@')}",
                case_id=case.case_id,
                counterpart_id=None,
                surface="messenger",
                handle=svc.handle,
                display_name=svc.name,
                role_label="Public records",
                bio="We answer from public records.",
            )
        )
        session.add(
            RecordRow(
                case_id=case.case_id,
                service="fake",
                data={"reply": svc.reply},
                fact_keys=list(svc.fact_keys),
            )
        )

    for room in case.rooms:
        room_id = room.id if room.id.startswith(case.case_id) else f"{case.case_id}:{room.id}"
        members = list(room.members) or [
            a.handle for cp in case.counterparts for a in cp.accounts if a.surface == "messenger"
        ]
        session.add(
            RoomRow(
                id=room_id,
                case_id=case.case_id,
                kind=room.kind,
                title=room.title,
                invite_only=room.invite_only,
                members=members,
                joined=[INVESTIGATOR_HANDLE] if not room.invite_only else [],
            )
        )
        for i, msg in enumerate(room.seed_messages, start=1):
            deliver = msg.deliver or {}
            cp_id = next(
                (
                    f"{case.case_id}:{cp.id}"
                    for cp in case.counterparts
                    if any(a.handle == msg.from_ for a in cp.accounts)
                ),
                None,
            )
            session.add(
                MessageRow(
                    id=f"{room_id}:seed:{i}",
                    room_id=room_id,
                    case_id=case.case_id,
                    counterpart_id=cp_id,
                    sender=msg.from_,
                    text=msg.text,
                    seq=i,
                    deliver_at_session=int(deliver.get("session", 1)),
                    deliver_at_stage=deliver.get("after_stage"),
                    attachments=list(msg.attachments),
                )
            )


def _apply_order(session: Session, order: Iterable[str], seed: int) -> None:
    for position, item_id in enumerate(order):
        row = session.get(FeedItemRow, item_id)
        if row is None:
            raise KeyError(f"feed order names unknown item {item_id}")
        row.position = position


def _assemble_order(
    cases: list[CaseIn],
    filler: CaseIn | None,
    seed: int,
    constraints: list[str],
) -> list[str]:
    """Deterministic interleave that honours the feed's order constraints.

    Case items get evenly spaced slots; filler fills the rest. Constraints are
    then enforced by swapping, never by dropping an item, so the judgeable set
    is identical across seeds and only the order changes.
    """
    rng = random.Random(seed)
    case_items: list[tuple[str, str, str]] = []  # id, case_id, truth
    for case in cases:
        for item in case.feed_items:
            if item.kind != "comment":
                case_items.append((item.id, case.case_id, case.truth))
    filler_items = [i.id for i in filler.feed_items] if filler else []
    rng.shuffle(case_items)
    rng.shuffle(filler_items)

    total = len(case_items) + len(filler_items)
    if total == 0:
        return []
    if not case_items:
        return filler_items

    k = len(case_items)
    slots: list[str | None] = [None] * total
    positions = [max(1, min(total - 1, (i + 1) * total // (k + 1))) for i in range(k)]
    positions = _repair_positions(positions, total, constraints)

    # Marketplace items must sit late; pair them with the latest slots.
    ordering = list(case_items)
    mkt = [c for c in ordering if c[1].startswith("mkt")]
    rest = [c for c in ordering if not c[1].startswith("mkt")]
    ordering = rest + mkt

    # At least one scam early, if the constraint asks for it.
    wants_scam_early = any("scam" in c and "12" in c for c in constraints)
    if wants_scam_early and not any(
        truth == "scam" and pos < 12 for (_, _, truth), pos in zip(ordering[:k], positions)
    ):
        scam_idx = next((i for i, c in enumerate(ordering) if c[2] == "scam"), None)
        if scam_idx is not None:
            ordering.insert(0, ordering.pop(scam_idx))

    for (item_id, _, _), pos in zip(ordering, positions):
        slots[pos] = item_id

    spare = [i for i, s in enumerate(slots) if s is None]
    for pos, item_id in zip(spare, filler_items):
        slots[pos] = item_id
    leftover = filler_items[len(spare):]

    order = [s for s in slots if s]
    order.extend(leftover)
    return order


def _repair_positions(positions: list[int], total: int, constraints: list[str]) -> list[int]:
    """Make slot positions distinct, non-adjacent, and satisfying the constraints."""
    positions = sorted({min(p, total - 1) for p in positions})
    while len(positions) < len(set(positions)) or len(positions) < 1:
        break
    # push right until every pair has a gap of at least 2
    for i in range(1, len(positions)):
        if positions[i] - positions[i - 1] < 2:
            positions[i] = min(total - 1, positions[i - 1] + 2)
    # if the last slot collided with the end, pull the run left
    if positions and positions[-1] >= total:
        shift = positions[-1] - (total - 1)
        positions = [max(0, p - shift) for p in positions]

    wants_late = any("beyond position 12" in c for c in constraints)
    if wants_late and total > 13 and max(positions) <= 12:
        positions[-1] = 13
        positions = sorted(set(positions))

    wants_early = any("within the first 12" in c for c in constraints)
    if wants_early and min(positions) > 11:
        positions[0] = 11
    return sorted(set(positions))


def clear_world(session: Session) -> None:
    """Drop every loaded row. Used by tests and by `bench reset`."""
    for model in (
        MessageRow,
        RoomRow,
        FeedItemRow,
        AttachmentRow,
        FactRow,
        RecordRow,
        EventRow,
        AccountRow,
        CounterpartRow,
        CaseRow,
    ):
        session.execute(delete(model))
    session.flush()
