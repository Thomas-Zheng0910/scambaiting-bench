"""Small deterministic text utilities shared by the engine and the scorer."""

from __future__ import annotations

import re

STOP = {
    "the", "and", "for", "that", "with", "from", "this", "have", "has", "are",
    "was", "were", "will", "would", "there", "their", "they", "them", "than",
    "into", "about", "which", "when", "what", "where", "your", "you", "our",
    "its", "not", "but", "can", "could", "should", "any", "all", "each",
    "been", "being", "after", "before", "over", "under", "such", "only",
}


def content_tokens(text: str) -> set[str]:
    words = re.findall(r"[A-Za-z@][A-Za-z0-9_.@-]+|\b\d[\d,.]*\b", text.lower())
    return {w for w in words if w not in STOP and len(w) > 2}


def overlap(a: str, b: str) -> float:
    """Share of the shorter token set that appears in the longer one."""
    ta, tb = content_tokens(a), content_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def quotes(text: str) -> set[str]:
    return {q.strip() for q in re.findall(r"'([^']{4,})'", text)}


def identifiers(text: str) -> set[str]:
    """Handles, IBANs and numbers of at least three digits."""
    found = set(re.findall(r"@[A-Za-z0-9_.\-]{2,}", text))
    found |= set(re.findall(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,}\b", text))
    found |= set(re.findall(r"\b\d{3,}\b", text))
    return found
