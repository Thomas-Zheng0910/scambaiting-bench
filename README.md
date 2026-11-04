# scambaiting-bench

A benchmark for scam-investigation agents. The agent reads a social feed, contacts
counterparts through a messenger, checks claims against public records, keeps notes
across six sessions, and submits a case table. Scored on `(D1, D2, D3, D4)`:
detection, evidence, scambaiting, and selection cost.

Design documents live in `docs/`; the plan is `IMPLEMENTATION_PLAN.md`.

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# validate the case files
.venv/bin/python -m harness.run lint

# a deterministic run with a scripted investigator and scripted counterparts
.venv/bin/python -m harness.run run --run-id demo --agent scripted --actor scripted

# read the result, then render the transcript
cat runs/demo/RESULTS.md
.venv/bin/python -m harness.run replay demo
```

## Running with models

Set the actor endpoint and run the real investigator loop:

```bash
export ACTOR_BASE_URL=https://api.example.com/v1 ACTOR_API_KEY=... ACTOR_MODEL=...
export INVESTIGATOR_MODEL=...
.venv/bin/python -m harness.run run --agent llm --actor llm
```

Any OpenAI-format endpoint that supports tool calling works. The model must honour
JSON-schema `enum`; the tool methods enforce it again, so a provider that ignores it
degrades to a tool error rather than an invalid call.

## What exists

```
world/      the simulated world: schema, loader, service, actors, records
harness/    the investigator: session loop, 14 tools, notes, trace
scoring/    D1-D4, the judge, RESULTS.md
view/       transcript renderer
cases/      one JSON file per instance, plus filler and the pilot feed
```

Two surfaces: **feed** and **messenger**. Fourteen tools for the investigator
(nine world, five harness) and seven for a counterpart. There is no browser, no
website and no pixel interface anywhere in the system.

## A case

A case is one JSON file. `bench lint` validates it: every fact needs a reachable
carrier, every `known_info` key must exist, a scam counterpart may not be told a
truth fact, and every `obtainable` entry needs an in-prompt strategy line.

```bash
.venv/bin/python -m harness.run lint cases/inv01.scam.json
```

## Tests

```bash
.venv/bin/python -m pytest
```

The suite covers the tool schema builder, the world tools, stage progression and
the guard, record services (including the fake verifier), submission validation,
the scripted end-to-end episode, and case lint.
