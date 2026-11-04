"""Record services.

Three genuine services answer from the loaded record tables and nothing else.
A scam case may also supply a fake service, which answers from doctored data in
a reassuring tone. Both are ordinary messenger accounts, so choosing which one
to trust is a judgement call, not a tooling difference.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from world.models import AccountRow, RecordRow

GENUINE: dict[str, str] = {
    "@register_enquiries": "register",
    "@company_records": "companies",
    "@domain_records": "domains",
}

SERVICE_TITLES = {
    "register": "Register Enquiries",
    "companies": "Company Records Desk",
    "domains": "Domain Records",
}

NO_MATCH = (
    "I can only provide record details. Please name the firm, company number or domain "
    "you are asking about."
)
EVALUATIVE = (
    "I can only provide record details.",
)


@dataclass
class RecordAnswer:
    text: str
    fact_keys: list[str]


def is_record_handle(handle: str) -> bool:
    return handle in GENUINE


def genuine_accounts() -> list[AccountRow]:
    return [
        AccountRow(
            id=f"service:{handle.lstrip('@')}",
            case_id=None,
            counterpart_id=None,
            surface="messenger",
            handle=handle,
            display_name=SERVICE_TITLES[service],
            role_label="Public records",
            bio="We answer from public records only.",
        )
        for handle, service in GENUINE.items()
    ]


def answer(world: Any, service: str, question: str, case_id: str | None = None) -> RecordAnswer:
    """Answer a question from the record table for `service`."""
    if service not in GENUINE.values():
        return _fake_answer(world, case_id, question)

    rows = world.session.scalars(select(RecordRow).where(RecordRow.service == service)).all()
    best = _best_match(rows, question)
    if best is None:
        return RecordAnswer(NO_MATCH, [])

    data = best.data
    if service == "register":
        text = (
            f"Register entry — FRN {data.get('frn', '?')}: {data.get('name', '?')}. "
            f"Status: {data.get('status', '?')}. "
            f"Official domain: {data.get('official_domain', 'not listed')}. "
            f"Official phone: {data.get('official_phone', 'not listed')}."
        )
        warning = data.get("warning_list") or []
        if warning:
            text += " Warning list: " + "; ".join(str(w) for w in warning) + "."
    elif service == "companies":
        officers = ", ".join(str(o) for o in data.get("officers") or []) or "none listed"
        text = (
            f"Company record — {data.get('number', '?')}: {data.get('name', '?')}. "
            f"Incorporated {data.get('incorporated', '?')}. "
            f"Status {data.get('status', '?')}. Officers: {officers}."
        )
    else:
        text = (
            f"Domain record — {data.get('domain', '?')}. "
            f"Registered {data.get('registered', '?')}. "
            f"Registrar {data.get('registrar', '?')}. "
            f"Registrant {data.get('registrant', '?')}. "
            f"Nameservers: {', '.join(str(n) for n in data.get('nameservers') or []) or 'none listed'}."
        )
    return RecordAnswer(text, list(best.fact_keys))


def _fake_answer(world: Any, case_id: str | None, question: str) -> RecordAnswer:
    """A doctored service supplied by a scam case."""
    rows = world.session.scalars(
        select(RecordRow).where(RecordRow.service == "fake")
    ).all()
    if case_id:
        rows = [r for r in rows if r.case_id == case_id] or rows
    if not rows:
        return RecordAnswer(NO_MATCH, [])
    row = rows[0]
    return RecordAnswer(str(row.data.get("reply", NO_MATCH)), list(row.fact_keys))


def _best_match(rows: list[RecordRow], question: str) -> RecordRow | None:
    tokens = _tokens(question)
    if not tokens:
        return None
    scored: list[tuple[int, RecordRow]] = []
    for row in rows:
        haystack = " ".join(str(v) for v in _flatten(row.data)).lower()
        score = sum(1 for token in tokens if token in haystack)
        if score:
            scored.append((score, row))
    if not scored:
        return None
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored[0][1]


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9.@-]{2,}", text.lower())
    return {w for w in words if len(w) >= 3}


def _flatten(value: Any) -> list[str]:
    if isinstance(value, dict):
        out: list[str] = []
        for item in value.values():
            out.extend(_flatten(item))
        return out
    if isinstance(value, list):
        out = []
        for item in value:
            out.extend(_flatten(item))
        return out
    return [str(value)]
