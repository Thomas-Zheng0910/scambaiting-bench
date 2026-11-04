# Active Scam Investigation — Project Plan

Working plan for human researchers and implementation agents · November 3, 2026

## Purpose and agreed scope

Build a desktop environment in which an autonomous agent finds potential scams in a mixed feed, chooses whom to approach, investigates through running apps and websites, and develops a supported judgment over multiple sessions. The eventual outputs are the environment, experimental data, a research report, and a poster.

The design has three parts: **Environment, Agent, and Experiment**. The user has confirmed four decisions: the agent starts from a mixed feed; desktop is the first device setting; actual running applications and web browsing are required to test computer-use ability (CUA); and a case can end once the agent reaches a supported scam/legitimate judgment. Continued engagement after sufficient evidence is optional. The environment is controlled rather than deployed to approach real people online.

Realism comes from two sources: genuine computer interaction and reconstruction of actual advertisements and documented scam cases. A running desktop messaging app and browser provide the interaction. The people responding, their accounts, and the case progression remain under experimental control. The first version needs functional applications rather than exact commercial-platform replicas.

## 1. Environment — Build the world the investigator operates in

### 1.1 What the desktop contains

Provide a desktop with a real browser, a running messaging application, and ordinary file handling. In the browser, the agent can browse a feed, inspect profiles, open linked websites, and use a search/reference service. In the messaging application, it can find contacts, initiate conversations, read replies, exchange permitted information, and return to existing threads. Links and files can move between the browser and messenger through normal desktop interaction.

The feed contains ordinary posts, legitimate advertisements, suspicious legitimate offers, and scam candidates. It should require scrolling, opening posts, and selecting leads. A target must not be identified through a conspicuous benchmark label, filename, or special interface treatment. The initial mixture and ordering are scenario parameters, allowing the experiment to vary discovery difficulty without changing the investigator.

The first websites should cover the functions needed by the pilot: advertisements/profiles, an employer/shop/investment service, and independent reference pages. Reference pages can represent official organization websites, government or regulator records, and domain-registration information. Searches return relevant and irrelevant results; they do not return an evaluator-generated scam verdict.

All sources used for a scored run are supplied within the controlled environment. A real browser can browse local or laboratory-hosted sites. This gives normal navigation, tabs, history, forms, redirects, downloads, and page interaction while preserving the case state for replay.

### 1.2 How to build functional apps without depending on public platforms

Implement the feed and websites as working web applications. Implement the messenger as an independently running desktop app connected to the environment's messaging service. Prefer an adaptable existing client when it supports the required controlled backend; otherwise use a simple desktop application with functional contact lists, threads, notifications, attachments, and links. The selection criterion is whether the investigator can perform the required computer actions and the environment can control the resulting state.

Preserve meaningful interface behavior: opening a thread, finding an old message, switching windows, scrolling a profile, entering a query, using a file dialog, and returning after a notification. Simplify branding, decorative features, account setup, and unrelated app functions. The agent must still execute the interaction rather than receive its result from a hidden semantic shortcut.

Use one desktop configuration for the initial comparison so platform differences do not accidentally become model differences. If a required operation cannot be performed through the visible UI, repair the interface or narrow the task; do not silently give one investigator privileged backend access.

### 1.3 Real advertisements and reconstructed cases

For each source case, retain provenance, the documented sequence, the original public claims, and what the source actually establishes. Keep the source material distinct from the reconstructed executable case. A documented scam can provide a real narrative and authentic advertisement wording, while the experimental actor, accounts, contact endpoints, and linked services are controlled substitutes.

Preserve the clues needed for the investigation when changing identifiers. For example, a replaced lookalike domain must retain the relevant mismatch with the reconstructed genuine organization. Importing an advertisement must not leave a contact button that unexpectedly reaches its original operator. Record modifications so the eventual report can describe which elements are sourced and which are simulated.

Source conclusions belong in the author's hidden case record. They should not appear in the feed or in reference results unless access to that report is an intentional part of the case. Legitimate examples must receive comparable attention to presentation and conversation quality. A polished page or a move to messaging should occur in both truth conditions.

### 1.4 One persistent world across services

Maintain a common state for actors, accounts, aliases, posts, messages, websites, files, and transactions. Distinguish actual facts, claims made by actors, and observations available to the investigator. The investigator may see the same phone number in an advertisement and a conversation, but it discovers that connection through the interfaces. It cannot query a hidden identity table.

Each source has an owner. Several testimonials and websites controlled by one actor remain dependent evidence even if they look separate. Profile edits, deleted messages, new posts, and changed website content are recorded as state changes. The world persists when a session or desktop process restarts.

### 1.5 Scammers, legitimate counterparts, and progression

Each counterpart has a role, account, knowledge, goal, relevant history, and rules for responding. A scenario may use one person or several coordinated personas such as recruiter, manager, adviser, group member, and customer support. These personas are part of the environment; they do not imply several cooperating investigator agents.

Use authored factual constraints and progression rules, with an LLM generating natural responses where useful. The controller decides what information exists and what a persona can reveal. The response model can phrase a reply or handle an unexpected question but cannot change whether the employer exists, invent a verified license, or expose future facts without the necessary events. Legitimate actors can ask reasonable questions, decline requests, and reply slowly too.

Progression should respond to actions. Asking about onboarding can reveal an onboarding link; asking about withdrawal conditions can elicit a fee claim. The scenario must also handle ordinary alternative routes, repeated questions, refusal, silence, and departure. If the investigator obtains decisive evidence early, the world does not force it through every planned stage.

### 1.6 Time and an illustrative case

The environment owns a virtual clock and event queue. Events specify a time, prerequisites, actor, content, and state effect. The investigator can wait or set a reminder; the scheduler advances time and delivers ordinary notifications. It never exposes hidden event names or announces when decisive evidence will appear.

For example, an investment case may begin with an advertisement, continue through a private adviser conversation, introduce a group or website later, and eventually expose a request for money. Useful evidence can also be found earlier through profile history or a contradictory reference record. A benign counterpart uses a comparable contact path but makes verifiable claims and offers a legitimate arrangement. Exact progression and delays belong to each case rather than one universal script.

**Environment completion criterion:** a human can use the desktop to discover a candidate, initiate a conversation, follow a lead across app boundaries, receive a delayed reply, inspect independent information, and resume the same case after restart. The resulting observations and state changes can be reconstructed from the recorded run.

## 2. Agent — Build a continuing investigator around a CUA model

### 2.1 Assignment and access

The investigator receives a mission to review the mixed feed, choose leads, investigate within its resource and time limits, and maintain supported assessments. It receives a consistent synthetic persona for permitted conversations. Its tools operate the computer through screenshots, mouse actions, keyboard input, window switching, and ordinary files. The first evaluated configuration uses these visible interactions for browsing and messaging.

The surrounding harness runs the model, executes computer actions, supplies observations, stores authorized memory, and wakes the agent. Backend APIs can initialize the world and record events for researchers, but are not investigator tools. The agent receives neither ground-truth labels nor the gold evidence checklist or future dialogue stages.

### 2.2 Investigation loop

At each activation, the agent reads the current screen and relevant retained case records, identifies what has changed, chooses its next useful action, and performs the necessary computer interactions. It can inspect another lead, contact someone, ask a question, check a claim, follow a website, revisit an earlier source, or wait. After a meaningful action or conversation exchange, it updates its case record and decides whether to continue, pause, close, or abandon the case.

Let the agent make these choices rather than prescribing one successful sequence. The instruction should establish the assignment and action limits without revealing which query, page, or dialogue branch proves the case. A fixed investigation sequence is useful as a baseline, not the default autonomous agent.

Use one investigator for the first system. It can manage several cases in the same desktop, including pending conversations. A team of specialist investigators is an optional later comparison; adding that coordination now would obscure whether failures arise from computer use, memory, investigation strategy, or inter-agent communication.

### 2.3 Memory and case records

Retain a record for each candidate: where it was found, accounts and identities involved, what was claimed, observations with their sources and times, unresolved questions, current assessment, pending replies, and next planned activity. Facts, quoted claims, and hypotheses need distinct fields or explicit labels. Keep raw conversation and action history separately so a summary can be checked against what actually happened.

The case record should help the investigator resume a task without replaying every prior screen. For instance: “Asked about withdrawals; waiting for adviser reply; website currently claims withdrawals are free.” On return, a new fee demand should be connected to that earlier claim. Similar display names must not automatically merge two people or cases.

The initial design uses agent-maintained notes plus retrieval of stored history. The exact memory format remains a proposed implementation choice. Experiments can compare recent context alone, history retrieval, and structured case notes with explicit storage/context budgets.

### 2.4 Sessions, waiting, and long-term behavior

An action is one computer operation; an interaction is a meaningful exchange or check; a session is one activation period; a case is an investigation of a candidate; a run contains the feed and all cases handled within the assigned horizon. Record these separately so “turn count” does not mix clicks with conversation exchanges.

End sessions at declared boundaries, such as waiting for a reply, a simulated daily cutoff, or a resource limit. At the next session, construct the model context from the allowed memory and current observations. Record notifications and reminders missed or handled. Introduce other leads and intervening activity so remembering a case is an actual requirement.

Waiting can be the correct action when useful information is unavailable. Repeatedly reopening an unchanged thread should consume actions without advancing a hidden scenario stage. A follow-up can trigger a response if its authored rules allow it. Track elapsed world time, sessions, and computer actions independently; simulated weeks do not require weeks of continuous computation.

### 2.5 Judgment, stopping, and operating boundaries

Keep assessments provisional during the process: unresolved, leaning scam, leaning legitimate, or sufficient evidence for a conclusion. These are recorded states rather than extra agent roles. The investigator can revise a belief as evidence changes. Once it has a supported scam or legitimate judgment, it can close the case; exposing every future harmful request is not mandatory.

The environment supplies permitted persona information and makes protected information distinguishable. Approaching a synthetic counterpart is authorized. Disclosure of protected data, credential submission, value transfer, permission grants, and execution of untrusted content have explicit case-level consequences. Safe inspection can be offered through a visible isolated application or inspection mode. Attempts blocked by controls remain visible in the trace but are distinguished from actions actually completed inside the simulated world.

The agent should finish a run with a case table listing investigated leads, supported conclusions, unresolved cases, and the key observations behind its decisions. Its reasoning is assessed from observable actions, concise recorded assessments, and reports; private chain-of-thought is not required.

**Agent completion criterion:** the same investigator can select a lead, operate both browser and messenger, preserve a case across sessions, perform a follow-up or independent check, revise its assessment, and close a case with cited observations. It can handle a pending case while working on another lead.

## 3. Experiment — Decide what cases to run and what performance means

### 3.1 Cases and underlying truth

Organize cases with the three agreed descriptors: scam family, contact surface, and harm surface. Job/task, investment, and marketplace cases are proposed starting families; this selection remains open to revision. Each template includes actors, initial feed content, platform transitions, event conditions, key observable facts, alternative investigation paths, permitted/risky actions, and the expected basis for judging it.

Include legitimate counterparts and ordinary distractors. A legitimate case must offer positive grounds for its conclusion, not simply lack an obvious red flag. A scam case must be distinguishable through evidence the investigator can access under its assigned tools. Some prefixes may remain inconclusive until more interaction occurs. Hidden case truth and what can be established at a particular time are separate annotations.

Annotate facts atomically with their source, meaning, availability, and dependencies. Specify one or more sufficient evidence sets rather than one required transcript. Distinguish when a fact exists, when the agent can access it, and when it actually observes it. Credit a valid unexpected route after review, and version any scoring change consistently across compared systems.

For the first pilot, a proposed size is six underlying templates, two per starting family, each with a scam and legitimate version. These 12 case instances can be embedded among additional ordinary feed posts. The pilot size and feed prevalence are design choices rather than fixed claims about real-world frequency. Keep related variants together when separating development from held-out evaluation.

### 3.2 Candidate evaluation measures

The scoring should describe the extended investigation. The following measures are candidates for the pilot, not a finalized replacement D1–D5 rubric. Hallucination is not a standalone primary metric. Evidence must nevertheless be grounded in recorded observations for a conclusion to count as supported.

| Capability | Proposed observation and measure |
|---|---|
| Find useful leads | Fraction of designated scam candidates noticed and investigated; legitimate cases selected; investigate selection against the full visible feed, including missed scams |
| Establish and advance an investigation | Whether meaningful contact occurs and case-specific investigative objectives are reached, such as establishing the actual offer, transaction terms, or identity relationship |
| Acquire and connect evidence | Distinct useful clues recognized, sufficient evidence sets completed, and correct connections across sources; retain both evidence found during the run and evidence presented in the report |
| Maintain continuity | Appropriate return to pending cases, use of earlier facts when later events make them relevant, and preservation of identity/claim distinctions across sessions |
| Resolve a case | Correct supported scam/legitimate conclusion; incorrect conclusion; or unresolved case, with separate recording of whether resolution was achievable within that run |
| Operate safely | Prohibited decisions attempted and prohibited actions completed, categorized by information disclosure, execution, permissions, or value transfer |
| Use resources appropriately | Computer actions, meaningful checks, messages, sessions, and time until supported resolution; continuation after sufficient evidence and repeated unproductive activity |

Useful interaction is judged by what it helps establish, not by conversation length or how humanlike the investigator sounds. Merely visiting every annotated page is not evidence understanding. An early supported stop should not lose credit for failing to collect redundant clues, and a lucky early guess should not receive credit as efficient supported resolution.

For cases that remain unresolved, retain how far the investigation progressed and which opportunities were available. Do not assign zero cost to failure or treat every waiting period as inefficiency. Human-authored reference paths provide interpretable comparisons for checks and computer actions, not a proven universal minimum.

The unresolved scoring question is how to summarize process progress without favoring one scripted route. The proposed approach is a small set of case-specific investigative objectives with alternative ways to satisfy them, reported alongside final outcome and the full timeline. The pilot should establish whether those objectives are clear enough for consistent scoring before a main experiment is fixed.

### 3.3 Experimental comparisons

First compare a fixed-check investigator with an autonomous investigator using the same CUA interface, underlying model, and budgets. The fixed workflow can inspect a profile, ask predefined questions, and check an official source; the autonomous version chooses which actions to take and when. This tests the value of investigation strategy without changing the basic tool access.

For platform effects, place equivalent case evidence in one service or distribute it across the feed, messenger, and website. Record extra interface actions separately from failures to connect evidence. For temporal effects, compare a continuous-session version with a multi-session version preserving the same evidence order; separately test changing content and intervening cases. This avoids attributing every difference to memory when the available facts also changed.

Compare memory support on a selected subset after the initial harness works. Use the same cases and disclose context/storage limits for each configuration. Multiple investigator agents are an optional later condition. Several simulated counterpart personas can already appear in all configurations.

A classifier given only initial posts can be a low-cost reference, but its access is narrower than an investigator's. Give a separate classifier the investigator's collected observations on a subset to examine interpretation independently of acquisition. These are supplementary comparisons; the main task remains operating the desktop and developing investigations.

### 3.4 Data to retain and how to interpret it

For each run, retain the case/environment version, random seeds, model configuration, available tools, budgets, feed order, clock events, screenshots, computer actions, app/browser transitions, sent and received messages, memory snapshots, checkpoint assessments, and final case table. A trace entry needs the world time, session/case association, observation, action, result, and relevant recorded state change.

Use environment events for objective facts such as messages sent or files executed. Use annotated observations and the agent's explicit report for evidence interpretation. Where semantic judgment is necessary, retain the relevant excerpt and a checkable scoring explanation; do not give an automated evaluator a vague instruction to score overall quality.

Run the pilot with repeated trials and inspect failure sources: missed lead, unproductive questioning, forgotten fact, mistaken cross-platform connection, computer-use error, unsafe action, premature stop, or failure to stop. A broken interface or invalid counterpart response is an environment failure and should be recorded separately from an agent failure.

Before the main comparison, freeze scenario versions, scoring definitions, prompts, and budgets. Repeat conditions with matched world seeds where possible. Summarize by underlying template rather than treating paraphrases and repeated runs as independent cases. Report detection and resolution over time alongside final outcomes so a single terminal label does not hide the process.

### 3.5 Execution and final outputs

Implement one complete scam/legitimate pair first, then expand the feed and pilot templates. Run the same tasks through the fixed and autonomous investigators, inspect the collected trajectories, and refine the environment and scoring where they are ambiguous. Select the main experiment size and repetition count using pilot variability and measured cost rather than an arbitrary large run count.

The research report should explain the three parts of this plan, the conditions actually run, their results, and representative trajectories that support the findings. The poster should show the environment workflow, one multi-session case timeline, the central experimental comparisons, and the most informative results. Preparing these outputs follows the experiments; neither requires a separate live-deployment workstream.

**Experiment completion criterion:** the team can run a versioned mixed-feed scenario repeatedly, inspect the full investigation, score both process and supported outcome, and produce comparison tables and timelines from saved data. Metric names and numerical thresholds remain provisional until the pilot resolves the scoring questions above.
