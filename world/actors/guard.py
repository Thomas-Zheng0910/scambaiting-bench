"""Post-turn checks on a counterpart reply.

Four hard checks and one diagnostic:

- entities: every handle, amount, domain, registration number and IBAN in the
  reply must exist somewhere in the case file;
- forbidden content: hard phrases that break character or admit the scam;
- policy limits: the case's own `guard.forbid` entries;
- length: the policy's sentence cap;
- obtainable timing: logged, never blocked (the actor decides disclosure).

A failed check causes one regeneration and then the authored fallback line.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

HANDLE = re.compile(r"@[A-Za-z0-9_.\-]{2,}")
MONEY = re.compile(r"£\s?\d[\d,]*(?:\.\d+)?")
PERCENT = re.compile(r"\b\d+(?:\.\d+)?\s?%")
DOMAIN = re.compile(r"\b[a-z0-9][a-z0-9\-]*(?:\.[a-z0-9\-]+)+\b")
REG = re.compile(r"\b(?:FSR|FRN)\s*#?\s*\d{3,}\b", re.IGNORECASE)
IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,}\b")

HARD_FORBIDDEN = [
    re.compile(r"\bi(?:'m| am) (?:an? )?(?:ai|bot|language model)\b", re.IGNORECASE),
    re.compile(r"\bthis is (?:a )?(?:scam|fraud)\b", re.IGNORECASE),
    re.compile(r"\bi(?:'m| am) (?:a )?scammer\b", re.IGNORECASE),
    re.compile(r"\bas an ai\b", re.IGNORECASE),
    re.compile(r"\[(?:system|instruction)", re.IGNORECASE),
]

_ENTITY_PATTERNS = (HANDLE, MONEY, PERCENT, DOMAIN, REG, IBAN)


def _norm(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


@dataclass(frozen=True)
class EntityTable:
    allowed: frozenset[str]

    @classmethod
    def from_case(cls, raw: dict[str, Any]) -> "EntityTable":
        text = json.dumps(raw, ensure_ascii=False)
        allowed = {_norm(m) for pattern in _ENTITY_PATTERNS for m in pattern.findall(text)}
        return cls(frozenset(allowed))

    def violations(self, text: str) -> list[str]:
        seen: list[str] = []
        for pattern in _ENTITY_PATTERNS:
            for match in pattern.findall(text):
                if _norm(match) not in self.allowed:
                    seen.append(match)
        return sorted(set(seen))


@dataclass
class GuardVerdict:
    ok: bool
    reason: str = ""
    violations: list[str] = field(default_factory=list)


def check(
    reply: str,
    *,
    entities: EntityTable,
    sentence_limit: int,
    forbid: Iterable[str] = (),
) -> GuardVerdict:
    bad = entities.violations(reply)
    if bad:
        return GuardVerdict(False, f"invented entities: {', '.join(bad)}", bad)

    for pattern in HARD_FORBIDDEN:
        if pattern.search(reply):
            return GuardVerdict(False, "forbidden content")

    lowered = reply.lower()
    for phrase in forbid:
        words = [w for w in re.findall(r"[a-z]{5,}", phrase.lower())]
        if words and all(w in lowered for w in words):
            return GuardVerdict(False, f"forbidden by policy: {phrase}")

    if sentence_limit > 0:
        from world.actors.policy import sentence_count

        if sentence_count(reply) > sentence_limit + 1:
            return GuardVerdict(False, "too long for this character's style")

    return GuardVerdict(True)


def obtainable_leaks(reply: str, obtainable: Iterable[dict[str, Any]]) -> list[str]:
    """Which obtainable entries the reply gives away, by distinctive token.

    Deliberately conservative: a leak needs a quoted name, a handle, an IBAN or
    a number of at least three digits from the entry's statement to appear.
    """
    lowered = reply.lower()
    hits: list[str] = []
    for item in obtainable:
        statement = str(item.get("statement", ""))
        tokens = set(HANDLE.findall(statement)) | set(IBAN.findall(statement))
        tokens |= {m for m in re.findall(r"\b\d{3,}\b", statement)}
        tokens |= set(re.findall(r"'([^']{4,})'", statement))
        if any(_norm(t) in _norm(reply) for t in tokens if len(t) >= 4):
            hits.append(str(item.get("key")))
        elif any(t.lower() in lowered for t in tokens if len(t) >= 4):
            hits.append(str(item.get("key")))
    return sorted(set(hits))
