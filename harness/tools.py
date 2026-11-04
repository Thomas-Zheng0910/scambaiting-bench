"""The investigator's five harness tools.

These are not world tools: they read and write the run record (notes, flags,
the submission) and never change the world. They share the schema builder with
everything else and count against a separate budget, so hiding in notes is not
free.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import select

from common.tooling import ToolResult, tool
from world.models import MessageRow, RoomRow, RunRow

INVESTIGATOR_HANDLE = "@jordan.lee"

NotesOp = Literal["upsert", "get", "list", "search"]
Verdict = Literal["scam", "legitimate", "unsure"]
EndReason = Literal["submitted", "out_of_ideas", "budget", "blocked"]
Assessment = Literal[
    "unresolved", "leaning_scam", "leaning_legit", "concluded_scam", "concluded_legit"
]

NOTES_FIELDS = {
    "source_location",
    "accounts",
    "claims",
    "observations",
    "hypotheses",
    "open_questions",
    "assessment",
    "pending",
    "next_action",
}


@dataclass
class HarnessTools:
    """Run-scoped memory and reporting. One instance per run."""

    run_id: str
    world: Any
    _ended: bool = False
    _end_reason: str | None = None

    # ---------------------------------------------------------------- helpers
    @property
    def run(self) -> RunRow:
        row = self.world.session.get(RunRow, self.run_id)
        if row is None:
            raise RuntimeError(f"run {self.run_id} missing")
        return row

    def _save(self) -> None:
        self.world.session.flush()

    # ------------------------------------------------------------------ tools
    @tool("Record a verdict on a feed item")
    def flag_item(
        self,
        item_id: str,
        verdict: Verdict,
        confidence: float = 0.5,
        evidence: list[str] | None = None,
    ) -> ToolResult:
        """Triage a feed card while reading.

        Args:
            item_id: the feed item this verdict is about.
            verdict: scam, legitimate, or unsure.
            confidence: 0 to 1.
            evidence: the observations the verdict rests on.
        """
        from world.models import FeedItemRow

        item = self.world.session.get(FeedItemRow, item_id)
        if item is None:
            return ToolResult.failure(f"unknown feed item {item_id}")
        if not 0.0 <= float(confidence) <= 1.0:
            return ToolResult.failure("confidence must be between 0 and 1")

        run = self.run
        flags = [f for f in (run.flags or []) if f.get("item_id") != item_id]
        flags.append(
            {
                "item_id": item_id,
                "verdict": verdict,
                "confidence": float(confidence),
                "evidence": evidence or [],
                "session": run.current_session,
            }
        )
        run.flags = flags
        self._save()
        return ToolResult.success({"recorded": item_id, "verdict": verdict})

    @tool("Read and write your case notes")
    def notes(
        self,
        op: NotesOp,
        case_key: str | None = None,
        fields: dict[str, Any] | None = None,
        query: str | None = None,
    ) -> ToolResult:
        """Maintain structured notes across sessions.

        Args:
            op: one of upsert, get, list, search.
            case_key: the case this note is about (for upsert, get).
            fields: for upsert, any of source_location, accounts, claims, observations, hypotheses, open_questions, assessment, pending, next_action.
            query: for search, a substring to look for.
        """
        run = self.run
        store: dict[str, Any] = dict(run.notes or {})

        if op == "list":
            index = [
                {
                    "case_key": key,
                    "assessment": value.get("assessment", "unresolved"),
                    "pending": value.get("pending", []),
                    "session": value.get("session"),
                }
                for key, value in sorted(store.items())
            ]
            return ToolResult.success({"cases": index})

        if op == "get":
            if not case_key:
                return ToolResult.failure("case_key is required for get")
            if case_key not in store:
                return ToolResult.failure(f"no note for {case_key}")
            return ToolResult.success(store[case_key])

        if op == "search":
            needle = (query or "").lower()
            if not needle:
                return ToolResult.failure("query is required for search")
            hits = []
            for key, value in store.items():
                if needle in json.dumps(value, ensure_ascii=False).lower():
                    hits.append({"case_key": key, "note": value})
            return ToolResult.success({"hits": hits})

        # upsert
        if not case_key:
            return ToolResult.failure("case_key is required for upsert")
        if not fields:
            return ToolResult.failure("fields are required for upsert")
        unknown = set(fields) - NOTES_FIELDS
        if unknown:
            return ToolResult.failure(f"unknown fields: {sorted(unknown)}")
        if "assessment" in fields and fields["assessment"] not in {
            "unresolved",
            "leaning_scam",
            "leaning_legit",
            "concluded_scam",
            "concluded_legit",
        }:
            return ToolResult.failure("invalid assessment value")

        current = dict(store.get(case_key, {}))
        history = list(current.pop("history", []))
        history.append({"session": run.current_session, "fields": fields})
        current.update(fields)
        current["session"] = run.current_session
        current["history"] = history
        store[case_key] = current
        run.notes = store
        self._save()
        return ToolResult.success({"case_key": case_key, "version": len(history)})

    @tool("Search your own past turns")
    def history_search(self, query: str) -> ToolResult:
        """Find something you did or saw in an earlier session.

        Args:
            query: words to look for in your own notes and messages.
        """
        needle = (query or "").strip().lower()
        if not needle:
            return ToolResult.failure("query is required")

        run = self.run
        hits: list[dict[str, Any]] = []
        for key, value in (run.notes or {}).items():
            if needle in json.dumps(value, ensure_ascii=False).lower():
                hits.append({"kind": "note", "case_key": key, "text": value})
        messages = self.world.session.scalars(
            select(MessageRow).where(MessageRow.sender == INVESTIGATOR_HANDLE)
        ).all()
        for msg in messages:
            if needle in msg.text.lower():
                hits.append({"kind": "message", "room_id": msg.room_id, "seq": msg.seq, "text": msg.text})
        rooms = self.world.session.scalars(select(RoomRow)).all()
        for room in rooms:
            if needle in (room.title or "").lower():
                hits.append({"kind": "room", "room_id": room.id, "title": room.title})
        return ToolResult.success({"hits": hits[:50]})

    @tool("End the current session")
    def end_session(self, reason: EndReason, plan: str = "") -> ToolResult:
        """Stop working for now. Replies arrive in a later session.

        Args:
            reason: why you are stopping.
            plan: what you intend to do next session.
        """
        self._ended = True
        self._end_reason = reason
        run = self.run
        run.notes = {
            **(run.notes or {}),
            "__session_plan__": {"session": run.current_session, "plan": plan, "reason": reason},
        }
        self._save()
        return ToolResult.success({"ended": True, "session": run.current_session})

    @tool("Submit your final case table")
    def submit_case_table(self, rows: list[dict[str, Any]]) -> ToolResult:
        """File the report. The last submission is the one scored.

        Args:
            rows: one object per judged item with lead, verdict, confidence, key_evidence (list of fact keys) and obtained (list of what/quote/source).
        """
        if not rows:
            return ToolResult.failure("the table is empty")
        problems: list[str] = []
        cleaned: list[dict[str, Any]] = []
        for i, row in enumerate(rows):
            lead = str(row.get("lead", "")).strip()
            verdict = row.get("verdict")
            if not lead:
                problems.append(f"row {i}: missing lead")
                continue
            if verdict not in {"scam", "legitimate", "unsure"}:
                problems.append(f"row {i}: invalid verdict {verdict!r}")
                continue
            obtained = []
            for entry in row.get("obtained") or []:
                quote = str(entry.get("quote", "")).strip()
                source = str(entry.get("source", ""))
                if quote and source and self._quote_exists(quote, source):
                    obtained.append({"what": entry.get("what", ""), "quote": quote, "source": source})
                elif quote:
                    problems.append(f"row {i}: quote not found at {source}")
            cleaned.append(
                {
                    "lead": lead,
                    "verdict": verdict,
                    "confidence": float(row.get("confidence", 0.5)),
                    "key_evidence": list(row.get("key_evidence") or []),
                    "obtained": obtained,
                    "notes": str(row.get("notes", "")),
                }
            )
        if not cleaned:
            return ToolResult.failure("no valid rows: " + "; ".join(problems[:3]))

        run = self.run
        run.submitted = {"rows": cleaned, "session": run.current_session, "problems": problems}
        self._save()
        return ToolResult.success(
            {"rows": len(cleaned), "rejected_quotes": [p for p in problems if "quote" in p]}
        )

    # --------------------------------------------------------------- helpers
    def _quote_exists(self, quote: str, source: str) -> bool:
        """A quote must appear in the message it claims to come from.

        `source` is "room_id:seq" (preferred) or just a room id.
        """
        room_id, _, seq = source.rpartition(":")
        if not room_id:
            room_id, seq = source, ""
        rows = self.world.session.scalars(
            select(MessageRow).where(MessageRow.room_id == room_id)
        ).all()
        if seq.isdigit():
            rows = [r for r in rows if r.seq == int(seq)]
        needle = _norm(quote)
        return any(needle in _norm(r.text) for r in rows)

    @property
    def ended(self) -> bool:
        return self._ended

    @property
    def end_reason(self) -> str | None:
        return self._end_reason


def _norm(text: str) -> str:
    import re

    return re.sub(r"\s+", " ", text).strip().lower()
