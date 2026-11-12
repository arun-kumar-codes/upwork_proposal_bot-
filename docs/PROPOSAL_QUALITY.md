# Proposal Quality — Diagnosis, Fix and Evidence

Date: 2026-11-12 · Scope: proposal generation only (Hub Simulated + Real Bot).
Preserved: profile isolation, portfolio mapping (incl. Gopalan + Vikas Singh),
identity validation, internal-notes guard, live-URL-only links, no-commas
contract, portfolio lines and fixed closing.

## Why proposals felt generic (root causes, verified live)

1. **Selection ignored the job.** Hub `select_projects` took an exact
   category match else most-recent projects; compound Hub categories
   (`ai + full stack`) never equal the detected `ai`, so Atul's
   document-Q&A job proved itself with Magdalenap (a WordPress course
   site) while Lomex AI (tenants upload documents and ask questions) sat
   unused. Bot scoring was the same shape (+3/+3/+2/+1).
2. **One template for every job.** Identical `_JOB_PHRASES` line and the
   same three `FIT_LINES` regardless of the client's problem; the proof
   project was simply the first with a live link.
3. **Skills were invented or generic.** Live data has `skills=[]` on every
   profile and `tech_stack=[]` on every project, yet the Bot derived
   "skills" from the client's own job text (Arun: "I work with React and
   Node.js") and the Hub template fell back to "modern web tools". The
   Simulated prompt never received profile skills at all.
4. **The LLM was boxed in.** Facts were title + 140 chars + link, with no
   job analysis, so relevance and personalisation had nothing to work
   from; the validator checked shape only, never accuracy.

## What changed

Both engines (Hub `backend/app/services/playground.py`, Bot `bot/index.js`)
now share the same pipeline:

- **Job analysis** (`analyze_job`/`analyzeJob`): deterministic needs
  (voice, document Q&A, CRM/booking, store, dashboard, scraping,
  automation, AI agent, website), technologies the client names
  ("asks"), evidence words, and the client's name when they give one.
- **Relevant matching** (`score_project`/`scoreProject`): category-token
  overlap (compound categories now relate), need-proof hits, job-word
  overlap with the project's public text, verified tech overlap, small
  live-link boost — relevance beats recency, with human reasons
  ("covers your store and checkout need") shown on the Playground card
  and fed to the LLM as "why relevant".
- **Structured personalised template**: greeting with the client's name /
  verified intro (only skills from profile skills + project tech stacks
  are ever claimed) / understanding line mirroring the client's problem /
  most relevant proof with live link and an explicit relevance tie /
  a concrete first step for this job / fit lines / portfolio / closing.
  Role labels come from the freelancer's own top project, never from
  the client's category.
- **Accuracy enforcement**: LLM briefs now carry client needs, verified
  skills, and client asks labelled "do not claim unless verified", plus
  per-project relevance reasons. Both validators reject skill claims
  (`I work with …`, `experience in …`, `specialize in …`, `skilled in …`)
  naming technology with no verified source; violations fall back to
  the deterministic template over the same projects. The Bot also reads
  verified skills (and a portfolio fallback) from the Hub profile record.

## Before / after (live, same jobs)

**Atul — "AI assistant that answers from our own documents"**
- Before (both modes): proof = Magdalenap (WordPress course site);
  Simulated invented "I work with WordPress and AI integrations";
  Real Bot template was the generic three fit lines.
- After: proof = **Lomex AI** in both modes ("covers your answers from
  your documents need"), opening mirrors staff hunting through PDFs,
  first step starts from the client's real documents and top questions.
  No unverified skill claim in either mode.

**Arun — "Lovable style web app for our store"**
- Before: no category detected → proof = No Limit Gaming (sports
  prediction); Simulated invented "React and Node.js".
- After: proof = **AhorraTya** (shoppers, store promotions) in both
  modes; store/checkout understanding and approach lines; no React claim.

**Aayush — hospital CRM (Real Bot)**
- Before: "I am Aayush a CRM dev I work with ai crm systems".
- After: proof = PrimeTime ("CRM for a hospital") with an explicit
  booking-flow relevance tie; no invented skill string.

**Gopalan + Vikas — voice agent (Simulated)**
- After: voice understanding/approach lines, Tellaigent GO proof, both
  verified portfolio lines, Gopalan sign-off. (An LLM draft claiming
  unverified AI experience was rejected by the new validator and the
  personalised template shipped instead.)

**Deepanshu — WhatsApp automation (Real Bot, zero active projects)**
- After: still no fabricated proof; the text now addresses the actual
  automation need instead of a mismatched booking flow.

## Tests

- Backend: **58 passed** (`pytest tests/ -q`). Bot: **25 passed** (`npm test`).
- New coverage: relevance beats recency (both suites), per-job template
  adaptation, unverified-ask never claimed, verified skill claimable,
  validator rejects/accepts by verified set, Simulated prompt carries
  analysis + verified boundary and falls back on an inventing LLM draft.
- Three existing fixtures encoded the old defective behaviour (recency
  order, "I work with voice AI"/"React" with no verified source, exact
  category equality); they were updated to the accuracy contract with
  comments, and the fallback test now also covers a truly unrelated
  category.
- Live guards re-checked: "Not named" → Hub 400; Bot unknown profile →
  404; Bot placeholder → 400.

## Remaining limits (honest)

- Live profiles/projects still carry no `skills`/`tech_stack` data, so
  proposals correctly name few technologies. Populating real skills in
  the dashboard will immediately personalise intros — the Bot already
  reads them from the Hub profile.
- A freelancer with no relevant project (Atul + Shopify job) still cites
  their closest project; the proposal no longer relabels them
  ("Shopify dev"), but there is no "no relevant proof" warning yet.
- Lomex AI's public proof line is its clean-but-thin result text
  ("Doc status: In-Progress."); a richer client-safe description in the
  Hub would improve that one proposal. Internal notes remain blocked.
- Simulated LLM output still varies run to run; anything off-contract
  (including invented skills) is replaced by the personalised template.
