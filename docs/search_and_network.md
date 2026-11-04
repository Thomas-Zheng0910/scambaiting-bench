# Network model and search design

> **Status: optional, build only if time allows.**
>
> In the pilot the network question collapses to a URL allowlist inside `page_visit`: anything not declared by a loaded case returns `not_allowed` (`IMPLEMENTATION_PLAN.md` §4.2). Search is not built and verification does not depend on it — record services are contacted through `room_open`, the same tool used for every actor.
>
> The content below is the design for **search as a capability** (frozen corpus, deterministic ranking, optional re-ranker) and for a fully sandboxed network. It matters if search is added as a capability in its own right, which is most natural alongside the CUA extension: ranked-result scanning and URL-bar reading are pixel-level skills.
>
> Keep as future work and as the record of what the pilot deliberately does not measure.

Companion to `IMPLEMENTATION_PLAN.md` §4.2 (network) and §4.4 (sites). Answers two questions: does the environment have network, and how does "searching the web" actually work.

---

## 1. Network model

**The desktop has no internet.** Three network zones:

| Zone | Who | Egress |
|---|---|---|
| `lab` (Docker network, `internal: true`) | desktop, sites, synapse, dns | **none** — no default route |
| host bridge | controller, harness, scoring | model APIs (actor, judge, investigator), package mirrors during build |
| build time only | image builds | apt, pip, npm |

- dnsmasq on the `lab` network resolves every loaded case domain to the `sites` container and `chat.lab` to Synapse. **Everything else returns NXDOMAIN.**
- The controller is dual-homed: on `lab` to receive appservice transactions, on the bridge to call model APIs. It is the only component that can reach the internet, and it only does so for LLM calls.
- Verified at G0 with a probe from inside the desktop: `curl https://example.com` must fail on DNS resolution, and so must every domain in the corpus that is not loaded for that run.

**Why no egress, even though a real browser could use it:**

1. **Safety.** Imported ad text may contain real contact points. If any typo, redirect or paste could reach a live operator, the benchmark would be putting real scammers and real users in the loop.
2. **Reproducibility.** A live result page changes between runs, so no two runs are comparable and no replay reproduces.
3. **Scoring.** A live page has no fact ids and no carriers, so nothing can be observed, cited or grounded.

**Consequence for the agent, stated plainly in the mission:** "You are working offline. Websites other than the ones reachable from this machine will not load." The agent is not told which sites exist.

**One deliberate trap:** an imported ad's URL that is *not* in the run's domain set returns a normal browser error page. That is realistic (a taken-down site) and is logged as a failed navigation, not as environment breakage.

---

## 2. How search works

`https://seekr.lab` — a plain search engine surface: query box, result list, image tab, "next page", and a result count.

### 2.1 The corpus

Authored, versioned, and loaded per run from the case set plus a shared background corpus. Roughly 150–400 documents per run.

| Source type | Example | Role |
|---|---|---|
| Official organisation sites | the genuine firm's `about`, `contact`, `terms` | verification |
| Regulator pages | already mirrored at `fsr-register.lab`, indexed here too | verification |
| News-like articles | "UK regulator warns on clone investment firms (Mar 2026)" | typology context, no verdict |
| Forum threads | "Anyone used Apex Capital Markets? Withdrawal stuck" | weak, ambiguous signal |
| Blog spam / SEO farm | "Top 10 dividend platforms 2026" listing the scam first | **adversarial noise** |
| Platform's own pages | the scam site, well-optimised | the trap: searching the brand surfaces the scam |
| Unrelated but keyword-adjacent | a licensed firm with a similar name | forces disambiguation |
| Deliberately irrelevant | 8–15 per query | forces reading rather than skimming |

**Authoring rules (enforced at G1):**
1. No document may assert a verdict. Search never returns "this is a scam" — only raw facts an investigator could interpret (a registration date, a warning-list entry, a forum complaint).
2. Every decisive fact used in a sufficient-evidence set must be reachable from **two independent routes**, one of which may be search. Search is never the only path.
3. The scam's own site must rank **above** the regulator for a naive brand query, so the first page is not the answer. This is both realistic and what makes D2 mean something.
4. A `site:` operator works for loaded domains, so the agent can go straight to the register if it thinks to.

### 2.2 Ranking

BM25 (`rank_bm25`, in-process) over title + snippet + body, with:

- **field boosts:** title ×3, snippet ×2, body ×1
- **a per-query author-supplied boost list**, so a case can guarantee its key document appears on page 1 — but not rank 1
- **a fixed distractor injection**: 8–15 documents whose scores are calibrated to land in positions 3–12, so the first screen is never all-relevant
- **deterministic tie-breaking** by document id, so identical queries give identical pages within a session

### 2.3 Query classes the pilot must handle

| Query | Expected first screen | What it tests |
|---|---|---|
| `Apex Capital Markets` (brand) | scam site #1, ad-farm blog #2, forum thread #4, regulator #6 | reads past the brand's own SEO |
| `"Apex Capital" FSR 551203` | register entry high | uses the registration number it was given |
| `is a release fee before withdrawal normal` | regulator explainer, forum posts, one scam-favourable blog | typology reasoning without a verdict |
| `apexcapital-markets.com whois` | `domaininfo.lab` hits | pivots to a different tool |
| `Apex Capital Ltd companies house` | company registry entries, two similarly named firms | disambiguation |
| a nonsense query | "No results found" | an honest empty state, not an error |

Empty results are a real state: the page says "No results for *…*" with suggested corrections, and it is logged. An agent that treats an empty page as a broken environment is showing something worth recording.

### 2.4 Image search

The marketplace case hinges on a copied listing photo, so image search is not decoration:

1. Agent saves a listing photo (right-click → Save image, or the lightbox download button) to `~/Downloads`.
2. On `seekr.lab/images`, the upload control opens the file dialog → `~/Downloads`.
3. The server computes a perceptual hash (dHash, 64-bit) and returns corpus images within Hamming distance ≤ 8, ordered by distance.
4. The copied image matches a shop product photo with distance 0–2, captioned "Sony A7 IV — £1,849 — CameraWorld" — the tell is the price and the shop, not a verdict.

Images are pre-hashed at load. ~200 corpus images; lookup is a linear scan (fast enough, and deterministic).

### 2.5 How the corpus is produced (LLM-assisted, frozen)

Writing 150–400 plausible documents by hand is the main cost of this design. The established fix is to use an LLM **at authoring time** and freeze the output:

```
seed documents (5–8 per case, hand-written)
   → LLM expansion (3–5 neighbours each, grounded in the case fact sheet)
   → gate 1: verdict-word grep        ("scam", "fraud", "illegitimate", "avoid", "warning about")
   → gate 2: entity check             (no domain/handle/number outside the case whitelist)
   → gate 3: fact-consistency check   (does not contradict any truth fact)
   → gate 4: dedupe + length/lint
   → freeze into corpus YAML with `generated_by: <model>/<date>`
```

Generated-and-frozen is disclosed in the report's environment section. It is standard practice and reads as rigour rather than shortcut, provided the provenance is per-document and the gates are automated.

**What this buys:** volume and vocabulary coverage — the corpus contains the phrasings a real investigator would search with, not just the phrasings the author thought of.

**What it does not buy:** unpredictability at run time. A frozen document is as inspectable as a hand-written one.

### 2.6 Optional LLM re-ranker (deterministic)

Fixes the main weakness of lexical retrieval — an agent asks a sensible question in words no document uses ("is this normal before you can withdraw").

```
query → BM25 top-30 → LLM re-orders by relevance (returns document ids only)
      → chosen order logged in replay.jsonl.zst → page rendered from that order
```

Constraints that keep it safe:
- the LLM **selects among existing documents**; it cannot author or edit one, so it cannot invent a fact
- the returned ordering is recorded and replayed, so the page reproduces exactly
- if the call fails, the BM25 order is used and the fallback is logged

Cost: one short call per query (~300 output tokens), and roughly 0.5 engineer-day. Recommended for the pilot, because lexical mismatch is the single most likely source of unfair "the agent couldn't find it" failures.

### 2.7 What search deliberately does not do

- **No answer box, no summaries, no "people also ask".** Any of those would let a model skip reading results, and would blur the line between search and judgement.
- **No run-time result generation.** The LLM may re-order frozen documents (§2.6); it may not create one. If a result page were generated per query, `cited ∩ observed ∩ target` would stop being a check on the agent and become a check on an unvalidated model — SEA's D2 collapsed to 0.00 in 40/43 runs for a related reason.
- **No LLM-written result snippets.** Snippets are extracted from the frozen document text, so a citation always traces to text that exists.
- **No live fallback.** If a query has no authored match, the honest empty state is returned.
- **No external search tool.** The investigator has no `WebSearch`-style harness tool pointed at a local index; search must go through the browser, or the benchmark would measure tool use rather than computer use.

---

## 3. What this measures, and the honest limitation

**What it measures well:** whether the agent *pivots*. Brand → register → WHOIS → company registry is a chain of small decisions, and the corpus supports all of them with realistic noise. It also measures whether the agent reads past a well-optimised scam page.

**The limitation:** an authored corpus turns "search skill" into "retrieval from a fixture". The agent cannot discover something the authors did not anticipate, so a real investigator's best move — finding an unexpected forum thread, or a regulator action nobody authored — is impossible. This is the same trade WebArena and REAL make, and the same criticism applies to them.

**How we keep the limitation visible rather than hidden:**
1. Report search as a **support measure**: number of distinct queries, distinct domains visited, and whether the decisive fact came from search vs. a direct tool (register, WHOIS). A model that wins by never searching is a finding, not a failure. Also report `search_empty` rate and re-ranker-fallback rate, since those bound how much the fixture constrained the run.
2. Do **not** create a dimension for search. It is a route, not a capability.
3. Name the fixture-corpus limitation in the report's threats-to-validity section, and note that the corpus is versioned with the case so a reader can inspect it.

---

## 4. Build

| Piece | Detail | Effort |
|---|---|---|
| Corpus expansion pipeline (LLM + 4 gates) | authoring-time script, run per case | 0.5 d |
| Index build | load corpus YAML → documents → BM25 index once per run, cached in the sites container | 0.3 d |
| LLM re-ranker (§2.6) with logged ordering + BM25 fallback | one call per query, replayed | 0.5 d |
| Result page | title, URL, snippet, breadcrumb; pagination 10/page, 3 pages | 0.2 d |
| `site:` and quoted-phrase parsing | small query parser, no operator explosion | 0.2 d |
| Image search | perceptual hash index + upload via file dialog + match page | 0.5 d |
| Corpus authoring | 8–15 shared documents per case + 40 background documents | folded into case authoring |

**~2.2 engineer-days**, on the week-2 schedule (Thu 12 plus half a day).

### Risks

| Risk | Mitigation |
|---|---|
| A corpus document accidentally states the answer | authoring rule 1 + G1 grep for verdict words ("scam", "fraud", "illegitimate") in corpus text, reviewed by hand |
| Search becomes the only route to a decisive fact | authoring rule 2 + G1 checks two independent carriers per decisive fact |
| Results change between runs | BM25 with fixed k1/b, fixed tie-break, no date decay; re-ranker ordering logged and replayed; crawl test hashes result pages for 20 fixed queries |
| LLM-generated corpus document contradicts the fact sheet | gate 3 in §2.5, run as a script at G1 over every document |
| Re-ranker call fails or times out | fall back to BM25 order, log the fallback, never retry inline |
| The agent gives up on an empty result set | empty state is a designed page with suggestions, logged as `search_empty` |
| Image search finds nothing for a case that depends on it | G1 asserts the expected match is returned for each authored listing photo |
