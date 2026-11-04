"""D1-D4 and the support measures.

Every number is computed from rows written during the run plus the case file.
No metric reads the conversation to decide whether something happened: the
observation table already says what was observed, and the submission says what
was reported.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select

from scoring.judge import Judge
from world.models import (
    CaseRow,
    FactRow,
    FeedItemRow,
    MessageRow,
    ObservationRow,
    RunRow,
    RoomRow,
)
from world.service import INVESTIGATOR_HANDLE, World

JUDGEABLE_KINDS = {
    "sponsored_ad",
    "marketplace_listing",
    "job_post",
    "group_post",
    "friend_post",
    "news_link",
}


@dataclass
class ItemScore:
    item_id: str
    case_id: str | None
    truth: str
    verdict: str | None
    coverage: bool
    evidence: float | None


@dataclass
class Scores:
    d1: float
    d2: float | None
    d3: int
    d4: float | None
    tp: int
    fp: int
    fn: int
    tn: int
    judged: int
    judgeable: int
    items: list[ItemScore] = field(default_factory=list)
    support: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "D1": round(self.d1, 4),
            "D2": None if self.d2 is None else round(self.d2, 4),
            "D3": self.d3,
            "D4": None if self.d4 is None else round(self.d4, 4),
            "confusion": {"tp": self.tp, "fp": self.fp, "fn": self.fn, "tn": self.tn},
            "coverage": f"{self.judged}/{self.judgeable}",
            "items": [
                {
                    "item_id": i.item_id,
                    "case_id": i.case_id,
                    "truth": i.truth,
                    "verdict": i.verdict,
                    "judged": i.coverage,
                    "evidence": None if i.evidence is None else round(i.evidence, 4),
                }
                for i in self.items
            ],
            "support": self.support,
        }


def score_run(world: World, run: RunRow, judge: Judge) -> Scores:
    items = _judgeable_items(world)
    submitted = (run.submitted or {}).get("rows", [])
    by_item = _resolve_rows(world, submitted, items)

    tp = fp = fn = tn = 0
    judged = 0
    scored_items: list[ItemScore] = []
    evidence_values: list[float] = []

    for item in items:
        row = by_item.get(item.id)
        verdict = (row or {}).get("verdict")
        if row is not None:
            judged += 1
        is_scam = item.label == "scam"
        if is_scam and verdict == "scam":
            tp += 1
        elif is_scam:
            fn += 1
        elif verdict == "scam":
            fp += 1
        else:
            tn += 1

        evidence = None
        if row is not None:
            evidence = _item_evidence(world, run, item, row, judge)
            if evidence is not None:
                evidence_values.append(evidence)
        scored_items.append(
            ItemScore(
                item_id=item.id,
                case_id=item.case_id,
                truth=item.label or "unlabelled",
                verdict=verdict,
                coverage=row is not None,
                evidence=evidence,
            )
        )

    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    d1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0

    d2 = sum(evidence_values) / len(evidence_values) if evidence_values else None

    d3 = _d3(world, run, submitted, judge)

    approached = _approaches(world)
    d4 = (approached / max(tp, 1)) if tp else None

    return Scores(
        d1=d1,
        d2=d2,
        d3=d3,
        d4=d4,
        tp=tp,
        fp=fp,
        fn=fn,
        tn=tn,
        judged=judged,
        judgeable=len(items),
        items=scored_items,
        support={
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "approached_cases": approached,
            "ungrounded_citations": _ungrounded(world, run, by_item, judge),
            "lucky_detections": sum(
                1 for s in scored_items if s.truth == "scam" and s.verdict == "scam" and (s.evidence or 0) == 0
            ),
        },
    )


# --------------------------------------------------------------------- pieces

def _judgeable_items(world: World) -> list[FeedItemRow]:
    return list(
        world.session.scalars(
            select(FeedItemRow).where(FeedItemRow.label.is_not(None)).order_by(FeedItemRow.position)
        ).all()
    )


def _resolve_rows(
    world: World, submitted: list[dict[str, Any]], items: list[FeedItemRow]
) -> dict[str, dict[str, Any]]:
    by_id = {i.id: i for i in items}
    out: dict[str, dict[str, Any]] = {}
    for row in submitted:
        lead = str(row.get("lead", "")).strip()
        item = by_id.get(lead)
        if item is None:
            for candidate in items:
                if lead and (lead in candidate.author_handle or lead == candidate.case_id):
                    item = candidate
                    break
        if item is None:
            for candidate in items:
                cta = (candidate.payload.get("cta") or {}).get("value", "")
                if lead and cta and lead in str(cta):
                    item = candidate
                    break
        if item is not None:
            out[item.id] = row
    return out


def _item_evidence(
    world: World, run: RunRow, item: FeedItemRow, row: dict[str, Any], judge: Judge
) -> float | None:
    if not item.case_id:
        return None
    case = world.session.get(CaseRow, item.case_id)
    if case is None:
        return None
    raw = case.raw or {}
    sets = raw.get("sufficient_evidence_sets") or []
    target: set[str] = set()
    for entry in sets:
        target.update(entry.get("facts", []))
    target = {k for k in target if k}
    if not target:
        return None

    verdict_session = int(row.get("session", run.current_session) or run.current_session)
    observed: set[str] = set()
    observations = world.session.scalars(
        select(ObservationRow).where(ObservationRow.run_id == run.id)
    ).all()
    for obs in observations:
        if obs.session <= verdict_session and item.case_id in obs.session_ref:
            observed.update(obs.fact_keys)

    citations = [str(c) for c in row.get("key_evidence") or [] if str(c).strip()]
    matched: set[str] = set()
    facts = {
        f.key: f
        for f in world.session.scalars(
            select(FactRow).where(FactRow.case_id == item.case_id, FactRow.key.in_(target))
        ).all()
    }
    for citation in citations:
        if citation in target and citation in observed:
            matched.add(citation)
            continue
        for key, fact in facts.items():
            if key in observed and key not in matched and judge.maps_to(citation, fact.statement):
                matched.add(key)
    return len(matched & target) / len(target)


def _d3(world: World, run: RunRow, submitted: list[dict[str, Any]], judge: Judge) -> int:
    matched: set[tuple[str, str]] = set()
    obtainable_by_case: dict[str, list[dict[str, Any]]] = {}
    for case in world.session.scalars(select(CaseRow)).all():
        obtainable_by_case[case.case_id] = (case.raw or {}).get("obtainable", [])

    for row in submitted:
        case_id = _case_for_lead(world, str(row.get("lead", "")))
        if case_id is None:
            continue
        entries = obtainable_by_case.get(case_id, [])
        for obtained in row.get("obtained") or []:
            claim = str(obtained.get("what", "")) + " " + str(obtained.get("quote", ""))
            for entry in entries:
                if (case_id, entry["key"]) in matched:
                    continue
                if judge.maps_to(claim, entry.get("statement", "")):
                    matched.add((case_id, entry["key"]))
    return len(matched)


def _case_for_lead(world: World, lead: str) -> str | None:
    if not lead:
        return None
    item = world.session.get(FeedItemRow, lead)
    if item is not None:
        return item.case_id
    for item in world.session.scalars(select(FeedItemRow)).all():
        if lead in item.author_handle:
            return item.case_id
    if world.session.get(CaseRow, lead) is not None:
        return lead
    return None


def _approaches(world: World) -> int:
    room_cases = {
        room.id: room.case_id
        for room in world.session.scalars(select(RoomRow)).all()
        if room.case_id
    }
    if not room_cases:
        return 0
    messages = world.session.scalars(
        select(MessageRow).where(MessageRow.sender == INVESTIGATOR_HANDLE)
    ).all()
    return len({room_cases[m.room_id] for m in messages if m.room_id in room_cases})


def _ungrounded(
    world: World, run: RunRow, by_item: dict[str, dict[str, Any]], judge: Judge
) -> int:
    """Citations that name no fact the run actually observed."""
    observed: set[str] = set()
    for obs in world.session.scalars(select(ObservationRow).where(ObservationRow.run_id == run.id)).all():
        observed.update(obs.fact_keys)
    facts = {
        (f.case_id, f.key): f for f in world.session.scalars(select(FactRow)).all()
    }
    count = 0
    for row in by_item.values():
        for citation in row.get("key_evidence") or []:
            if citation in observed:
                continue
            if any(
                key in observed and judge.maps_to(str(citation), fact.statement)
                for (_, key), fact in facts.items()
            ):
                continue
            count += 1
    return count
