# Proposal Bot (Hub-backed)

Real proposal generator for Project Hub Playground **Real Bot** mode.
No Slack yet.

## Run

```bash
cp bot/.env.example bot/.env   # BOT_API_KEY must match Hub BOT_API_KEY
cd bot && npm install && npm start   # PORT (default 9000)
```

Docker: `docker compose up --build` runs it as `bot` (Hub: `http://bot:9000`,
bot reads Hub at `http://api:8000`).

## How it works

1. `POST /generate` checks `X-API-Key` vs `BOT_API_KEY` (`401` wrong/missing,
   `503` unset; non-JSON body `400`).
2. Fetches Hub `GET /api/categories` + `GET /api/projects?status=active`
   + `GET /api/meta/profiles` with `X-API-Key: $HUB_API_KEY` (30s in-memory
   cache). Hub unreachable falls back to any `projects` in the request
   payload, then to no projects.
3. **Profile isolation:** a missing or placeholder `profile` ("Not named",
   "Unknown", "N/A", blank) is rejected (`400`) before any generation;
   when the Hub answered, an unknown `profile` is
   rejected (`404 Profile not found`) and the ranking pool is filtered to
   projects linked to that freelancer only — other freelancers' projects
   are never ranked or cited. A freelancer with no eligible projects gets
   the deterministic no-proof template (no "recently" claim). Payload
   projects carrying profile links are filtered the same way.
4. Detects the category (explicit `category` wins; tech aliases like
   React/ML/Shopify normalize onto Hub categories) and ranks within the
   freelancer's own projects: profile + category match, `live_url`
   presence, light `tech_stack` overlap. Top 3.
5. Generates with OpenAI when `OPENAI_API_KEY` is set; otherwise (or on
   OpenAI failure) uses **stub mode**: a deterministic template over the
   same selected projects — no invented claims. With no eligible projects
   the template is always used (the LLM is never asked to invent proof).
   Response `mode` says which.
6. Returns `{ success, proposal, reply, category, source, projects, mode }`.
   `source` is `hub` when Hub projects with live demos were used, else
   `fallback`. Only `title` + `live_url` ever appear — `github_url` is
   dropped at selection and stripped from generated text.

Tests: `npm test` (selection, detection, hub/fallback, auth).
