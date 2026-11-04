"""Case file schema and cross-reference lint.

The loader validates every case with these models, then runs `lint_case`,
which checks the things pydantic cannot: that every reference resolves and that
the case is actually scoreable.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

FAMILIES = {"investment", "marketplace", "jobs"}
TRUTHS = {"scam", "legitimate"}
SURFACES = {"feed", "messenger"}
ROLES = {"mentor", "recruiter", "seller", "shill", "support", "adviser", "employer"}
SERVICES = {"register", "companies", "domains", "firm"}
REQUEST_KINDS = {f"R{i}" for i in range(1, 17)}
GENUINE_HANDLES = {"@register_enquiries", "@company_records", "@domain_records"}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- counterparts


class PersonaIn(Strict):
    name: str
    headline: str = ""
    avatar: str = ""
    bio: str = ""


class AccountIn(Strict):
    surface: Literal["feed", "messenger"]
    handle: str
    role_label: str = ""
    joined_label: str = ""

    @field_validator("handle")
    @classmethod
    def _no_spaces(cls, v: str) -> str:
        if not v or any(c.isspace() for c in v):
            raise ValueError("handle must be non-empty and contain no spaces")
        return v


class CoverAnswerIn(Strict):
    if_asked: str
    say: str
    only_if: str | None = None


class StrategyStageIn(Strict):
    goal: str = ""
    tactics: str = ""
    cover_answers: list[CoverAnswerIn] = Field(default_factory=list)
    contradicts: list[str] = Field(default_factory=list)


class StageNodeIn(Strict):
    on: dict[str, str] = Field(default_factory=dict)
    emits: list[str] = Field(default_factory=list)


class ReplyModeIn(Strict):
    in_session_after_calls: int = 0
    later: Literal["next_session", "same_session"] = "next_session"
    silence: Literal["none", "nudge_after_1_session"] = "none"


class GuardIn(Strict):
    forbid: list[str] = Field(default_factory=list)


class LLMIn(Strict):
    model: str = "actor_default"
    temperature: float = 0.7
    max_tokens: int = 220


class TemplateIn(Strict):
    id: str
    stage: str = ""
    fixed: str
    free: str = ""
    fact_keys: list[str] = Field(default_factory=list)


class ActivityIn(Strict):
    at: dict[str, Any] = Field(default_factory=dict)
    action: Literal["group_post", "dm", "react"] = "group_post"
    text: str = ""


class PolicyIn(Strict):
    truth_awareness: Literal["scam", "legit"]
    style: str = ""
    max_sentences: int = 3
    known_info: dict[str, list[str]] = Field(default_factory=dict)
    off_limits: list[str] = Field(default_factory=list)
    strategy: dict[str, StrategyStageIn] = Field(default_factory=dict)
    reply_mode: ReplyModeIn = Field(default_factory=ReplyModeIn)
    behaviour: dict[str, str] = Field(default_factory=dict)
    stage_machine: dict[str, StageNodeIn] = Field(default_factory=dict)
    request_kinds: dict[str, list[str]] = Field(default_factory=dict)
    payees: dict[str, str] = Field(default_factory=dict)
    guard: GuardIn = Field(default_factory=GuardIn)
    templates: list[TemplateIn] = Field(default_factory=list)
    activity_plan: list[ActivityIn] = Field(default_factory=list)
    llm: LLMIn = Field(default_factory=LLMIn)

    @field_validator("request_kinds")
    @classmethod
    def _known_request_kinds(cls, v: dict[str, list[str]]) -> dict[str, list[str]]:
        for stage, kinds in v.items():
            bad = set(kinds) - REQUEST_KINDS
            if bad:
                raise ValueError(f"stage {stage!r}: unknown request kinds {sorted(bad)}")
        return v


class CounterpartIn(Strict):
    id: str
    role: Literal["mentor", "recruiter", "seller", "shill", "support", "adviser", "employer"]
    persona: PersonaIn
    accounts: list[AccountIn]
    policy: PolicyIn

    @field_validator("accounts")
    @classmethod
    def _needs_messenger(cls, v: list[AccountIn]) -> list[AccountIn]:
        if not any(a.surface == "messenger" for a in v):
            raise ValueError("a counterpart needs at least one messenger account")
        return v


# ---------------------------------------------------------------- rooms, feed


class SeedMessageIn(Strict):
    from_: str = Field(alias="from")
    text: str
    deliver: dict[str, Any] = Field(default_factory=dict)
    attachments: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class RoomIn(Strict):
    id: str
    kind: Literal["dm", "group"] = "group"
    title: str = ""
    members: list[str] = Field(default_factory=list)
    invite_only: bool = False
    seed_messages: list[SeedMessageIn] = Field(default_factory=list)


class AttachmentIn(Strict):
    id: str
    kind: Literal["document", "photo"]
    filename: str = ""
    text: str = ""
    caption: str = ""
    fact_keys: list[str] = Field(default_factory=list)
    obtainable_keys: list[str] = Field(default_factory=list)
    visible_from_stage: str | None = None
    decisive: bool = False

    @field_validator("decisive")
    @classmethod
    def _photos_are_not_decisive(cls, v: bool, info: Any) -> bool:
        if info.data.get("kind") == "photo" and v:
            raise ValueError("a photo may not be decisive")
        return v


class RecordIn(Strict):
    service: Literal["register", "companies", "domains", "firm"]
    data: dict[str, Any]
    fact_keys: list[str] = Field(default_factory=list)


class FeedItemIn(Strict):
    """Feed items are open-shaped by kind, but the envelope is fixed."""

    model_config = ConfigDict(extra="allow")

    id: str
    kind: Literal[
        "friend_post",
        "news_link",
        "community_event",
        "sponsored_ad",
        "marketplace_listing",
        "group_post",
        "job_post",
        "page_suggestion",
        "comment",
    ]
    author: dict[str, Any] = Field(default_factory=dict)
    visible: dict[str, Any] = Field(default_factory=dict)
    age_label: str = ""
    # Only the lead item of a case is judged. Corroborating posts are unlabelled.
    judgeable: bool = True
    # Only set on judgeable non-case items (the suspicious-but-legitimate set).
    label: Literal["scam", "legitimate"] | None = None


# ---------------------------------------------------------------- scoring data


class FactIn(Strict):
    key: str
    kind: Literal["claim", "truth", "link"]
    statement: str
    carrier: dict[str, Any] | None = None
    carriers: list[dict[str, Any]] = Field(default_factory=list)
    available: dict[str, Any] = Field(default_factory=dict)
    weight: Literal["weak", "moderate", "strong"] = "moderate"
    requires: list[str] = Field(default_factory=list)


class ObjectiveIn(Strict):
    label: str = ""
    any: list[dict[str, Any]] = Field(default_factory=list)


class SufficientSetIn(Strict):
    id: str
    tier: Literal["decisive", "strong", "conversational"] = "decisive"
    facts: list[str]
    rationale: str = ""


class ObtainableIn(Strict):
    key: str
    statement: str
    in_strategy: str
    also_obtainable_from: list[str] = Field(default_factory=list)
    notes: str = ""


class FakeServiceIn(Strict):
    handle: str
    name: str
    reply: str
    fact_keys: list[str] = Field(default_factory=list)


class EventIn(Strict):
    id: str
    trigger: dict[str, Any] = Field(default_factory=dict)
    action: Literal["invite_room", "edit_message", "unlock_facts", "post_series", "message"]
    payload: dict[str, Any] = Field(default_factory=dict)


class DifficultyIn(Strict):
    regulator_warning: Literal["absent", "listed", "listed_with_caveat"] = "absent"
    public_reports: Literal["none", "weak", "clear"] = "weak"
    shill_clustering: Literal["discoverable", "hidden"] = "discoverable"


class SafetyIn(Strict):
    protected_tokens: list[str] = Field(default_factory=list)
    harmful_outcomes: list[dict[str, Any]] = Field(default_factory=list)
    permitted: list[str] = Field(default_factory=list)


class CaseIn(Strict):
    case_id: str
    family: Literal["investment", "marketplace", "jobs"]
    truth: Literal["scam", "legitimate"]
    version: str = "1.0.0"
    summary: str = ""

    counterparts: list[CounterpartIn] = Field(default_factory=list)
    rooms: list[RoomIn] = Field(default_factory=list)
    feed_items: list[FeedItemIn] = Field(default_factory=list)
    attachments: list[AttachmentIn] = Field(default_factory=list)
    records: list[RecordIn] = Field(default_factory=list)
    facts: list[FactIn] = Field(default_factory=list)
    objectives: dict[str, ObjectiveIn] = Field(default_factory=dict)
    sufficient_evidence_sets: list[SufficientSetIn] = Field(default_factory=list)
    obtainable: list[ObtainableIn] = Field(default_factory=list)
    events: list[EventIn] = Field(default_factory=list)
    fake_services: list[FakeServiceIn] = Field(default_factory=list)
    difficulty: DifficultyIn = Field(default_factory=DifficultyIn)
    safety: SafetyIn = Field(default_factory=SafetyIn)


class FeedFileIn(Strict):
    feed_id: str
    seed: int = 1
    instances: list[str]
    order_constraints: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------- lint


class LintError(ValueError):
    def __init__(self, case_id: str, problems: list[str]) -> None:
        self.case_id = case_id
        self.problems = problems
        super().__init__(f"{case_id}: " + "; ".join(problems))


def lint_case(case: CaseIn) -> list[str]:
    """Return every cross-reference problem in a case. Empty means valid."""
    problems: list[str] = []
    cp_ids = {c.id for c in case.counterparts}
    feed_ids = {f.id for f in case.feed_items}
    att_ids = {a.id for a in case.attachments}
    fact_keys = {f.key for f in case.facts}
    room_ids = {r.id for r in case.rooms}
    handles = {a.handle for c in case.counterparts for a in c.accounts}
    services = {r.service for r in case.records}
    stages = {
        stage
        for c in case.counterparts
        for stage in c.policy.stage_machine
    }

    is_filler = case.case_id == "filler"
    if not case.feed_items:
        problems.append("no feed items")
    if not case.facts and not is_filler:
        problems.append("no facts")

    # facts: one carrier, reachable
    for fact in case.facts:
        if not fact.carrier and not fact.carriers:
            problems.append(f"fact {fact.key} has no carrier")
        for carrier in ([fact.carrier] if fact.carrier else []) + list(fact.carriers):
            problems.extend(_carrier_problem(carrier, feed_ids, att_ids, cp_ids, services))
        for req in fact.requires:
            if req not in fact_keys:
                problems.append(f"fact {fact.key} requires unknown fact {req}")

    # known_info: keys exist, stages exist, facts attached to a topic not a truth
    truth_keys = {f.key for f in case.facts if f.kind == "truth"}
    for cp in case.counterparts:
        for stage, keys in cp.policy.known_info.items():
            if stage not in stages and cp.policy.stage_machine:
                problems.append(f"{cp.id}: known_info stage {stage!r} is not in the stage machine")
            for key in keys:
                if key not in fact_keys:
                    problems.append(f"{cp.id}: known_info references unknown fact {key}")
                if key in truth_keys and cp.policy.truth_awareness == "scam":
                    problems.append(
                        f"{cp.id}: a scam counterpart's known_info must not contain truth fact {key}"
                    )

    # strategy: stages exist
    for cp in case.counterparts:
        for stage in cp.policy.strategy:
            if cp.policy.stage_machine and stage not in stages:
                problems.append(f"{cp.id}: strategy stage {stage!r} is not in the stage machine")
        for answer in (a for s in cp.policy.strategy.values() for a in s.cover_answers):
            for handle in _handles_in_text(answer.say):
                if handle not in handles:
                    problems.append(f"{cp.id}: cover answer names unknown handle {handle}")

    # objective and sufficient-set keys
    for name, objective in case.objectives.items():
        for route in objective.any:
            for key in route.get("observed", []):
                if key not in fact_keys:
                    problems.append(f"objective {name}: unknown fact {key}")
    for s in case.sufficient_evidence_sets:
        for key in s.facts:
            if key not in fact_keys:
                problems.append(f"sufficient set {s.id}: unknown fact {key}")

    # obtainable
    seen: set[str] = set()
    for item in case.obtainable:
        if item.key in seen:
            problems.append(f"duplicate obtainable key {item.key}")
        seen.add(item.key)
        if not item.in_strategy.strip():
            problems.append(f"obtainable {item.key} has no strategy line")
        for ref in item.also_obtainable_from:
            if ref not in att_ids and ref not in feed_ids:
                problems.append(f"obtainable {item.key}: unknown alternative source {ref}")
            elif ref in att_ids:
                att = next(a for a in case.attachments if a.id == ref)
                if item.key not in att.obtainable_keys:
                    problems.append(
                        f"obtainable {item.key}: attachment {ref} does not list it in obtainable_keys"
                    )

    # templates
    for cp in case.counterparts:
        for template in cp.policy.templates:
            for key in template.fact_keys:
                if key not in fact_keys:
                    problems.append(f"{cp.id}: template {template.id} names unknown fact {key}")

    # attachments
    for att in case.attachments:
        for key in att.fact_keys:
            if key not in fact_keys:
                problems.append(f"attachment {att.id}: unknown fact {key}")
        if att.decisive and not (att.fact_keys or att.obtainable_keys):
            problems.append(f"attachment {att.id} is decisive but carries no fact or obtainable key")
        for key in att.obtainable_keys:
            if key not in {o.key for o in case.obtainable}:
                problems.append(f"attachment {att.id}: unknown obtainable key {key}")
        if att.visible_from_stage and stages and att.visible_from_stage not in stages:
            problems.append(f"attachment {att.id}: unknown stage {att.visible_from_stage}")

    # fake services
    for svc in case.fake_services:
        if svc.handle in GENUINE_HANDLES:
            problems.append(f"fake service may not shadow the genuine {svc.handle}")
        for key in svc.fact_keys:
            if key not in fact_keys:
                problems.append(f"fake service {svc.handle}: unknown fact {key}")

    # rooms and seed messages
    for room in case.rooms:
        for member in room.members:
            if member not in handles and member != "@jordan.lee":
                problems.append(f"room {room.id}: unknown member {member}")
        for msg in room.seed_messages:
            if msg.from_ not in handles and msg.from_ != "@jordan.lee":
                problems.append(f"room {room.id}: seed message from unknown {msg.from_}")
            for att in msg.attachments:
                if att not in att_ids:
                    problems.append(f"room {room.id}: seed message references unknown attachment {att}")
    for event in case.events:
        target = event.payload.get("room")
        if event.action == "invite_room" and target and target not in room_ids:
            problems.append(f"event {event.id}: unknown room {target}")

    # records
    for record in case.records:
        for key in record.fact_keys:
            if key not in fact_keys:
                problems.append(f"record {record.service}: unknown fact {key}")

    # accounts
    for cp in case.counterparts:
        if cp.role == "shill" and not cp.policy.activity_plan:
            problems.append(f"{cp.id}: a shill needs an activity_plan")

    return problems


def _carrier_problem(
    carrier: dict[str, Any],
    feed_ids: set[str],
    att_ids: set[str],
    cp_ids: set[str],
    services: set[str],
) -> list[str]:
    kind = carrier.get("type")
    ref = str(carrier.get("ref", ""))
    if kind == "post" and ref not in feed_ids:
        return [f"carrier references unknown post {ref}"]
    if kind == "attachment" and ref not in att_ids:
        return [f"carrier references unknown attachment {ref}"]
    if kind == "record":
        service = ref.split(":", 1)[0]
        if service not in services:
            return [f"carrier references unknown record service {service}"]
    if kind == "message":
        owner = ref.split(":", 1)[0]
        if owner not in cp_ids:
            return [f"carrier references unknown counterpart {owner}"]
    if kind not in {"post", "attachment", "record", "message"}:
        return [f"unknown carrier type {kind!r}"]
    return []


def _handles_in_text(text: str) -> set[str]:
    return {token.strip(".,;:()") for token in text.split() if token.startswith("@")}


def lint_case_json(raw: dict[str, Any]) -> CaseIn:
    case = CaseIn.model_validate(raw)
    problems = lint_case(case)
    if problems:
        raise LintError(case.case_id, problems)
    return case
