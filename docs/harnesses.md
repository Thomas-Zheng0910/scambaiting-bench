# Harnesses: the counterpart harness and the investigator harness

Two harnesses, deliberately built as separate services with no shared code path. One drives everything trying to deceive, mislead or legitimately answer. The other runs the system under test. Splitting them is not tidiness; it is what lets the same investigator run against every condition, and what prevents a model failure in one from being attributed to the other.

Companion to `IMPLEMENTATION_PLAN.md` §4.7–4.8 and §6.

---

## 0. Why two harnesses rather than one

| Concern | Counterpart harness | Investigator harness |
|---|---|---|
| Purpose | make the world behave plausibly | run the system under test |
| Trust in the model | adversarial or neutral; output is *content* | unknown; output is *behaviour under test* |
| Failure meaning | environment defect — the run should be flagged, possibly voided | that is the measurement |
| Can the agent see it? | only through the world tools | it *is* the agent |
| Reused across conditions | yes, identical for every model | no, this is the variable |

A single harness with two "roles" was SEA's structure and its weakness: scammer drift, grader corruption and agent failure all ended up in one log with no way to separate them. Two services with separate logs is the fix, and it costs nothing at build time because they communicate only through the world server.

---

# Part 1 — The counterpart harness

## 1.1 What it is responsible for

- Actors (scammers, shills, legitimate counterparts) and record services, all as world accounts reachable through `room_open`.
- Deciding *what* is said, *when* it is delivered, and *what* it discloses.
- Not deciding what the world contains. Facts, stages, entities and timings are authored data; the harness only selects from them.
- Emitting a frozen, replayable transcript.

That last point defines the whole design: **the model phrases, the harness decides.** Every content decision is made before the model is called, so a model change changes tone, never substance.

## 1.2 Components

```
world/actors/
├── handle.py         # message_send → which counterpart handles it; batching per room
├── intent.py         # investigator message → fixed intent labels (cheap model, temp 0)
├── policy.py         # stage machine: intent + state → stage, known_info additions, strategy
├── facts.py          # known_info blocks per stage, obtainable list, entity whitelist
├── guard.py          # entity/forbidden-content/contradiction checks with regeneration
├── prompts.py        # known_info + strategy assembly per stage
└── (delivery lives in world/sessions.py; records in world/records.py)
```

Every component is a pure function of `(world state, incoming message)` except `respond.py`, which calls a model. That boundary is where testability lives: the whole pipeline can be unit-tested with a stub responder.

## 1.3 The turn: speak + typed tool calls

The counterpart uses **real OpenAI-style function calling with generated JSON schemas**, the same mechanism the investigator's harness uses for its bookkeeping tools. There are no inline markers, no regex dispatch, and no hand-rolled argument parsing. One implementation (`tools_schema.build_tools(methods)`) serves both harnesses.

### 1.3.1 The tool set

Each tool is a plain Python method on the actor, decorated to be exposed. Schemas are built from type hints and docstrings exactly as in `llm_agent.build_openai_tools`.

```python
class ScammerActor(Counterpart):
    @counterpart_tool("Send a file we prepared for this client")
    def send_artifact(self, artifact_id: str) -> ToolResult: ...
    #   artifact_id: enum, restricted to ids declared for the current stage

    @counterpart_tool("Send a web page to the client")
    def send_link(self, url_id: str) -> ToolResult: ...
    #   url_id: enum, restricted to the case's declared links

    @counterpart_tool("Invite the client into a private group")
    def invite_to_room(self, room_id: str) -> ToolResult: ...

    @counterpart_tool("Edit a message you already sent")
    def edit_last_message(self, new_text: str) -> ToolResult: ...

    @counterpart_tool("Stop replying permanently")
    def go_silent(self) -> ToolResult: ...

    @counterpart_tool("Leave the room; the client sees that you left")
    def leave_room(self) -> ToolResult: ...
```

`ToolResult(success, content, error)` is the same dataclass the agent's apps use, so an invalid call returns a readable error the model can react to, rather than being silently dropped.

### 1.3.2 Stage-scoped registration

**The model only sees the tools valid in the current stage.** `policy.tools_for(stage)` returns the subset before the call:

| Stage | Registered tools |
|---|---|
| `intro` | `go_silent` |
| `invite_group` | `invite_to_room`, `send_link`, `go_silent` |
| `platform` | `send_link`, `send_artifact`, `go_silent` |
| `fee` | `send_artifact`, `request`, `edit_last_message`, `go_silent` |
| `deflect` | `edit_last_message`, `leave_room` |
| `ghost` | *(none — the actor is finished)* |

This is what replaces the stage machine's action authority without taking choice away from the model. The model decides *whether* to attach the fee schedule now or wait for the next message; it cannot decide to attach something the stage does not offer. Argument enums are generated per stage too, so `send_artifact` in `fee` lists `fee_schedule_pdf` and `payee_details_txt` and nothing else.

Why stage-scoped rather than globally available with a guard: a tool the model could call but must not is a guard failure waiting to happen, and every such failure is an environment issue that muddies attribution. Not offering it is cleaner than rejecting it.

### 1.3.3 The round

```
investigator message(s)  ──►  router (DM / group / record service, 3 s debounce)
                              │
                              ├─ intent.classify(texts) → {label, confidence}      [cheap model, temp 0]
                              ├─ policy.step(stage, intent, counters) → {stage', known_info, strategy, triggers}
                              └─ tools = policy.tools_for(stage')                    [deterministic]
                                   │
     ┌─────────────────────────────┴──────────────────────────────────────┐
     │ inner loop, max 4 iterations (one reply turn, not a session)        │
     │   r = model(messages, tools, tool_choice="auto")                    │
     │   if r.tool_calls:                                                  │
     │       for call in r.tool_calls: execute → append role:"tool"        │
     │       continue                          # let it use the result     │
     │   else:                                                             │
     │       reply = r.content; break          # text ends the turn        │
     └────────────────────────────────────────────────────────────────────┘
                                   │
                              guard.check(reply, tool_calls, known_info)
                                   │  fail → 1 regeneration with the reason → template → silence
                                   │
                              deliver.schedule(reply, trigger)             # in-session or next-session
                              log.record(turn)                             # stage, tools, reveals, guard, model, seed
```

The inner loop is the same shape as the investigator's per-session round: tools first, text ends the turn. If the model calls tools and never produces text within 4 iterations, the harness makes **one final completion with `tool_choice="none"`** to force an utterance — the forced-reply trick from SEA's `llm_agent`, which exists because a tool-only round leaves the counterpart with nothing to say next turn and desynchronises the exchange.

### 1.3.4 Why tool calls, not a structured `{say, do, reveal}` object

| | Structured object | Typed tool calls |
|---|---|---|
| Validation | hand-written | generated from signatures |
| Invalid arguments | own parser, own failure mode | `ToolResult.error` returned to the model |
| Error recovery | the model has to be told the shape failed | the model sees the error and can retry, like any tool-using system |
| Enumeration | prose in the prompt | JSON-schema `enum`, enforced by the provider |
| Reuse | a bespoke second format | same builder as the investigator's tools |
| Natural tool semantics | actions feel bolted on | "send the document, then tell them it's the schedule" is one turn |

Tools carry **actions on the world** — send this file, invite to this room, ask for this amount from this payee. They do not carry utterances. Saying what the case authored is not an action: it is what the prompt tells the actor it knows (§1.4.1), and the actor words it freely. An earlier version exposed `reveal_fact(fact_id)`, which made every disclosure a rigid, pre-worded transaction; it was removed because the actor then sounded templated and could not answer a question nobody had anticipated.

### 1.3.5 The guard, revised

Now that reveals arrive as tool calls, the checks split by what was claimed:

| Check | Input | On fail |
|---|---|---|
| **Entity whitelist** | all URLs, handles, amounts, addresses and numbers in the reply must be in the case entity table | reject |
| **Forbidden content** | no truth admission, no verdict words, no "I am an AI", no invented guarantees, nothing in `guard.forbid` | reject |
| **Contradiction** | a claim negating an earlier stated fact is allowed only if the current strategy declares `contradicts: [withdrawal_terms]` | reject unless declared |
| **Request discipline** | `request.kind` enabled at this stage, `payee_id` in the instance | reject |
| **Obtainable timing** | an `obtainable` fact stated when the prior investigator turn did not ask for it | log `actor_leak`, deliver |

The last row is the one that changed most. Withholding is now a property of the actor's judgement, not of the interface, so the guard records rather than blocks. That is deliberate: a guard that refuses to let the actor mention the payee would be `reveal_fact` again, wearing a different hat.

What is lost: the guarantee that a sensitive fact cannot be stated early. What is kept, and what carries the weight: the entity whitelist (an invented amount or a wrong registration number makes the case unscoreable), the truth never being in the prompt, and contradiction checking.

### 1.3.6 Determinism

- Tool schemas, enums and stage transitions are deterministic; only `model(...)` and its arguments are sampled.
- Every tool call is logged with name, arguments and `ToolResult`, so a replay re-executes the calls rather than re-sampling.
- On replay, `model(...)` is replaced by the recorded turn reader (text + tool calls); no provider call is made.

## 1.4 What the model is allowed to see

### 1.4.1 How authored facts reach the conversation

Facts reach the model as **prose in the prompt**, in a `known_info` block, in the character's own register. The model paraphrases freely; it does not reproduce authored sentences, and there is no splice.

```
## What you know
The account minimum is £250, paid by transfer or card.
We trade as Apex Capital Markets and we're authorised under FSR 551203.
Clients in the signals programme have been seeing 8–12% a month.
Withdrawals normally clear within 24 hours.
```

Three properties make this safe enough to replace the tool:

1. **Accumulation, not permission.** A fact is appended when its stage opens and stays. The fee sentence is not in the prompt during `intro`, so it cannot be said early — not because a checker stops it, but because the actor has not been told it.
2. **The truth is never present.** The scam prompt contains no statement of what is really true; `off_limits` names topics. A model cannot leak what it does not know, so truth leakage requires invention, which the forbidden-content check catches.
3. **Decisive values travel typed.** The amount and payee of a payment arrive through `request(amount=480, payee_id=client_trust)`, so D2 matches exact terms regardless of the prose around them. The prose is commentary; the typed call is the term.

**Consistency without verbatim text** is carried by `strategy.cover_answers`: authored answers to the questions a suspicious investigator will ask, so the lie is the same in every run. `templates` remain as default phrasing and as the guard's fallback when a reply is rejected twice.

**Leak accounting.** An `obtainable` fact is one the actor holds and is told to raise only if asked. When it raises one unprompted, the turn is delivered and flagged `actor_leak`. The flag is a case-quality diagnostic only: it never removes credit, because an investigator who hears a volunteered bank account and writes it down has done the job.

### 1.4.2 Prompt assembly

Prompt assembly is the only place facts and model meet, so it is worth stating exactly:

| In the prompt | Deliberately absent |
|---|---|
| Persona (name, role, style, ≤N sentences) | The truth label |
| `known_info`: accumulated prose facts | Fact ids, targets, sufficient sets, other instances' facts |
| `strategy`: goal, tactics, cover answers, off-limits **topics** | The truth it is concealing, as a statement |
| Current stage guidance | Other actors' stage machines |
| Last N messages of this room | The judge prompt or rubric |
| Behaviour rules (on accusation, refusal, off-topic) | Wall time, session number beyond a natural-phrasing hint |

The "never reveal" list is given as *topics to avoid*, not as text, so a model cannot leak a hidden fact by paraphrasing it.

No fact ID appears anywhere in the prompt. IDs exist in the case file for grading; the prompt carries prose only. The `off_limits` block names topics rather than the hidden truth, which is stricter than the previous design: the model cannot paraphrase a secret it was never told.

## 1.5 Record services

Same pipeline, minus the stage machine and with a stricter guard:

- Input: a question. It must map to a field lookup. If it doesn't, the answer is "I can only provide record details."
- Output: record values only. No adjectives, no advice.
- Guard: a post-generation scan for evaluative words; a hit triggers a structural rewrite ("field: value" lines).
- A **fake** record service uses the same schema with doctored values and a reassuring tone, and is a separate counterpart entry supplied by the scammer.

## 1.6 Determinism and replay

- Every model call is logged with prompt hash, model, params, seed and output.
- On replay, the engine is replaced by a recorded-output reader. **No model calls happen during a replay** — the process refuses provider network access when `REPLAY=1`.
- Delivery triggers, stage transitions and message rows replay from the log, so the transcript is byte-identical.

## 1.7 Testing the counterpart harness on its own

No investigator model:

1. **Scripted conversations.** 8–12 adversarial scripts per case (vague, precise, accusatory, silent, off-topic, probing for hidden facts, 40 turns). Assert: no forbidden entity appears, no truth admission, stage progression matches the authored machine, guard-fallback rate under a threshold.
2. **Truth-leak fuzz.** Ask 200 generated questions per case; assert zero replies assert a truth fact (the truth is not in the prompt, so any hit is a prompt-assembly bug). Separately measure the `obtainable` leak rate: unsolicited disclosures per 3 conversations, target < 1.
3. **Stage discipline.** For every stage, the registered tool set equals the authored set, and `known_info` contains every fact from that stage and earlier and no future fact.
4. **Determinism.** Same conversation twice with the same seed → identical stage sequence and identical `known_info` blocks (prompt assembly is deterministic; only the reply text is sampled).

These run in CI, cost almost nothing, and are the main defence against actor drift.

## 1.8 Effort

| Piece | Days |
|---|---|
| handle + intent + policy | 1.5 |
| facts + prompts (known_info / strategy assembly) | 1.5 |
| tools + guard (incl. fallback lines) | 1.5 |
| record services (incl. fake variant) | 0.5 |
| scripted-conversation tests | 1 |

**~6 engineer-days.**

---

# Part 2 — The investigator harness

## 2.1 What it is responsible for

- Running the system under test across six sessions with fixed budgets.
- Exposing exactly one action space: the 16 tools over the world (§2.5).
- Assembling context at round boundaries, including compaction and the notes index.
- Recording every call and result so the run can be replayed and scored.

It does **not** decide anything about the world, and it never inspects truth. It is a driver plus a recorder.

**No desktop.** The pilot has no browser, no Xvfb, no screenshot loop, no coordinates. CUA is a deferred adapter (§2.9), not a build dependency.

## 2.2 Components

```
harness/
├── run.py          # CLI, config, run.lock.json
├── session.py      # 6-session lifecycle and budget enforcement
├── context.py      # assembly, per-type truncation, compaction
├── tools.py        # the 16 tools, as typed methods
├── dispatch.py     # call → world server (HTTP) or local harness
├── notes.py        # structured notes store, versioned by session
├── agents/
│   ├── chat_tools.py  # primary adapter: any tool-calling chat model
│   ├── scripted.py    # G1 solver, identical tool surface
│   └── cua.py         # deferred; interface stub
├── trace.py        # append-only log → replay.jsonl.zst
└── prompts/ (mission.md, cover_identity.yaml)
```

`agents/` is the only place a model is called. Everything else is model-agnostic, which is what makes "same harness, different model" a real claim.

## 2.3 The loop

```python
for session in 1..6:
    world.start_session(session)               # deliver queued counterpart turns
    ctx = build_context(session)
    while rounds < 20 and world_calls < 80 and harness_calls < 40 and not ended:
        step = adapter.step(ctx, tools)        # text + N calls, any mix
        for call in step.calls:
            res = dispatch(call)
            trace.record(session, round, call, res)
            ctx = ctx.with_observation(call, res)
        rounds += 1
    world.end_session(reason)
submit_case_table(final)                       # forced in the last session if absent
```

Four invariants:

1. **A round is one assistant turn.** It may contain any number of calls. Rounds, not calls, are what limit reasoning; calls are separately capped so batching cannot be exploited without bound.
2. **A failed call still costs budget.** `{ok: false}` goes back to the model and increments the counter, so trial and error is priced.
3. **Text without calls ends the turn, not the session.** The agent can think aloud and continue.
4. **Nothing moves between sessions.** Deliveries land at `start_session`; the harness never polls for "new messages".

## 2.4 Context

| In | Out |
|---|---|
| Mission, cover identity, protected tokens | Case label, truth, target set, `obtainable` list |
| Session number (not "3 of 6") | Remaining sessions |
| Notes index: keys, assessment, one-line pending | Full note text beyond the retrieval budget |
| Last 6 tool results verbatim | Older results |
| Compacted summary of everything earlier | Raw history |
| Budgets remaining | Wall clock |

**Truncation is per type and deterministic:** `page_visit` text ≤4k chars with a trailing marker; `feed_list` complete (41 snippets); `messages_read` honours `last_n`; `profile_view` ≤10 recent posts. Stated in the tool descriptions so the model knows to re-read rather than assume.

**Compaction** every 20 rounds: a cheap model call summarises evicted observations into ≤600 tokens. Logged, not charged as a round — otherwise context management silently eats a quarter of the session. Target ≤40k tokens per round.

`end_session(reason, plan)` writes `plan` into the next brief. That, plus the notes index, is the entire cross-session memory; a memory ablation replaces them with nothing.

## 2.5 Tools

Eleven world tools and five harness tools; the full signatures are in `IMPLEMENTATION_PLAN.md` §6.3. Three properties matter here:

- **`flag_item` is free.** D4 counts actors contacted, not flags, so triage costs a call but never a selection penalty.
- **`notes` is one tool with an `op` enum**, not four tools plus a checkpoint. The assessment is a field on `upsert`, and versioning by session gives the revision history that a checkpoint tool would have duplicated.
- **`submit_case_table` is validated before any judge sees it.** Each `obtained[].quote` must appear at the named message by string match; a row whose lead matches nothing is rejected with an error.

The tools are plain Python methods with type hints and docstrings, converted by the same `build_tools()` builder the counterpart uses. One schema implementation, two harnesses.

## 2.6 Budgets

| Budget | Value | Enforced by |
|---|---|---|
| Sessions | 6 | `session.py` |
| Rounds per session | 20 | `session.py` |
| World calls per session | 80 | `session.py` |
| Harness calls per session | 40 | `session.py` |
| Wall clock per session | 45 min (logged when hit) | `run.py` |
| Tokens per run | configurable cap | adapter |

Hitting any budget ends the session, not the run, and the reason is recorded in `result.json`.

## 2.7 Recording

```
runs/<run_id>/result.json        scores, confusion matrix, case table, support measures, run.lock
runs/<run_id>/replay.jsonl.zst   every call and result, actor turns, events, model text
```

`result.json` is the only input to `RESULTS.md` and the analysis scripts. The replay log exists to re-drive the run and to re-score if a rubric bug is found.

Because the harness records both what the model claimed and what actually executed, ungrounded claims are a rule, not a judgement: a cited fact with no corresponding tool result is ungrounded by construction.

## 2.8 Determinism and replay

Determinism is structural. A tool call is a pure function of `(world state, arguments)`; the only sampled step in the whole system is the counterpart's LLM turn, and that is recorded verbatim.

`bench replay` restores the session snapshot, re-executes every call, and asserts exact equality of results. There is no frame hash, no drift threshold, and no settle delay — a mismatch is always a bug (unseeded sampling in the counterpart, or a non-deterministic query).

## 2.9 Adapters

| Adapter | Interface | Use |
|---|---|---|
| `chat_tools` | `step(ctx, tools) -> Step(actions=[], calls=[], text)` over any OpenAI-format endpoint | primary |
| `scripted` | same signature, deterministic policy | G1 solver |
| `cua` | would translate the same world into a rendered surface | deferred |

`run.lock.json` records two adapter capabilities that affect comparability: whether the model batches calls, and whether the provider enforces `enum` in argument schemas. A model that cannot batch is not disadvantaged on correctness but uses its 20 rounds differently, and that has to be visible.

## 2.10 Testing without a model

| Component | Test |
|---|---|
| World server | endpoint tests per case fixture; `form_submit` transitions; allowlist rejection |
| Context builder | golden strings per (session, round) |
| Truncation | boundary cases at 4k, `last_n`, 10-post cap |
| `submit_case_table` | 12 cases including a fabricated quote, wrong room, re-submission |
| Budgets | scripted adapter exhausting each counter; asserts the session ends and the reason is recorded |
| End to end | 6 scripted runs producing known `(D1, D2, D3, D4)` |

## 2.11 Effort

| Piece | Days |
|---|---|
| session, budgets, trace | 1.5 |
| context, truncation, compaction, notes | 1.5 |
| tools, dispatch, schema | 1 |
| `submit_case_table` validation | 0.5 |
| adapter + scripted solver | 1 |
| tests | 1 |
| replay + transcript | 0.5 |

**~7 engineer-days.**

## Part 3 — The boundary between them

| Interaction | Mechanism | Never |
|---|---|---|
| Investigator sends a message | `message_send` → world server → counterpart engine | direct function call |
| Counterpart replies | engine writes a message row with `deliver_at_session` | writing to harness state |
| Investigator reads a page | `page_visit` over the URL allowlist | fetching anything live |
| Counterpart changes the world | world-server write, attributed to an actor | page mutation by the investigator |
| Scoring | reads `result.json` and `replay.jsonl.zst` | asks either harness at run time |

The one shared dependency is the **world database**, and it is append-only from both sides with a `cause` column, so every state can be attributed to an actor, an event, or the investigator.

The URL allowlist is the boundary that replaces the network sandbox: `page_visit` resolves only against URLs declared by loaded cases, so no case content can cause an outbound fetch.

## Part 4 — Combined effort and sequencing

| Week 1 | Counterpart: policy, facts, prompts, tools. Investigator: loop, dispatch, context, notes |
| Week 2 | Counterpart: guard, record services, document templates. Investigator: submission validation, scoring inputs, replay, scripted solver |
| Week 3 | Both: fixes from the pilot; freeze; batch runs |

**~14 engineer-days total** for both harnesses, excluding the world server, page content and scoring.

## Part 5 — Risks

| Risk | Mitigation |
|---|---|
| Counterpart model drifts off persona | deterministic stage machine + entity guard + template fallback; drift is logged as an environment issue, not an agent failure |
| Intent classifier mislabels and skips a stage | label set is small and per-case; unknown → `off_topic`; scripted tests cover each label |
| Investigator adapter leaks hidden state via prompt | context-grep test in CI; adapters reach the world only through tools |
| Budget accounting differs per adapter (batched calls) | counters at the harness level: rounds, world calls, harness calls — all incremented per executed call, never per model turn |
| Replay calls a model by accident | provider network refused when `REPLAY=1`; any attempt raises |
| Two harnesses drift in their world view | single world DB, single write path, `cause` column |
