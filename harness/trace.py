"""Append-only record of a run.

One JSON object per line. Enough to re-drive the run and to re-score it; no
screenshots, no frames, no hashes, because there is nothing rendered.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class Trace:
    def __init__(self, path: Path, header: dict[str, Any]) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("w", encoding="utf-8")
        self.write({"type": "header", **header})

    def write(self, record: dict[str, Any]) -> None:
        self._fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        self._fh.flush()

    def session_start(self, session: int, events: list[str]) -> None:
        self.write({"type": "session_start", "session": session, "events": events})

    def tool(self, session: int, round_no: int, name: str, arguments: dict[str, Any], ok: bool, result: Any) -> None:
        self.write(
            {
                "type": "call",
                "session": session,
                "round": round_no,
                "tool": name,
                "arguments": arguments,
                "ok": ok,
                "result": result,
            }
        )

    def model(self, session: int, round_no: int, text: str, calls: list[dict[str, Any]]) -> None:
        self.write(
            {
                "type": "model_output",
                "session": session,
                "round": round_no,
                "text": text,
                "calls": calls,
            }
        )

    def session_end(self, session: int, reason: str) -> None:
        self.write({"type": "session_end", "session": session, "reason": reason})

    def close(self) -> None:
        self._fh.close()
