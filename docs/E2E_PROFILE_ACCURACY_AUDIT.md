# E2E Audit — Profile Accuracy in Proposal Generation

Date: 2026-11-06 · Scope: testing only. **No code was changed for this audit.**
Live system tested: Hub `http://127.0.0.1:20330`, Bot `http://127.0.0.1:20321`, Web :20315.
Hub status at test time: `llm_configured=true, bot_configured=true, github_configured=false, llm_model=gpt-4o-mini`.

## Verdict

**The platform does NOT reliably use the selected freelancer's profile.**

- **Simulated (Hub) mode is profile-safe for project selection** — it only picks from the
  selected profile's own active projects. Its failures are missing portfolio links for
  some names, fabricated skill claims, and irrelevant "most recent" picks.
- **Real Bot mode is not profile-safe.** The Bot ignores the projects the Hub selected
  and re-ranks **all** active Hub projects globally. Freelancers with few/no projects
  get proposals that present **other freelancers' projects as their own work**, with
  `source: "hub"` and HTTP 200. This is deterministic ranking behaviour, not LLM
  randomness (reproduced with the deterministic template, `mode: "stub"`).
- The Hub has **no real per-freelancer data to personalise from**: every live profile
  has `skills=[]`, `portfolio_url=null`, empty intro, and every project has
  `tech_stack=[]`. Anything specific in a proposal ("I work with React and Node.js")
  is invented by the LLM or derived from the job text — never from the freelancer.

## How the two modes actually flow (evidence)

| Step | Simulated (`mode=simulated`) | Real Bot (`mode=real_bot`) |
|---|---|---|
| Profile resolve | Hub `_resolve_profile`: exact ID or case-insensitive `Profile.name`; unknown → 404 | Same Hub resolve, then only the **name string** is forwarded |
| Project pool | Selected profile's own active projects only (`profile.projects`) | Hub sends its picked projects, but Bot **discards them when Hub is up** and fetches `GET /api/projects?status=active&limit=100` (all freelancers) |
| Selection | Hub `select_projects`: exact category match, else recent-active fallback (live first) | Bot `selectProjects`: score = profile +3, category +3, live_url +2, tech overlap +1 each; top 3 of the **global** pool |
| Skills in text | Template fallback: Hub `profile.skills`, else project `tech_stack`; LLM path: not sent at all | Job-text/project tech tokens only; Hub profile skills/intro/tone are **never fetched** |
| Portfolio | Hardcoded `PORTFOLIO_LINKS` map wins; Hub `profile.portfolio_url` only if map misses | Hardcoded map only; Hub `portfolio_url` never consulted |
| Result stored | Hub run: selected + reply | Hub stores **Hub's** selected list, but the Bot's `source`/`projects`/`mode` are thrown away (`call_real_bot` returns reply text only) |

Key files: [backend/app/routers/playground.py](/srv/agents/data/docs/Crew/project-hub-a323d351/code/project-hub/backend/app/routers/playground.py),
[backend/app/services/playground.py](/srv/agents/data/docs/Crew/project-hub-a323d351/code/project-hub/backend/app/services/playground.py),
[bot/index.js](/srv/agents/data/docs/Crew/project-hub-a323d351/code/project-hub/bot/index.js).

## Live test data (Hub DB at audit time)

59 projects · 35 active · 27 active with `live_url` · 12 profiles · **all profiles
`skills=[]`, `portfolio_url=null`** · **all projects `tech_stack=[]`**.

| Hub profile (exact name) | Projects | Active | Notes |
|---|---|---|---|
| Atul | 15 | 10 | |
| Arun | 9 | 3 | |
| Aayush | 4 | 2 | |
| Rahul | 6 | 2 | |
| Mahima | 2 | 2 | |
| Gopalan | 2 | 2 | Name does **not** match portfolio-map key `gopal` |
| Gopalan + Vikas | 2 | 2 | Combined token; no matching portfolio key |
| Yuvraj | 1 | 1 | |
| Deepanshu | 2 | **0** | |
| Faizal / LYT | 1 | **0** | Alias-resolves to Faisal portfolio |
| Kishan | 1 | **0** | Only project is inactive (but has a live_url) |
| Not named | 14 | 11 | Bucket for blank-profile Excel rows; selectable in the UI |

Three different naming systems coexist and disagree: Excel/Hub names
(`Gopalan`, `Gopalan + Vikas`, `Faizal / LYT`), [scripts/profile_aliases.json](/srv/agents/data/docs/Crew/project-hub-a323d351/code/project-hub/scripts/profile_aliases.json)
canonical names (`Gopal`, `Gopal/Vikas`, `Faizal/LYT`), and the proposal portfolio
maps (`gopal`, `vikas kumar`, `vikas singh`). `normalize_profiles.py` dry-run reports
`Gopalan`, `Gopalan + Vikas`, `Not named` as **unresolved** (left untouched).

---

## Findings

Severity: **P0** = wrong person / false claim to a client · **P1** = inconsistent or
misleading · **P2** = minor / cosmetic.

### P0-1 — Real Bot attributes other freelancers' projects to the selected freelancer

- **Where:** Bot fetches the global active pool ([bot/index.js](/srv/agents/data/docs/Crew/project-hub-a323d351/code/project-hub/bot/index.js) `fetchHub`/`selectProjects`); profile match is only +3, so category (+3) + live_url (+2) + tech (+1) can beat it. Hub-sent projects are ignored whenever the Hub is reachable.
- **Repro (live, Bot `POST /generate`):** profile `Deepanshu` (0 active projects), job "AI automation tool for WhatsApp".
  - Expected: no project proof, or a clear "no matching project" outcome.
  - Actual (`mode: "stub"`, `source: "hub"`): *"recently I worked on Magdalenap https://online.magdalenap.com/courses/wow-courses-formula-3/"* — Magdalenap belongs to **Atul**. Bot also returns AI Cofounder (Atul) and Mr White (Not named) as this freelancer's projects.
- Same for `Kishan` (0 active): cites Atul's AI Cofounder as *"recently I've worked on an AI Cofounder project"* via Hub Playground **and** direct Bot calls.
- **Deterministic proof (offline, Bot `_test.selectProjects`):** own project (profile match, no live/category) scores 3; a foreign project (category + tech + live) scores 6 and ranks first. Not an LLM fluke.
- Hub-down fallback differs: with the Hub unreachable the Bot uses the caller-supplied projects (through the Playground those are profile-scoped, so fallback is accidentally safer than the Hub-up path).

### P0-2 — Bot never checks that the freelancer exists

- **Repro:** `POST /generate` with `profile: "Zztop Unknown"` → HTTP 200, *"I am Zztop a web dev I work with AI…"*, citing Atul's AI Cofounder. The Bot has no profile lookup at all (it never calls `/api/profiles` or `/api/meta/profiles`).
- Expected: 404/400 like the Hub Playground (`Nobody XYZ` → Hub 404, verified). Actual: a signed proposal for anyone.

### P0-3 — "Not named" is a selectable freelancer and signs proposals as "Not"

- The blank-profile Excel bucket became a real Hub profile owning 14 projects (11 active) and appears in the Playground profile dropdown.
- **Repro (live, Simulated):** profile `Not named` → *"hey Aparna I am Not a web dev…"*, sign-off *"Best regards / Not."*, citing Mr White / Ghsrk AI / PatentWatch AI as its work.
- Expected: unattributed projects are never proposal-ready under a fake person.

### P0-4 — Gopalan / "Gopalan + Vikas" get no portfolio and the second person is erased

- Hub names `Gopalan` and `Gopalan + Vikas` match no key in either portfolio map (`gopal`, `vikas kumar`, `vikas singh`); resolver returns `portfolio: null` (verified live + offline for both Hub and Bot resolvers).
- **Actual (live, both modes):** proposals for Gopalan end with no `please review my portfolio:` line at all. "Gopalan + Vikas" signs as **Gopalan only** — Vikas silently disappears. A bare `Vikas` (Bot direct) also resolves to no portfolio.
- Expected: every real freelancer's proposal carries their own portfolio link; combined ownership is handled explicitly, not by dropping a person.

### P0-5 — Internal Excel Notes are pasted verbatim into client proposals

Project `result` (the Excel "Notes" column) is used as the proposal's proof sentence
(`asSentence(proof.result || proof.description)` in both engines). Live examples sent
as client-facing text:

- *"recently I worked on No Limit Gaming … Live product. Git URL not given."*
- *"recently I worked on Multi-broker trading platform … Live dashboard IP. Not an ML model. Team confirmed Active (Slack)."*
- Under **Gopal's** name (Bot direct): AI Cofounder proof line *"Added from Google Sheet. Linked to theentrepreneurlab / Atul profile."* — another freelancer's name inside the proposal.

Expected: only client-safe project descriptions reach a proposal; internal notes never do.

### P0-6 — Skills/experience claims are fabricated; there is no source data for them

- Live data: every profile `skills=[]`, every project `tech_stack=[]`. The Simulated LLM prompt never even receives profile skills; the Bot never receives the Hub profile record.
- Live inventions: Aayush *"I work with React and Node.js"*, Arun *"HTML CSS JavaScript"*, Kishan *"experience integrating AI agents in various platforms like WordPress"*, Zztop *"I work with AI"*. None of this exists in Hub data.
- Template mode instead claims *"I work with modern web tools"* or a role guessed from the category — generic, not the freelancer's.
- Profiles UI fields `intro` ("Used by the proposal bot"), `tone`, `signature` are **read by no generator**; `skills` is read only by the Simulated template fallback. Editing a profile in the dashboard therefore cannot fix Real Bot personalisation.

### P1-7 — Playground "Selected projects" and History do not describe Real Bot replies

Two independent selections happen (Hub profile-scoped, then Bot global). The API
response and History show only the Hub's.

- History run 37 (this audit): profile Kishan, `selected=[]`, reply cites AI Cofounder. Run 27 (Atul): selected = Scripting and Automation / Edwin scraping pipeline; reply cites AI Cofounder.
- The Bot's `source`, `projects`, and `mode` (openai vs stub) are discarded by `call_real_bot`; neither the response schema nor History can show them. An auditor cannot tell from the product which projects the Bot actually used or whether the LLM or the template wrote the reply.

### P1-8 — Hub and Bot disagree about category

- Hub categories are compound (`ai + full stack + automation`). Bot `canonicalOf` collapses any compound containing "ai" to `ai`.
- **Repro (live):** explicit category `ai + full stack + automation` → Bot responds `category: "ai"` while returning Arun's full-stack projects. With explicit `ai`, the Bot still returns `ai + full stack…` projects (category is a score, not a filter).
- The Lovable store job detects **no category at all** in the Hub (`detected_category=null`), so selection degrades to "most recent projects" (see P1-11).

### P1-9 — Portfolio source of truth is a hardcoded code map, not the Hub profile

- Hub Simulated: hardcoded map beats `Profile.portfolio_url`. Bot: Hub profile is never fetched, so `portfolio_url` is ignored entirely.
- Consequence: adding/renaming a freelancer in the dashboard silently produces proposals with a missing (P0-4) or stale portfolio link until someone edits both code files (`PORTFOLIO_LINKS` exists in two places: Hub service and Bot).

### P1-10 — Same input, different proposal (stub/openai flip, greeting, role)

- Identical Aayush Simulated input twice in a row: run 1 = template (*"hey there / I am Aayush a automation dev I work with modern web tools"*), run 2 = LLM (*"hey Aparna / I work with HTML CSS JavaScript"*). Validation failure silently swaps engine; nothing records which ran.
- The Hub never forwards a client name (`PlaygroundRunRequest` has no client-name field; Bot `clientName` is unsupported via the Hub), so the greeting is `hey there` in template mode and `hey Aparna` only when the LLM happens to extract the name from the message.

### P1-11 — Irrelevant proof project when no category matches

With `detected_category=null` both engines fall back to most-recent/global ranking.
Live: Arun's proof for a **store web-app** job is No Limit Gaming (a sports-prediction
site) in both modes. The proposal is profile-correct but job-irrelevant; nothing
warns the user that no relevant project was found.

### P1-12 — Profiles with zero active projects are handled inconsistently

- Simulated (Faizal / LYT, Deepanshu, Kishan-via-Hub): honest but shape-breaking — no `recently` proof line at all, yet the fit lines still claim *"I already know how the full flow should work"*. The template bypasses the validator that would reject this shape.
- Real Bot: fabricates proof from other freelancers (P0-1). Same situation, opposite failure.

### P2-13 — Smaller inconsistencies

- Atul Simulated (LLM): portfolio URL used mid-text as the project "proof" link (*"capabilities here: \<portfolio\>"*) and again in the correct line — the validator only checks presence, not placement/count.
- LLM replies attach sentence punctuation to URLs (`https://primetimekeeper.com/login.`), so copied links need care (validators strip trailing dots only for the portfolio check).
- Bot caches Hub categories/projects for 30s: dashboard edits (new project, status toggle) can lag one Playground run behind.
- API `limit` (1–10) exists on Playground runs but the UI never sends it (always 3); Bot limit is fixed at 3.
- Kishan's only project is inactive **with** a live_url: correctly excluded everywhere, but the UI gives no hint why Kishan has no proof.
- Bot has no `/api/proposal` legacy endpoint and no Slack path in this repo (only `/generate`); nothing in the Playground tells the user this.

## What passed

- Simulated selection never crossed profiles in 8 live cases (Aayush, Arun, Atul, Mahima, Gopalan, Gopalan + Vikas, Not named, Yuvraj all cited their own projects).
- No `github.com` link and no banned corporate phrase appeared in any of the 24 generations in this audit; only `live_url` links plus the portfolio link were emitted.
- Correct portfolio link for Aayush, Arun, Atul, Mahima, Rahul, Yuvraj, Deepanshu, Kishan, and for `Faizal / LYT` → Faisal (alias works in both engines despite spaces/slash).
- Unknown profile via Hub Playground → 404; Bot auth wrong/missing key → 401 (503-unset and 400-non-JSON covered by the Bot test suite).
- Existing suites green at audit time: backend **42 passed**, Bot **10 passed**. They pass because no test asserts cross-profile exclusion, Hub-vs-Bot selection agreement, or portfolio coverage for the live names (the Bot selection test only checks the preferred winner in a same-profile fixture).

## Test log (reproducibility)

All against the live Hub/Bot above. Jobs used: Lovable store job ("Hi I am Aparna we
need a Lovable style web app for our store…") and AI/WhatsApp automation job.

| # | Call | Result |
|---|---|---|
| 1 | Hub Simulated × Aayush, Arun, Atul, Mahima, Gopalan, Gopalan + Vikas, Faizal / LYT, Deepanshu, Not named, Yuvraj | 200; own projects only; portfolio missing for Gopalan pair; "I am Not" for Not named |
| 2 | Hub Real Bot × Arun, Aayush, Atul, Mahima, Gopalan, Rahul, Kishan | 200; Atul reply cites project outside Hub selection; Kishan (selected=[]) cites Atul's AI Cofounder |
| 3 | Hub Simulated, profile `Nobody XYZ` | 404 Profile not found (expected) |
| 4 | Hub Simulated ×2 identical Aayush input | Different engine/greeting/skills (template vs LLM) |
| 5 | Hub Simulated Arun + override `ai` | No exact category match → recent-projects fallback; reply still self-describes as "a ai dev" |
| 6 | Bot direct × Deepanshu, Kishan, Vikas, Gopal, Zztop Unknown | 200 `source: hub`; foreign projects cited as own; unknown person signed |
| 7 | Bot direct, Arun + fake payload project (Hub up) | Fake project ignored; Hub pool used (confirms payload discard) |
| 8 | Bot direct, explicit compound category | Bot reports `category: "ai"`, returns full-stack projects |
| 9 | Bot direct, wrong/missing key | 401 / 401 |
| 10 | Offline Bot `selectProjects` scoring fixture | Foreign project (6) outranks own project (3) — deterministic root cause of #6 |
| 11 | `normalize_profiles.py` dry-run (read-only) | Plans Faizal rename; unresolved: Gopalan, Gopalan + Vikas, Not named |
| 12 | `pytest tests/ -q` / `npm test` | 42 passed / 10 passed |

Side effect, disclosed: Playground testing created History runs 22–40 (history went
21 → 40). No projects, profiles, code, or config were created, edited, or deleted.

## Fix status (updated after the audit)

- **Fixed:** P0-1/P0-2 isolation slice — the Bot filters its ranking pool to
  the selected freelancer's own Hub projects, rejects unknown profiles with
  404 when the Hub can be checked, and never asks the LLM to invent proof
  when a freelancer has no eligible projects (Simulated does the same).
  Regression tests added in `bot/test/generate.test.js` and
  `backend/tests/test_playground.py`; live-verified for Deepanshu, Kishan,
  Atul, Gopalan, and "Zztop Unknown". The Hub now also sends project
  ownership (`profiles`) with its Bot payload.
- **Fixed:** P0-5 internal-notes leakage — both engines now derive proposal
  proof text through a fail-closed `public_proof_text`/`publicProofText`
  guard (clean verified result → public description → nothing); internal
  Notes reach neither templates nor LLM prompts. Regression tests in both
  suites; live-verified on Mahima/Arun/Aayush/Atul examples from this audit.
- **Fixed:** P0-3 placeholder identity — shared name validation
  (`backend/app/services/profile_names.py`, mirrored in the Bot) rejects
  blank/placeholder identities with 400 in Hub Playground (both modes) and
  Bot `/generate` before any generation; resolvers never derive a
  placeholder display name; Excel import no longer creates/links
  placeholder profiles (existing "Not named" data and its 14 projects are
  preserved, just not proposal-eligible). Regression tests in all suites.
- **Fixed:** P0-4 Gopalan portfolio (partial, verified scope) — the portfolio
  service identifies ID `69492fd730db86ebbad04a0b` as **Gopalan Prakash**, so
  Hub "Gopalan" now maps to that verified link in both engines. The owner
  then confirmed the Tellaigent collaborator is **Vikas Singh**
  (`6949306730db86ebbad04a17`). Hardened after self-review: there is NO
  global bare-"Vikas" alias — Singh is credited only inside the explicitly
  allowlisted combined profile (`_COMBINED_COLLABORATORS` /
  `COMBINED_COLLABORATORS`), so lookalike names ("Kishan / Vikas",
  "Newdev + Vikas") earn nothing. The combined proposal (still signed by
  Gopalan, people never merged) carries `please review my portfolio:
  <Gopalan>` and `please review Vikas Singh's portfolio: <Singh>`, enforced
  by both validators. Verified freelancers sign with full canonical names.
  Hub↔Bot maps are asserted identical by a Bot test, and
  `scripts/profile_aliases.json` uses the same verified canonical names.
  Verified live in Simulated and Real Bot modes.
- **Fixed:** P0-6 fabricated skills + generic proposals — both engines
  now analyse the job (needs, client-named tech "asks", evidence words),
  rank owned projects by relevance (need/keyword/tech overlap; compound
  category tokens relate) with shown reasons, generate a structured
  personalised proposal (client-problem opening, relevant proof with
  relevance tie, concrete first step), and claim only verified skills
  (profile skills + project tech stacks). Both validators reject
  unverified skill claims from LLM output and fall back to the
  personalised template. See
  [PROPOSAL_QUALITY.md](/srv/agents/data/docs/Crew/project-hub-a323d351/code/project-hub/docs/PROPOSAL_QUALITY.md).
  Live-verified across Atul/Arun/Aayush/Gopalan + Vikas/Mahima/Deepanshu
  in both modes; backend 58 passed, Bot 25 passed.
- **Still open:** P1-7–P1-12, P2-13 (selection alignment improved by the
  shared relevance scoring; Bot actuals still not surfaced in History).

## Suggested fix order (for the review, not done here)

1. Make Real Bot profile-safe: rank only the selected profile's projects (honour the Hub-sent selection or filter the Hub pool by profile), and return a clear no-proof outcome instead of borrowing projects.
2. Validate the profile in the Bot against the Hub; reject unknown names.
3. Decide one canonical name per freelancer across Excel, aliases file, Hub, and portfolio map; resolve Gopalan/Gopal/Vikas and retire or hide "Not named" from proposal flows.
4. Move portfolio (and skills) to the Hub profile as the single source of truth; have both engines read it.
5. Stop sending internal Notes (`result`) to clients; use a client-safe description field.
6. Record and display the Bot's actual `source`/`projects`/`mode` in Playground results and History so selection and reply can be audited together.
7. Populate real `skills`/`tech_stack` data (or stop claiming skills in proposals until it exists).

