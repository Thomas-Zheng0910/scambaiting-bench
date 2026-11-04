from __future__ import annotations

import json
from pathlib import Path

from harness.run import main
from harness.tools import HarnessTools
from world.models import RunRow


def test_scripted_episode_produces_a_scored_result(tmp_path: Path):
    out = tmp_path / "run"
    code = main(["run", "--run-id", "t1", "--out", str(out), "--agent", "scripted", "--actor", "scripted"])
    assert code == 0

    result = json.loads((out / "result.json").read_text())
    scores = result["scores"]

    assert scores["D1"] == 1.0
    assert scores["confusion"] == {"tp": 1, "fp": 0, "fn": 0, "tn": 3}
    assert scores["coverage"] == "4/4"
    assert scores["D2"] is not None and scores["D2"] > 0
    assert scores["D3"] >= 1
    assert scores["D4"] == 3.0
    assert (out / "RESULTS.md").exists()
    assert (out / "replay.jsonl").exists()


def test_replay_log_is_complete(tmp_path: Path):
    out = tmp_path / "run"
    main(["run", "--run-id", "t2", "--out", str(out), "--agent", "scripted", "--actor", "scripted"])
    lines = [json.loads(line) for line in (out / "replay.jsonl").read_text().splitlines()]
    kinds = [line["type"] for line in lines]
    assert kinds[0] == "header"
    assert kinds.count("session_start") == 6
    assert kinds.count("session_end") == 6
    assert "call" in kinds
    calls = [line for line in lines if line["type"] == "call"]
    assert any(c["tool"] == "submit_case_table" and c["ok"] for c in calls)


def test_submission_rejects_a_fabricated_quote(world):
    tools = HarnessTools(run_id=world.run_id, world=world)
    result = tools.submit_case_table(
        [
            {
                "lead": "fi_inv01_ad",
                "verdict": "scam",
                "confidence": 0.9,
                "key_evidence": [],
                "obtained": [
                    {
                        "what": "payee",
                        "quote": "Send everything to account 999",
                        "source": "inv01_scam:rm_vip_circle:1",
                    }
                ],
            }
        ]
    )
    assert result.ok
    run = world.session.get(RunRow, world.run_id)
    assert run.submitted["rows"][0]["obtained"] == []
    assert run.submitted["problems"]


def test_notes_are_versioned_across_sessions(world):
    tools = HarnessTools(run_id=world.run_id, world=world)
    tools.notes("upsert", "fi_inv01_ad", {"assessment": "leaning_scam"})
    world.start_session(2)
    tools.notes("upsert", "fi_inv01_ad", {"assessment": "concluded_scam"})
    note = tools.notes("get", "fi_inv01_ad").content
    assert note["assessment"] == "concluded_scam"
    assert len(note["history"]) == 2


def test_notes_reject_unknown_fields(world):
    tools = HarnessTools(run_id=world.run_id, world=world)
    result = tools.notes("upsert", "x", {"nonsense": True})
    assert not result.ok


def test_flag_requires_a_real_item(world):
    tools = HarnessTools(run_id=world.run_id, world=world)
    assert not tools.flag_item("nope", "scam").ok
    assert tools.flag_item("fi_inv01_ad", "scam", 0.8).ok
