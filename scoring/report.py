"""Render a result dict as RESULTS.md.

One row per instance plus the run-level numbers. Generated from result.json
alone, so re-scoring never needs the database.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def write_results(out_dir: Path, result: dict[str, Any]) -> Path:
    scores = result["scores"]
    lines: list[str] = []
    lines.append(f"# Run {result['run_id']}")
    lines.append("")
    lines.append(f"- feed: `{result['feed']}` (seed {result['seed']})")
    lines.append(f"- agent: `{result['agent']}`, actor: `{result['actor']}`")
    lines.append(f"- models: {result.get('models', {})}")
    lines.append("")
    lines.append("## Headline")
    lines.append("")
    lines.append("| | D1 | D2 | D3 | D4 |")
    lines.append("|---|---|---|---|---|")

    def fmt(v: Any) -> str:
        return "n/a" if v is None else f"{v:.3f}" if isinstance(v, float) else str(v)

    lines.append(
        f"| value | {fmt(scores['D1'])} | {fmt(scores['D2'])} | {fmt(scores['D3'])} | {fmt(scores['D4'])} |"
    )
    lines.append("")
    confusion = scores["confusion"]
    lines.append(
        f"Confusion: TP {confusion['tp']} · FP {confusion['fp']} · FN {confusion['fn']} · TN {confusion['tn']}"
    )
    lines.append(f"Coverage: {scores['coverage']}")
    lines.append("")
    lines.append("## Items")
    lines.append("")
    lines.append("| item | case | truth | verdict | judged | evidence |")
    lines.append("|---|---|---|---|---|---|")
    for item in scores["items"]:
        evidence = "—" if item["evidence"] is None else f"{item['evidence']:.2f}"
        lines.append(
            f"| `{item['item_id']}` | {item['case_id'] or '—'} | {item['truth']} | "
            f"{item['verdict'] or '—'} | {'yes' if item['judged'] else 'no'} | {evidence} |"
        )
    lines.append("")
    lines.append("## Support measures")
    lines.append("")
    for key, value in (scores.get("support") or {}).items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    path = out_dir / "RESULTS.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
