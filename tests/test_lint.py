from __future__ import annotations

from pathlib import Path

import pytest

from world.schema import CaseIn, LintError, lint_case

CASES = Path(__file__).resolve().parent.parent / "cases"


def load(name: str) -> dict:
    return CaseIn.model_validate_json((CASES / name).read_text()).model_dump(mode="json")


def test_shipped_cases_are_clean():
    for name in ("inv01.scam.json", "inv01.legit.json", "filler.json"):
        case = CaseIn.model_validate_json((CASES / name).read_text())
        assert lint_case(case) == []


def test_missing_carrier_is_reported():
    raw = load("inv01.scam.json")
    raw["facts"][0]["carrier"] = None
    problems = lint_case(CaseIn.model_validate(raw))
    assert any("has no carrier" in p for p in problems)


def test_dangling_fact_reference_is_reported():
    raw = load("inv01.scam.json")
    raw["counterparts"][0]["policy"]["known_info"]["intro"].append("F99")
    problems = lint_case(CaseIn.model_validate(raw))
    assert any("unknown fact F99" in p for p in problems)


def test_truth_fact_in_a_scam_prompt_is_reported():
    raw = load("inv01.scam.json")
    # F3 is a truth fact; a scam counterpart must not be told it.
    raw["counterparts"][0]["policy"]["known_info"]["intro"].append("F3")
    problems = lint_case(CaseIn.model_validate(raw))
    assert any("must not contain truth fact F3" in p for p in problems)


def test_obtainable_needs_a_strategy_line():
    raw = load("inv01.scam.json")
    raw["obtainable"][0]["in_strategy"] = ""
    problems = lint_case(CaseIn.model_validate(raw))
    assert any("no strategy line" in p for p in problems)


def test_obtainable_alternative_source_must_agree():
    raw = load("inv01.scam.json")
    raw["obtainable"][0]["also_obtainable_from"] = ["at_fee_schedule"]
    problems = lint_case(CaseIn.model_validate(raw))
    assert any("does not list it in obtainable_keys" in p for p in problems)


def test_unknown_room_member_is_reported():
    raw = load("inv01.scam.json")
    raw["rooms"][0]["members"].append("@ghost")
    problems = lint_case(CaseIn.model_validate(raw))
    assert any("unknown member @ghost" in p for p in problems)


def test_photo_may_not_be_decisive():
    raw = load("inv01.scam.json")
    raw["attachments"][-1]["kind"] = "photo"
    raw["attachments"][-1]["decisive"] = True
    with pytest.raises(Exception):
        CaseIn.model_validate(raw)
