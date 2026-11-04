# Counterpart harness: final design

Status: **finalised** for the 3-week pilot, 2026-11-04. Supersedes §1.3 of `docs/harnesses.md`. Scope decisions, the identities we need, and the build.

---

## 1. Scope: three families, six instances

| Family | Why it is in |
|---|---|
| **Investment** | Most common social-media scam pattern in the English sources we can cite (clone firms, signal groups, pig-butchering). |
| **Marketplace** | Highest volume in real feeds; the escrow/lookalike archetype is reused by two other families later. |
| **Jobs / freelance** | Task and pay-to-unlock scams; also the cleanest legitimate twin (the role either exists on the careers page or it doesn't). |

Deliberately out of the pilot, recorded for the main experiment: property/rental, travel, tickets (all reuse the escrow or booking archetype), courier and telecom as *mid-case* surfaces rather than feed leads, government, tech support, charity, romance.

**Feed-native rule (decided):** a case may only start in the feed if a stranger could plausibly publish it as an offer. Alerts that arrive unbidden to a specific person (bank, courier, telecom, tax) are never feed entries; they may only appear later as an in-case message.

---

## 2. The identities

Each instance binds **its own distinct identity** (§1 of the case spec). No persona appears in both truth conditions of a family. Presentation parity is an authoring check, not a shared face.

### Investment (`inv01`)

| | Scam instance | Legitimate instance |
|---|---|---|
| **Account** | `@apex_emma` — "Emma Carter \| Client Success" | `@daniel_okafor` — "Daniel Okafor, CFA \| Client Adviser" |
| **Feed account** | `apex.capital.markets` (page) | `apex.capital.official` (page) |
| **Secondary accounts** | `vip_admin`, `shill_1`, `shill_2` (group shills); `apex_support` (in-platform support) | `apex_events` (webinar host) |
| **Identity truth** | Fictional platform **Apex Capital Markets Ltd** borrowing the registration number, name and address of a real-shaped authorised firm **Apex Capital Ltd** | Actual adviser at the real-shaped authorised firm |
| **Shills' relationship** | Same operator as the mentor (discoverable: accounts created in the same week) | Not applicable |
| **Reference contacts** | `@fsr_verify_desk` — *fake* register desk, supplied by the mentor | `@register_enquiries`, `@domain_records`, `@company_records` |
| **Requests made** | R1 pay-to-join, R2 deposit-to-trade, R3 release fee, R12 join group | R1 paid membership via checkout, R12 join webinar |

### Marketplace (`mkt01`)

| | Scam instance | Legitimate instance |
|---|---|---|
| **Account** | `daniel_k` — "Daniel K." | `rachel_m` — "Rachel M." |
| **Feed account** | `daniel.k.trades` | `rachel.m.photos` |
| **Secondary accounts** | `safeship_support` — fake escrow "support" | `safeship_official` — the real courier's support (legit policy) |
| **Identity truth** | Listing photos copied from a shop page; escrow page on a lookalike domain | Private seller; pay on collection or platform checkout |
| **Reference contacts** | `@safeship_verify` (fake) | `@domain_records`, `@company_records` |
| **Requests made** | R5 pay-for-item by bank transfer, R11 move to messenger | R5 pay on collection / platform checkout, R11 move to messenger to arrange pickup |

*Reverse-image search is deferred, so this case carries an alternative seller-history route to a sufficient set (account age, listing history, a second listing using the same photo set under a different name).*

### Jobs / freelance (`job01`)

| | Scam instance | Legitimate instance |
|---|---|---|
| **Account** | `brightpath_hr` — "Megan Ross \| Brightpath Talent" | `northwind_hr` — "Priya Nair \| Northwind Retail" |
| **Feed account** | `brightpath.talent` (page) | `northwind.careers` (page) |
| **Secondary accounts** | `taskdesk_support` — task platform support; `brightpath_manager` — "team lead" | `northwind_interview` — scheduling |
| **Identity truth** | Recruiter claims a real-shaped agency that never lists this role; tasks require a top-up | Real employer; role listed on the careers page; no fees |
| **Reference contacts** | `@brightpath_verify` (fake) | `@company_records`, `@register_enquiries` |
| **Requests made** | R4 top-up to unlock commission, R8 identity documents in chat, R6 install task app | R7 interview call, R8 documents through the official portal |

### Shared across all instances

| Role | Contact | Notes |
|---|---|---|
| Investigator | `@jordan.lee` | cover identity; not a counterpart |
| Register Enquiries | `@register_enquiries` | record service; firm/individual records, official contact channels |
| Company Records Desk | `@company_records` | record service; incorporation, officers, filings |
| Domain Records | `@domain_records` | record service; registration date, registrar, nameservers |

**Symmetry rule:** a scam instance and its legitimate twin use the same persona *shape*, the same tool set, the same request types where possible, and the same contact routes. They differ only in facts, policy, and which reference contact is trustworthy.

---

## 3. Final harness design

### 3.1 Principle

> **One counterpart class. One tool set. Two policies.**
>
> The legitimate counterpart and the scammer are the same code path with the same tools. No tool exists that only a scammer can call. They differ only in what they know, how their strategy is written, which requests they make, when, and how they respond to refusal.

### 3.2 Structure

Runs **inside the world server process**, not as a separate service. There is no appservice, no Matrix client and no delivery daemon: the engine is called when `message_send` arrives or when the delivery scheduler fires at a session boundary.

```
world/actors/
├── handle.py    # message_send → which counterpart handles it; per-room batching
├── intent.py    # message → closed label set (cheap model, temp 0)
├── policy.py    # stage machine, per-stage tool registration, request enums
├── facts.py     # known_info blocks per stage, obtainable list, entity whitelist
├── prompts.py   # known_info + strategy assembly
├── tools.py     # the 10 typed tool methods
├── schema.py    # inspect signatures + docstrings → JSON schemas (shared with harness)
├── respond.py   # model call + tool loop
├── guard.py     # post-turn checks, fallback line
└── (delivery: world/sessions.py; record services: world/records.py)
```

### 3.3 The tool set

Typed function calling, schemas generated from signatures and docstrings — the same builder used for the investigator's harness tools.

| Tool | Arguments | Registered when |
|---|---|---|
| `send_link` | `url_id: enum(declared for this stage)` | stages after the platform/listing exists |
| `send_artifact` | `artifact_id: enum(authored artifacts for this stage)` | stages where authored evidence is due |
| `send_photo` | `subject: enum`, `detail: str` | stages where improvised proof is plausible |
| `send_document` | `doc_type: enum`, `subject: str`, `details: str` | same |
| `request` | `kind: enum(R1…R16)`, `amount?`, `payee_id?`, `channel?` | request stages only |
| `invite_to_room` | `room_id: enum` | group-invitation stages |
| `move_to_messenger` | `handle: enum` | when the policy allows channel change |
| `edit_last_message` | `new_text: str` | one permitted "cover-up" stage |
| `go_silent` | — | any stage |
| `leave_room` | — | terminal stages |

Every call returns `ToolResult(success, content, error)`. Invalid arguments return a readable error to the model; the turn is not silently dropped.

**Stage-scoped registration is what bounds the model's *actions*.** In `intro` only `send_link` and `go_silent` exist; the fee stage adds `send_artifact` and `edit_last_message`. Argument enums are generated per stage, so `send_artifact` at `fee` lists `fee_schedule_pdf` and `payee_details_txt` and nothing else.

**Words are bounded differently.** There is no `reveal_fact`: what the actor may *say* is controlled by what its prompt tells it it knows (§3.3.1), not by a tool enum. The tools carry the things that must exist in the world — a file, a room, an account, an amount — and those stay enumerated because a wrong choice points at nothing.

### 3.3.1 What the actor knows, and what it is trying to do

Two prose blocks are assembled per stage and replace every fact ID the model used to see.

```markdown
## What you know

The account minimum is £250, paid by transfer or card.
We trade as Apex Capital Markets and we're authorised under FSR 551203.
Clients in the signals programme have been seeing 8–12% a month.
Withdrawals normally clear within 24 hours.

## Your strategy for this stage

Goal: get them to open an account today.
Tactics: answer what was asked, then make one next step easy. Short messages.
Prepared cover answers — use if asked, never volunteer:
- "Which firm are you registered as?" → "We're the UK arm of Apex Capital
  Group; the register lists us under the group name."
- "Your domain is new." → "We rebranded off the old domain last month."
- "Where does the money go?" → a client-funds account at our processor.
Off limits: who owns the platform, when it launched, why the name differs from
the register. Deflect to the register or the programme.
```

**Assembly rules.**

| Rule | Why |
|---|---|
| `known_info` **accumulates** across stages; facts are appended, never swapped | the character's memory stays intact, and a fact cannot appear before the stage that can back it with a link or an artifact |
| `strategy` is **replaced** per stage | the goal and tactics are stage-specific; keeping old tactics invites drift |
| Cover answers are **authored lies**, written at authoring time | a consistent story that the record services can contradict; improvisation would vary per run |
| Off-limits entries name **topics, not truths** | the model cannot leak a fact it does not possess |
| No fact IDs, no `{{revealable}}` list, no `{{never_reveal}}` text | IDs are grading artefacts, not prompt content |

**Obtainable information.** Facts the case author wants obtainable by good scambaiting are marked in the case file, and their guidance appears in `strategy` rather than `known_info`:

> *"Where the money goes: if they ask directly and have shown they intend to deposit, say it's a client-funds account. Don't bring it up."*

So the actor holds the fact, decides when to use it, and words it itself — the behaviour you asked for. The fact's canonical `statement` lives in the case file for grading (§6.4 of the case spec) and never enters the prompt.

**What this gives up:** a fact can be said at the wrong moment. Nothing rejects it; it is logged (`actor_leak` in the turn record) and reported as a case-quality diagnostic. A high leak rate on a case means the strategy text is too permissive, not that the run failed.

### 3.4 The turn

```
investigator message(s)
  → router (channel, debounce)
  → intent.classify          [cheap model, temp 0, closed labels]
  → policy.step              [deterministic: stage', known_info, strategy, request enums, triggers]
  → prompt.assemble(stage')  [deterministic: known_info + strategy + rules + last N messages]
  → tools = policy.tools_for(stage')
  → inner loop (≤4): model(messages, tools, tool_choice="auto")
       tool calls → execute → append role:"tool" → continue
       text        → end the turn
     if 4 iterations pass with no text: one final call, tool_choice="none"
  → guard.check(reply, tool_calls, known_info)
       fail → 1 regeneration with the reason → authored template → silence
  → deliver.schedule(turn, trigger)     [in-session or next-session]
  → log.record(turn)         [stage, tools, reply, guard, actor_leak, model, seed]
```

The loop shape matches the investigator's per-session round: tools first, text ends the turn. The forced final completion exists because a tool-only turn would leave the counterpart silent and desynchronise the exchange.

### 3.5 The guard

| Check | What it catches | On fail |
|---|---|---|
| Entity whitelist | Any URL, handle, amount, number, address or registration number not in the instance table — including those inside an attachment's `detail` | reject |
| Forbidden content | A statement contradicting a fact the actor was never told (truth admission), verdict words, "I am an AI", invented guarantees | reject |
| Contradiction | A claim negating an earlier stated fact, unless the current strategy declares it (`contradicts: [withdrawal_terms]` is how "withdrawals are free" → "£480 fee" stays legitimate) | reject unless declared |
| Request discipline | `request` called with a kind not enabled at this stage, or a `payee_id` not in the instance | reject |
| Obtainable-fact timing | An `obtainable` fact stated in a message whose preceding investigator turn did not ask for it | **log only** (`actor_leak`) — a case-quality diagnostic, not a deduction |

The first four are hard rejects: regenerate once with the reason, then the authored fallback line, then silence. Rejections never reach the investigator and are logged as environment issues, never charged to them.

The fifth is not a reject. Whether to disclose is the actor's decision, per §3.3.1; the guard only records it. A volunteered fact is delivered normally and still counts for D3 if the investigator notices and files it — the score is for collecting useful information, not for extracting it. A high leak rate means the case is too easy and is rewritten at G1.

### 3.6 Media

**No generation.** Every artifact is authored at case-writing time and frozen. The model chooses *which* to send; it never composes one.

| Kind | How it exists | Checks before delivery |
|---|---|---|
| **Document** | A frozen file per `doc_type` in the case directory, with extracted text and annotated entity values. `send_document(doc_type, subject)` selects it | Text stored with the file is checked against the entity whitelist at load time, once — not per run |
| **Image** | A frozen stock set; `send_photo(subject, detail)` chooses one. `detail` may not introduce entities | `detail` is scanned for entities before sending; captions are authored and never carry a decisive fact |

**Why this is better than generating.** The agent reads attachments as text (`attachment_read`), so a generated image would reach it as a caption — the generation would buy nothing the authored caption does not. Documents that matter (a fee schedule stating £480, a licence certificate bearing FSR 551203) must be *byte-identical across runs* for D2 to match them, which authored files guarantee and generation does not.

**Practical benefit:** the entity-check risk at run time disappears, and the media backend, OCR pipeline and their cost with it. Roughly two engineer-days and one failure class removed.

**Authored versus fabricated:** artifacts that appear in a sufficient-evidence set are hand-made and annotated with the fact keys they carry. Fabricated ones (the ones a scammer shows off) are claims only and never decisive. The decisive tell stays a consistency fact — register mismatch, domain age, contradiction across sessions.

### 3.7 Delivery and sessions

No clock. `reply_mode` on the policy:

```yaml
reply_mode:
  first_exchange: {in_session_after_calls: 2}
  subsequent: next_session
  silence: nudge_after_1_session
```

A reply may be composed in session 2 and delivered at the start of session 3; the model writes to a message it received earlier. Delivery triggers are `after_event`, `after_stage`, `after_join`, `session: n`. Every delivery is a row written with `deliver_at_session` and a synthetic `ts` derived from `(session, sequence)`, so ordering is exact and replayable.

### 3.8 Determinism and replay

- Intent classification, stage transitions, tool availability, enums, and delivery triggers are deterministic given the same inputs.
- The only sampled step is the model call.
- Every turn is logged with: stage before/after, intent + confidence, tool calls and results, reply text, guard outcome, model, seed, latency.
- On replay, the model call is replaced by the recorded turn; no provider call is made (`REPLAY=1` refuses provider network).
- Generated media is replayed from stored files.

### 3.9 Testing

| Test | Assertion |
|---|---|
| Scripted conversations (8–12 per case) | Vague, precise, accusatory, silent, off-topic, probing-for-hidden-facts, 40-turn. Stage progression matches the authored machine; guard-fallback rate below threshold. |
| Truth-leak fuzz (200 questions per case) | Zero replies assert a truth fact. The actor is never given the truth, so any hit is a prompt-assembly bug. |
| Obtainable-leak rate (per case) | Each case produces fewer than one unsolicited `obtainable` disclosure per three conversations on the scripted probes; above that, the strategy text is rewritten. |
| Tool-availability test | For every stage, the registered tool set equals the authored set; a forbidden call returns `ToolResult.error`. |
| Prompt-assembly test | For every stage, `known_info` equals the facts of all stages up to and including it (no removal), and contains no fact ID, no future fact, and no `off_limits` text beyond the topic name. |
| Request discipline | No `request` kind appears before its enabling stage; no request in the legitimate twin differs in *type* from its scam twin. |
| Symmetry test | The scam and legitimate policies expose an identical tool set; only args and stage gating differ. |
| Symmetry of requests | For each family, the set of request kinds used by both instances overlaps in at least one element. |
| Attachment test | Every authored document's text and every photo caption contains no entity outside the instance whitelist (checked once at case load). |
| Replay determinism | Two replays of the same log produce byte-identical transcripts and identical media checksums. |

### 3.10 Build effort

| Piece | Days |
|---|---|
| handle, intent, policy | 1.5 |
| facts, prompts (known_info + strategy) | 1.5 |
| schema, tools, respond (tool loop), guard | 2 |
| documents (authored, frozen) + stock photo set | 0.5 |
| records | 0.5 |
| tests (the nine above) | 1.5 |

**~7 engineer-days.** Media generation was dropped: documents are authored and frozen per case, and photos come from a small stock set chosen by `subject`.

---

## 4. Settled decisions (2026-11-04)

1. **No fact IDs reach the model.** `reveal_fact` is removed; the tool set is 10. Facts arrive as prose in `known_info`, and the model words them itself. IDs survive only in the case file, for grading.
2. **`known_info` accumulates by stage; `strategy` is replaced by stage.** Cover answers are authored, not improvised.
3. **Disclosure timing is the actor's decision.** The guard does not enforce withholding; it records `actor_leak`. Volunteered facts still count for D3 if reported; the flag tells us when a case is too easy.
4. **Enum arguments for world objects only** — `url_id`, `artifact_id`, `room_id`, `handle`, `request.kind`, `payee_id`, `doc_type`, photo `subject`. Independent of fact disclosure, and still required because a wrong value points at something that doesn't exist.
5. **The legitimate twin uses the same mechanism**: its `known_info` carries the positive grounds for legitimacy (registration number, official domain, the no-returns policy) and its `strategy` carries the honest answers.
6. **One LLM judge**, from a model family distinct from both actor and investigator, temp 0, JSON out, verbatim quote required on every positive. D3's input is the investigator's **submission** plus the case's obtainable list — not the transcript.

## 5. Still open

1. **Enum enforcement per provider** — verify in week 1; if a provider drops `enum`, the tool method is the only enforcement point and every rejected call must be logged.
2. **Photo generation backend and cost** — one call per photo, estimated 20–40 per run. Fallback: a frozen stock set chosen by `subject`.
3. **`move_to_messenger` availability** — build the Friendbook platform inbox, or start every case in Element. Starting in Element is cheaper and loses the "moved off-platform" tell.
