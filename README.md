# Project Hub

Central store for freelance projects and Upwork profiles, with an API for the
proposal bot and a dashboard for managing everything.

- **Backend:** FastAPI + SQLAlchemy 2.0 + Alembic (`DATABASE_URL`: SQLite locally, Postgres-ready)
- **Frontend:** Next.js (App Router) + TypeScript + Tailwind + shadcn/ui-style components
- **Auth:** dashboard uses a single admin password (`ADMIN_PASSWORD`); the API uses `X-API-Key` (`API_KEY`)

## Quick start (local dev)

```bash
cp .env.example .env        # then edit API_KEY and ADMIN_PASSWORD

# Backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend
alembic upgrade head
uvicorn app.main:app --port 8000   # API at http://localhost:8000 (docs at /docs)
cd ..

# Frontend (new terminal)
cd frontend
npm install
npm run dev                      # dashboard at http://localhost:3000
```

Log in to the dashboard with `ADMIN_PASSWORD`.

## Docker

```bash
cp .env.example .env   # set API_KEY and ADMIN_PASSWORD
docker compose up --build
```

Starts `db` (Postgres), `api` (port 8000, migrations run on start), and `web`
(port 3000).

## API (all under `/api`, all require `X-API-Key`)

| Method | Path | Purpose |
|---|---|---|
| GET/POST | `/api/projects` | List (filters below) / create |
| GET/PUT/PATCH/DELETE | `/api/projects/{id}` | Read / update / delete |
| POST | `/api/projects/{id}/toggle-status` | Flip active ↔ inactive (archived → active) |
| GET/POST | `/api/profiles` | List / create |
| GET | `/api/profiles/{name or id}` | Profile with `projects` + `active_projects` |
| PUT/PATCH/DELETE | `/api/profiles/{id}` | Update / delete |
| POST | `/api/import/excel` | Upload `.xlsx` (`?dry_run=true` previews only) |
| GET | `/api/github/prefill?url=…` | Repo name/description/README for the form |
| POST | `/api/auth/login` | `{password}` → dashboard bearer token |
| GET | `/api/categories` | Distinct project categories, sorted |
| GET | `/api/meta/profiles` | Lightweight profiles (counts, no project detail) for the bot |
| GET | `/api/playground/config` | Which playground modes are enabled |
| GET | `/api/playground/status` | `{llm_configured, bot_configured, github_configured, llm_model}` |
| POST | `/api/playground/run` · `/api/playground/generate` | Simulate a bot reply (aliases, see below) |
| GET | `/api/playground/history` | Saved runs (incl. failed, with `error`), newest first |
| GET | `/api/playground/history/{run_id}` | One saved run |

List filters: `GET /api/projects?profile=Web%20Dev&category=web&status=active&limit=3&q=shop`

```bash
curl -H "X-API-Key: $API_KEY" \
  "http://localhost:8000/api/projects?profile=Web%20Dev&status=active&limit=3"
```

Create/update accept `profile_ids` and/or `profile_names` (unknown names are
created). Category/status are trimmed and lowercased; `tech_stack` accepts a
list or a comma-separated string.

## Excel format

Sheets `projects` and `profiles` (headers are case-insensitive):

- projects: `title* description category status github_url live_url tech_stack
  result client_type profiles`
- profiles: `name* intro skills tone portfolio_url signature`

`*` required. `status` must be `active|inactive|archived` (empty → `active`).
Comma-separated cells become lists. Matches: projects by `github_url`, else
case-insensitive `title`; profiles by case-insensitive `name` — re-imports
update instead of duplicating. Project↔profile links are only rewritten when
the `profiles` cell is non-empty, so dashboard links survive re-imports.
Import summaries include `missing_live_url`: valid project rows with no
live demo URL (proposals share live links only, so fill these in).

Seed from CLI:

```bash
source .venv/bin/activate
python scripts/seed_from_excel.py data.xlsx [--dry-run]
```

## Test Playground

The `/playground` dashboard page previews what the bot would reply to a
client message: pick a profile, paste the job post, optionally override the
category. The output shows the detected category, the selected projects with
reasons, and the generated reply. Every run is saved to history.

- **Simulated** (Hub's own LLM call) needs `OPENAI_API_KEY` in env
  (`LLM_MODEL` default `gpt-4o-mini`). The prompt includes the profile
  intro/tone/signature plus the selected projects, with hard rules: use
  ONLY the given projects, never invent any, and share LIVE demo links
  only — project GitHub URLs never enter the brief or reply text.
- **Real Bot** POSTs the same input to `BOT_URL/generate` and shows the
  bot's real reply (expects `{"reply": "…"}` or plain text). It stays
  disabled until both `BOT_URL` and `BOT_API_KEY` are set.

```bash
curl -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"profile":"Web Dev","client_message":"Build me a store","mode":"simulated"}' \
  http://localhost:8000/api/playground/run
```

### Real Bot handshake (minimal `bot/`)

`bot/` is the Express Proposal Bot (`POST /generate`) behind Real Bot mode. Hub sends `X-API-Key: $BOT_API_KEY`. Proposals use `live_url`
only. Keep the bot private: it only needs to be reachable from the Hub —
do not publish it publicly (compose binds it to `127.0.0.1` only).

**Ports — native live server vs compose (do not mix):**

| Run mode | Web | Hub API | Bot |
|---|---|---|---|
| Native (this live host) | `20315` | `20330` (`BOT_URL=http://127.0.0.1:20321`) | `20321` |
| Docker compose | `3000` | `8000` (`BOT_URL=http://bot:9000`) | `9000` (host `127.0.0.1` only) |

Compose always uses `BOT_URL=http://bot:9000` (service name); the `.env`
`BOT_URL` is for native runs only. Set the same `BOT_API_KEY` on Hub and
bot, then restart both. Real Bot stays disabled until both are set.

**How the Playground distinguishes failures** (`POST /api/playground/run`):

| Bot outcome | Hub response | Playground shows |
|---|---|---|
| OK `200` | `200` + reply | Bot proposal |
| Bot `401` | Hub `401` | "Bot API key mismatch…" — fix `BOT_API_KEY` on both sides |
| Bot `503` | Hub `503` | "Bot API key not configured…" — set `BOT_API_KEY` on the bot |
| Bot down/timeout | Hub `502` | "Bot unreachable…" — bot is down, not a key problem |

The bot reads Hub categories/projects itself (`HUB_URL` + `HUB_API_KEY`),
ranks by profile/category/live_url, and generates with OpenAI when
`OPENAI_API_KEY` is set — otherwise documented stub mode (template over
the same live projects, `mode:"stub"`). The dashboard must point at the
current Hub (`:20330` natively) for Real Bot; older builds on `:20325`
and `:20329` are broken leftovers — never use them.

```bash
# Bot direct (compose port shown; natively use 127.0.0.1:20321):
# happy path (live Hub) -> source:"hub"; Hub down -> source:"fallback"
# correct key → 200 { success, proposal, reply, source, projects }
curl -X POST http://localhost:9000/generate -H "Content-Type: application/json" \
  -H "X-API-Key: $BOT_API_KEY" \
  -d '{"profile":"Web Dev","client_message":"Need a store","category":"web","projects":[{"title":"Shop Demo","github_url":"https://github.com/demo/shop","live_url":"https://shop-demo.example.com"}]}'
# wrong/missing key → bot 401 → Hub 401 (key mismatch, not downtime)
# bot started without BOT_API_KEY → bot 503 → Hub 503 (key unset on bot)
# bot stopped → Hub 502 Bot unreachable
# non-JSON body → bot 400 Expected application/json body
```

Playground: open `/playground`, pick a profile with an active project that
has a `live_url`, paste a job post, choose **Real Bot**, and **Run** — the
reply card shows the bot proposal (live link only). Failed runs are
saved to history with `error` set (fetch one via
`GET /api/playground/history/{run_id}`).

**Live trio & link policy:** the single fixed live deployment is
Web `20315` -> Hub `20330` -> Bot `20321`
(`http://116.202.210.102:20315/login`). These ports do not change.
The old Web `20325`/`20329` (and Hub `20326`) are deprecated leftovers —
do not use them. Link policy: proposals share
**`live_url` only**; GitHub URLs stay in the Hub as source links and never
enter proposal text (enforced in Hub briefs and in the bot, with
`missing_live_url` import warnings for projects that still need one).

**Ops scripts:** `python scripts/check_handshake.py` (read-only Hub/bot
auth + HTML-trap + live_url warnings; `--hub/--bot` override URLs) and
`python scripts/normalize_profiles.py` (dry-run alias plan using
`scripts/profile_aliases.json`; `--apply` backs up the SQLite DB first).

**Stopping strays:** current services record PIDs in `logs/*.pid`
(`web20315`, `hub20330`, `bot20321`) — `kill $(cat logs/<name>.pid)`.
Older ad-hoc instances (ports `20328`, `9000`, Web `20325`/`20329`, Hub `20326`)
have no pidfile: on the host (where `/proc` is visible) run
`ss -tlnp | grep <port>` then `kill <PID>`; the sandbox shell cannot see
those PIDs, which is why they were left running. Never `killall node` —
the frontend and bot are Node processes too.

## Tests

```bash
cd backend
../.venv/bin/python -m pytest tests/ -q
```

Covers the bot filter endpoint (profile/category/status/limit), toggle,
auth, CRUD normalization, the Excel import (preview errors, save,
no-duplicate re-import), and the playground (detection, override,
simulated/real-bot runs, history, bot 401/503/502 mapping). Bot: `cd bot && npm test`.

## Layout

```
backend/app/        FastAPI app (routers/, services/, models, schemas)
backend/alembic/    migrations (DATABASE_URL-driven)
backend/tests/      pytest suite
frontend/app/       dashboard pages (login, projects, profiles, import, playground)
bot/                minimal Proposal Bot stub (POST /generate handshake)
frontend/components/  ui primitives + dialogs
scripts/seed_from_excel.py
```
