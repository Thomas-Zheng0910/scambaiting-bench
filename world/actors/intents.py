"""Intent classification for investigator messages.

The default is a small keyword classifier so tests and replay are deterministic.
An LLM classifier can be plugged in for real runs; it must return one of the
closed labels, and anything unrecognised becomes `off_topic`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterable

DEFAULT_LABELS = [
    "ask_identity",
    "ask_returns",
    "ask_fees",
    "ask_withdrawal",
    "ask_payee",
    "ask_meeting",
    "express_interest",
    "agree_to_pay",
    "refuse",
    "accuse_scam",
    "share_personal_info",
    "small_talk",
    "off_topic",
]

# Ordered: the first match wins, so accusation and payment beat interest.
_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("accuse_scam", ("scam", "fraud", "fake", "police", "report you", "regulator", "stolen", "clone")),
    ("agree_to_pay", ("i'll pay", "i will pay", "send the fee", "how do i pay the fee", "ok, pay")),
    ("ask_payee", ("where do i send", "which account", "payee", "beneficiary", "sort code", "iban", "wallet address")),
    ("ask_withdrawal", ("withdraw", "cash out", "take my money out", "release my funds", "payout")),
    ("ask_fees", ("fee", "fees", "charge", "cost", "commission")),
    ("ask_returns", ("return", "returns", "yield", "profit", "how much", "10.4", "monthly income")),
    ("ask_identity", ("who are you", "which firm", "registered", "registration", "licence", "license", "regulated", "company number")),
    ("ask_meeting", ("meet", "meeting", "call", "zoom", "video", "in person")),
    ("express_interest", ("interested", "sign me up", "how do i join", "join the group", "i'm in", "count me in", "send me the link")),
    ("refuse", ("not interested", "no thanks", "leave me alone", "stop messaging")),
    ("share_personal_info", ("my name is", "my email", "my number", "i live in", "my address")),
]

_LLM_LABELS_PROMPT = """Classify the investigator's message into exactly one label.
Labels: {labels}
Reply with the label only."""


@dataclass(frozen=True)
class Intent:
    label: str
    confidence: float
    source: str  # keyword | llm | fallback

    def to_json(self) -> dict[str, object]:
        return {"label": self.label, "confidence": self.confidence, "source": self.source}


def classify(
    text: str,
    labels: Iterable[str] | None = None,
    llm: Callable[[str, list[str]], str | None] | None = None,
) -> Intent:
    """Map a message to a closed label set."""
    allowed = list(labels or DEFAULT_LABELS)
    clean = text.strip().lower()
    if not clean:
        return Intent("off_topic", 0.0, "fallback")

    for label, needles in _RULES:
        if label not in allowed:
            continue
        if any(needle in clean for needle in needles):
            return Intent(label, 0.8, "keyword")

    if llm is not None:
        try:
            answer = llm(_LLM_LABELS_PROMPT.format(labels=", ".join(allowed)), allowed)
        except Exception:  # noqa: BLE001 - classifier failure is not fatal
            answer = None
        if answer in allowed:
            return Intent(answer, 0.6, "llm")

    # Never invent a label that could advance a stage: small_talk and
    # off_topic are always allowed and no stage machine transitions on them.
    for safe in ("small_talk", "off_topic"):
        if safe in allowed:
            return Intent(safe, 0.3, "fallback")
    return Intent("unclassified", 0.0, "fallback")


def strip_mentions(text: str) -> str:
    return re.sub(r"@[A-Za-z0-9_.-]+", "", text)
