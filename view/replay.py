"""Render a run's replay log as a readable HTML transcript.

There is nothing to watch: the run is a sequence of calls and messages, so the
viewer is a document. Ground truth can be included for authoring review, but is
off by default.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

CSS = """
body { font: 14px/1.5 -apple-system, Segoe UI, Roboto, sans-serif; margin: 0; background: #f6f4ef; color: #22201c; }
main { max-width: 880px; margin: 0 auto; padding: 32px 20px 80px; }
h1 { font-size: 22px; margin: 0 0 4px; }
.meta { color: #6b665c; font-size: 12px; margin-bottom: 28px; }
.session { margin: 32px 0 12px; font-size: 13px; letter-spacing: .08em; text-transform: uppercase; color: #8a3b2e; border-bottom: 1px solid #ddd6c8; padding-bottom: 6px; }
.call { margin: 6px 0; padding: 8px 10px; background: #fff; border: 1px solid #e6e0d4; border-radius: 6px; }
.call.fail { border-color: #c86a5a; background: #fdf3f1; }
.tool { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; color: #2f4d6e; }
.args { color: #6b665c; font-size: 12px; word-break: break-word; }
.result { margin-top: 4px; font-size: 12px; color: #444; white-space: pre-wrap; max-height: 180px; overflow: auto; }
.msg { margin: 8px 0; padding: 8px 12px; border-radius: 10px; max-width: 78%; }
.msg.actor { background: #fff; border: 1px solid #e6e0d4; }
.msg.agent { background: #e8eef7; margin-left: auto; }
.who { font-size: 11px; color: #6b665c; margin-bottom: 2px; }
.text { white-space: pre-wrap; }
"""


def render_html(replay_path: Path, *, reveal: bool = False) -> str:
    lines: list[str] = []
    title = replay_path.parent.name
    header: dict[str, Any] = {}
    session = 0

    for line in replay_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        kind = record.get("type")

        if kind == "header":
            header = record
            title = record.get("run_id", title)
            lines.append(f"<h1>{html.escape(str(title))}</h1>")
            meta = (
                f"feed {record.get('feed', '?')} · seed {record.get('seed', '?')} · "
                f"agent {record.get('agent', '?')} · actor {record.get('actor', '?')}"
            )
            lines.append(f"<div class='meta'>{html.escape(meta)}</div>")
            if reveal:
                lines.append(
                    f"<div class='meta'>instances: {html.escape(', '.join(record.get('instances', [])))}</div>"
                )
        elif kind == "session_start":
            session = int(record["session"])
            lines.append(f"<div class='session'>Session {session}</div>")
            for event in record.get("events", []):
                lines.append(f"<div class='call'><span class='tool'>event</span> {html.escape(event)}</div>")
        elif kind == "model_output":
            text = (record.get("text") or "").strip()
            if text:
                lines.append(
                    "<div class='msg agent'><div class='who'>investigator</div>"
                    f"<div class='text'>{html.escape(text)}</div></div>"
                )
        elif kind == "call":
            tool = record.get("tool", "?")
            args = html.escape(json.dumps(record.get("arguments", {}), ensure_ascii=False))
            ok = record.get("ok", True)
            cls = "call" if ok else "call fail"
            result = html.escape(json.dumps(record.get("result"), ensure_ascii=False, default=str))
            if len(result) > 1200:
                result = result[:1200] + "…"
            lines.append(
                f"<div class='{cls}'><span class='tool'>{html.escape(tool)}</span> "
                f"<span class='args'>{args}</span>"
                f"<div class='result'>{result}</div></div>"
            )
        elif kind == "session_end":
            lines.append(f"<div class='meta'>session ended: {html.escape(str(record.get('reason')))}</div>")

    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(str(title))}</title><style>{CSS}</style></head>"
        "<body><main>" + "\n".join(lines) + "</main></body></html>"
    )


def write_html(replay_path: Path, out_path: Path | None = None, *, reveal: bool = False) -> Path:
    out = out_path or replay_path.parent / "transcript.html"
    out.write_text(render_html(replay_path, reveal=reveal), encoding="utf-8")
    return out
