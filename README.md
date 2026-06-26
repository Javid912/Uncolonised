# Uncolonised

An agentic-driven digital magazine and event platform for anti-colonial, anti-imperialist movements in Berlin. Every piece of content is curated — no open submissions, no public write endpoints, no bypassing the human in the loop.

```
                  ┌──────────────────────────────────────────────────┐
                  │              CONTENT PIPELINE                    │
                  ├──────────────────────────────────────────────────┤
  Contributor     │  Telegram Bot  →  submissions (pending)          │
  (whitelisted)   │         ↓                                       │
                  │  content-reviewer agent  →  agent_review         │
  Editor (You)    │         ↓                                       │
                  │  You approve / reject via admin API              │
                  │         ↓                                       │
                  │  raw_posts (draft)  →  you publish  →  LIVE      │
                  └──────────────────────────────────────────────────┘
                  │           HUMAN IN THE LOOP AT EVERY GATE        │
                  └──────────────────────────────────────────────────┘
```

## Why This Exists

Berlin has a dense, fast-moving landscape of protests, assemblies, and grassroots publications — but they're scattered across police bulletins, Telegram channels, Instagram stories, and word of mouth. Uncolonised centralises them into a single, searchable, bilingual (DE/EN) source, with editorial curation that ensures nothing goes live without a human reading it first.

AI agents assist — summarising, tagging, reviewing tone — but they never publish. That decision stays with you.

## Core Principles

- **No public writes.** Every POST, PUT, and DELETE requires an API key. Readers browse freely.
- **Human-in-the-loop.** AI suggests. You decide. Agents assist with research and review but never auto-publish.
- **Curated contributors.** Only whitelisted Telegram users can submit articles. No open registration, no spam.
- **Bilingual search.** Full-text search in German and English, with automatic English→German term translation at query time.
- **Works offline-first.** Everything runs on your machine with `docker compose up`. No SaaS dependencies.

## Architecture

```
 scrape ──────────────────────────────────────────────────────────┐
  Police API, RSS feeds, Telegram bot                              │
    ↓                                                              │
  ┌─────────────────────┐                                          │
  │  BRONZE (raw data)  │  raw_assemblies, raw_posts, submissions   │
  └─────────┬───────────┘                                          │
            │ dbt run                                               │
  ┌─────────────────────┐                                          │
  │  SILVER (cleaned)   │  stg_posts, int_posts                    │
  └─────────┬───────────┘                                          │
            │ dbt run                                               │
  ┌─────────────────────┐                                          │
  │  GOLD (API-ready)   │  mart_posts_api, mart_events_api         │
  └─────────┬───────────┘                                          │
            │ asyncpg                                               │
  ┌─────────────────────┐                                          │
  │  FastAPI            │  public read + admin (auth required)     │
  └─────────────────────┘                                          │
            │                                                       │
  ┌─────────────────────┐                                          │
  │  Internal Dashboard │  GitHub Pages (ui/index.html)            │
  └─────────────────────┘                                          │
```

All writes go through the admin API, which checks `Authorization: Bearer <ADMIN_API_KEY>` on every request.

## Tech Stack

| Layer | Choice | Why |
|---|---|---|
| **API** | FastAPI + asyncpg + Pydantic v2 | Async, typed, auto-docs at `/docs` |
| **Database** | PostgreSQL 16 | GIN-indexed full-text search across two languages |
| **Transforms** | dbt-core 1.8 (Postgres) | Bronze → Silver → Gold with testable models |
| **Scrapers** | Python 3.12 + httpx | Async HTTP for multi-source aggregation |
| **Bot** | python-telegram-bot 21.x | Curated intake from whitelisted contributors |
| **AI** | Ollama (local) or OpenAI | Tagging, summarisation, tone review |
| **Orchestration** | Monomind swarm | 4 agents: project-manager, editor, content-reviewer, builder |
| **Dashboard** | Static HTML (monomind template) | GitHub Pages, OKLCH colours, dark theme |
| **Containers** | Docker Compose | 5 services: db, api, pipeline, bot, dashboard |

## Quick Start

```bash
# 1. Database
createdb uncolonised
psql uncolonised -f scripts/init_db.sql

# 2. Python environment
python -m venv .venv && source .venv/bin/activate
pip install -r api/requirements.txt

# 3. Run dbt transforms
cd dbt_project && dbt run --profiles-dir .

# 4. Start the API
uvicorn api.main:app --reload   # → http://localhost:8000

# Or everything at once:
docker compose up
```

API docs are at `http://localhost:8000/docs` (Swagger UI).

## API Reference

Every endpoint is documented in Swagger, but here's the high-level map.

### Public — no auth required

| Method | Endpoint | Returns |
|---|---|---|
| GET | `/health` | `{"status": "ok"}` |
| GET | `/events` | Filtered event list (date, district, tag, search) |
| GET | `/events/{id}` | Single event with full details |
| GET | `/posts` | Published blog posts (paginated) |
| GET | `/posts/{id}` | Single published post with body |
| GET | `/search?q=...` | Unified search across events + posts (EN/DE) |
| GET | `/tags` | All tags with counts |
| GET | `/districts` | All districts with counts |

### Admin — requires `Authorization: Bearer <ADMIN_API_KEY>`

| Method | Endpoint | What it does |
|---|---|---|
| GET | `/admin/stats` | Dashboard stats (total posts, submissions, events) |
| GET | `/admin/submissions` | List submissions (filter by status) |
| POST | `/admin/submissions` | Create a submission (internal / bot use) |
| POST | `/admin/submissions/{id}/approve` | Approve → creates a draft post |
| POST | `/admin/submissions/{id}/reject` | Reject with a reason |
| POST | `/admin/submissions/{id}/agent-review` | Run content-reviewer agent on submission |
| GET | `/admin/posts` | List all posts, including drafts |
| POST | `/admin/posts/{id}/publish` | Publish a draft → live on site |
| POST | `/admin/posts/{id}/unpublish` | Pull a post from the live site |
| POST | `/admin/ai/suggest-tags` | AI generates tags for given text |
| POST | `/admin/ai/summarize` | AI summarises given text |

## Content Pipeline — End to End

### For Contributors (invite-only)

1. You receive a link to the Telegram bot and your user ID is whitelisted.
2. Send your article as a Markdown message. First line = title, the rest = body.
3. The bot stores it in `submissions` with `status = 'pending'`.
4. You wait. The editor reviews and either publishes or rejects your piece.

### For the Editor (you)

1. Check the queue at `GET /admin/submissions?status=pending`.
2. Optionally trigger an agent review: the content-reviewer agent analyses tone, suggests tags, and drafts a summary. Results are stored in `submissions.agent_notes`.
3. You read the submission and the agent's notes. Then you decide:
   - **Approve** → creates a draft post in `raw_posts`
   - **Reject** → submission is archived with your reason
4. Review the draft at `GET /admin/posts?status=draft`. Optionally edit the body directly in the database.
5. **Publish** → `POST /admin/posts/{id}/publish` → post goes live on the public API immediately.

### For the Public (readers)

1. Browse events and published posts at `GET /events` and `GET /posts`.
2. Search across everything at `GET /search?q=climate+housing`.
3. No login, no registration, no ads. It's a free resource for the movement.

## Swarm Agents

Uncolonised uses Monomind to orchestrate four specialised agents. They coordinate through a shared memory namespace (`uncolonised`).

| Agent | Role | What it does |
|---|---|---|
| **project-manager** | Coordinator | Maintains roadmap, breaks work into sprints, delegates to other agents |
| **editor** | Researcher | Monitors editorial calendar, suggests topics, researches Berlin movements |
| **content-reviewer** | Reviewer | Reads submissions, checks anti-colonial tone, suggests tags and edits |
| **builder** | Developer | Implements scrapers, dbt models, API changes, Docker config |

**Agents never auto-publish.** The content-reviewer can flag issues and suggest edits, but the final publish call is always yours.

## Environment Variables

| Variable | Default | Required | Notes |
|---|---|---|---|
| `DATABASE_URL` | `postgresql://berlin:berlin@db:5432/uncolonised` | Yes | Internal database (name stays `uncolonised`) |
| `ADMIN_API_KEY` | `changeme` | Yes | **Change this in production.** Sent as Bearer token. |
| `AI_PROVIDER` | `none` | No | `none` (off), `ollama`, or `openai` |
| `AI_MODEL` | `gemma3:12b` | No | Ollama model name |
| `TELEGRAM_BOT_TOKEN` | — | Yes (for bot) | From @BotFather |
| `ALLOWED_USER_IDS` | — | Yes (for bot) | Comma-separated Telegram user IDs |
| `ALLOWED_ORIGINS` | `*` | No | CORS origins for the API |

## Project Structure

```
uncolonised/
├── api/                 FastAPI app — main.py, Dockerfile, requirements.txt
├── bot/                 Telegram bot — bot.py, Dockerfile, requirements.txt
├── scraper/             Multi-source scrapers — run_all.py, sources/*.py
├── dbt_project/         dbt transformations — models/, seeds/, profiles.yml
├── scripts/             DB init SQL, data pipeline runner
├── ui/                  Internal dashboard (static HTML, deployed to Pages)
├── docker-compose.yml   5 services: db, api, pipeline, bot, dashboard
├── CLAUDE.md            Agent configuration for Monomind
├── .env                 Environment variables (gitignored)
```

## Development Commands

```bash
# Run scrapers
python -m scraper.run_all

# Start the API
uvicorn api.main:app --reload

# Run dbt transforms + tests
cd dbt_project && dbt run --profiles-dir . && dbt test --profiles-dir .

# Full stack
docker compose up

# Telegram bot (standalone)
python bot/bot.py

# Internal dashboard
open http://localhost:8080          # if running via Docker
open ui/index.html                  # directly in a browser

# Monomind swarm
monomind memory search --query "vision" --namespace uncolonised
monomind agent list
monomind swarm status
```

## Security

- **No public write endpoints.** You cannot POST, PUT, or DELETE without an API key.
- **API key auth.** Every admin endpoint checks `Authorization: Bearer <ADMIN_API_KEY>`. Default is `changeme` — change it.
- **Telegram whitelist.** Only user IDs in `ALLOWED_USER_IDS` can use the bot. No open registration.
- **Agent review is advisory.** The content-reviewer agent suggests — you decide. Agents never auto-publish.
- **Audit trail.** Every agent action and admin decision is logged in `review_log`.

## Deployment

### Docker Compose (recommended)

```bash
cp .env.example .env    # set your secrets
docker compose up -d    # starts all 5 services
```

Services:
- **db** — PostgreSQL 16
- **api** — FastAPI on `:8000`
- **pipeline** — dbt runner (runs transforms on startup)
- **bot** — Telegram bot
- **dashboard** — nginx serving the internal dashboard

### GitHub Pages

The internal dashboard is deployed to GitHub Pages automatically when changes are pushed to `ui/` or the workflow file. The workflow is at `.github/workflows/pages.yml`.

## License

Anti-colonial. Anti-imperialist. For the movement, by the movement.
