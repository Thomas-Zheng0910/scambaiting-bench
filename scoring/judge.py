"""Narrow judge tasks.

Four tasks, each mapping a short piece of text to an authored statement. The
default implementation is a deterministic overlap judge so that tests and
replays do not need a model; an LLM judge can be swapped in with the same
interface.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from common.text import content_tokens


class Judge(Protocol):
    def maps_to(self, claim: str, statement: str) -> bool:
        ...


@dataclass
class OverlapJudge:
    """Deterministic stand-in for an LLM judge.

    A claim matches a statement when they share enough content words, or when
    the claim contains a distinctive token from the statement (a quoted name, a
    handle, an identifier).
    """

    threshold: float = 0.45

    def maps_to(self, claim: str, statement: str) -> bool:
        a = content_tokens(claim)
        b = content_tokens(statement)
        if not a or not b:
            return False
        # A short quote should count when most of *its* words appear in the
        # statement; a long paraphrase should count when the two sets largely
        # coincide either way.
        if len(a & b) / len(a) >= 0.6:
            return True
        if len(a & b) / min(len(a), len(b)) >= self.threshold:
            return True
        distinctive = {
            t for t in b if len(t) >= 4 and (any(c.isdigit() for c in t) or t.startswith("@"))
        }
        return bool(distinctive & a)


@dataclass
class LLMJudge:
    """Ask a model whether a claim states a given statement.

    The prompt is deliberately tiny: one claim, one statement, yes or no. The
    judge never sees the conversation, the case label, or the other candidate
    statements, which is what keeps it auditable.
    """

    model: Any
    name: str = "llm"

    def maps_to(self, claim: str, statement: str) -> bool:
        prompt = [
            {
                "role": "system",
                "content": (
                    "You compare two texts. Answer YES if the CLAIM conveys the "
                    "same specific information as the STATEMENT, even in different "
                    "words. Answer NO if it is vaguer, different, or merely related. "
                    "Reply with YES or NO only."
                ),
            },
            {"role": "user", "content": f"CLAIM: {claim}\nSTATEMENT: {statement}"},
        ]
        turn = self.model.complete(prompt, [], tool_choice="none", temperature=0.0, max_tokens=4)
        return turn.text.strip().upper().startswith("YES")


def pick_judge(model: Any | None = None) -> Judge:
    return LLMJudge(model) if model is not None else OverlapJudge()
