# Uncolonised

**An agentic-driven journal with a human in the loop.**

A curated digital magazine and event platform for anti-colonial, anti-imperialist movements in Berlin. Aggregates protests, publishes articles, and indexes resistance — powered by swarm agents, secured with API key auth, and curated through a human审核 pipeline.

```
                    ┌─────────────────────────────────────────────┐
                    │         AGENTIC JOURNAL PIPELINE           │
                    ├─────────────────────────────────────────────┤
  Contributor       │  Telegram Bot → submissions (pending)       │
  (via Telegram)    │       ↓                                    │
                    │  content-reviewer agent → agent_review      │
                    │       ↓                                    │
  You (editor)      │  You approve/reject via admin API            │
                    │       ↓                                    │
                    │  raw_posts (draft) → you publish → LIVE     │
                    └─────────────────────────────────────────────┘
                    │        HUMAN IN THE LOOP AT EVERY GATE      │
                    └─────────────────────────────────────────────┘
```

## Core Principles

- **No public write endpoints.** All content is curated.
- **Agentic but human-controlled.** AI agents assist with review, tagging, and summarization — you make the final call.
- **Curated contributors only.** Approved members submit via Telegram. No open registration.
- **Bilingual by default.** Full-text search in German and English with automatic translation.
- **Everything in Docker.** Single `docker compose up` to run the full stack.

## Architecture

```
Sources (Police API, Telegram Bot, RSS)
    │  scrapers run daily
raw_assemblies + raw_posts + submissions  (Bronze)
    │  dbt run
stg → int → fct  (Silver — cleaned, enriched, search vectors)
    │  dbt run
mart_events_api + mart_posts_api  (Gold — indexed, API-ready)
    │  asyncpg
FastAPI  —  public read (events, posts, search)  +  admin (auth required)
```

## Tech Stack

| Component | Technology | Purpose |
|---|---|---|
| **API** | FastAPI + asyncpg + Pydantic v2 | REST framework with API key auth |
| **Database** | PostgreSQL 16 | Primary store with GIN-indexed FTS |
| **Pipeline** | dbt-core 1.8 (Postgres) | Bronze → Silver → Gold transformations |
| **Scrapers** | Python 3.12 + httpx | Multi-source event aggregation |
| **Bot** | python-telegram-bot 21.x | Curated submission intake |
| **AI Director** | Ollama / OpenAI | Auto-tagging, summarization, review |
| **Agents** | Monomind swarm | project-manager, editor, content-reviewer, builder |
| **UI** | nginx | Internal development dashboard |
| **Containers** | Docker + compose | 5 services: db, api, pipeline, bot, ui |

## Setup

```bash
# Create database
createdb berlin_demos
psql berlin_demos -f scripts/init_db.sql

# Install dependencies
python -m venv .venv && source .venv/bin/activate
pip install -r api/requirements.txt

# Run dbt
cd dbt_project && dbt seed --profiles-dir . && dbt run --profiles-dir .

# Run scrapers
python -m scraper.run_all

# Start API
uvicorn api.main:app --reload

# Full stack (Docker)
docker compose up
```

## API Reference

### Public Endpoints (no auth required)

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/events` | List/filter events (date, district, tag, FTS) |
| GET | `/events/{id}` | Single event detail |
| GET | `/posts` | List published blog posts |
| GET | `/posts/{id}` | Single published post with body |
| GET | `/search` | Unified search across events + published posts |
| GET | `/tags` | All tags with event counts |
| GET | `/districts` | All districts with event counts |

### Admin Endpoints (require `Authorization: Bearer <ADMIN_API_KEY>`)

| Method | Endpoint | Description |
|---|---|---|
| GET | `/admin/stats` | Dashboard statistics |
| GET | `/admin/submissions` | List submissions (filterable by status) |
| POST | `/admin/submissions` | Create a submission (bot/internal use) |
| POST | `/admin/submissions/{id}/approve` | Approve → creates draft post |
| POST | `/admin/submissions/{id}/reject` | Reject with reason |
| POST | `/admin/submissions/{id}/agent-review` | Trigger content-reviewer agent |
| GET | `/admin/posts` | List all posts including drafts |
| POST | `/admin/posts/{id}/publish` | Publish a draft post |
| POST | `/admin/posts/{id}/unpublish` | Unpublish a post |
| POST | `/admin/ai/suggest-tags` | AI auto-tag text |
| POST | `/admin/ai/summarize` | AI summarize text |

## Content Pipeline (Detailed)

### For Contributors
1. You're invited personally and given access to the Telegram bot
2. Send your article as a Markdown message (first line = title, rest = body)
3. Bot stores it in `submissions` table with `status = 'pending'`

### For the Editor (You)
4. Trigger agent review via admin API → `content-reviewer` agent suggests tags + summary
5. Review the submission → approve (creates draft post) or reject (with reason)
6. Publish the draft post → goes live immediately

### For the Public
7. Browse published posts via `GET /posts`
8. Search across events and posts via `GET /search?q=...`
9. No login, no accounts, no registration required

## Security

- **No public write endpoints.** All POST/PUT/DELETE require admin API key.
- **API key auth.** Set via `ADMIN_API_KEY` env var (default: `changeme` in dev).
- **Telegram whitelist.** Only approved user IDs can submit (`ALLOWED_USER_IDS` env var).
- **Agent review is advisory.** AI suggests tags and summaries — you approve or reject.
- **Full audit trail.** Every agent action logged in `review_log` table.

## Swarm Agents

| Agent | Type | Role |
|---|---|---|
| **project-manager** | coordinator | Roadmap, sprint planning, task orchestration |
| **editor** | researcher | Editorial strategy, topic research, content calendar |
| **content-reviewer** | reviewer | Quality checks, moderation, anti-colonial lens, tone |
| **builder** | coder | Implements scrapers, dbt models, API endpoints, Docker |

Memory namespace: `uncolonised` — stores vision, team-roles, data-model, api-endpoints, security-policy.

## Running

```bash
# Start everything
docker compose up

# Individual services
uvicorn api.main:app --reload           # API on :8000
python -m scraper.run_all               # Run scrapers
python bot/bot.py                       # Telegram bot

# dbt
cd dbt_project && dbt run --profiles-dir . && dbt test --profiles-dir .

# Internal dashboard
open http://localhost:8080              # nginx serving ui/index.html

# Monomind
monomind memory search --query "vision" --namespace uncolonised
monomind agent list
monomind swarm status
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://berlin:berlin@db:5432/berlin_demos` | PostgreSQL connection |
| `ADMIN_API_KEY` | `changeme` | API key for admin endpoints |
| `AI_PROVIDER` | `none` | AI backend: `none`, `ollama`, or `openai` |
| `AI_MODEL` | `gemma3:12b` | Model name for Ollama |
| `TELEGRAM_BOT_TOKEN` | — | Bot token from @BotFather |
| `ALLOWED_USER_IDS` | — | Comma-separated Telegram user IDs (whitelist) |
| `ALLOWED_ORIGINS` | `*` | CORS origins |

## Project Structure

```
api/              FastAPI app (main.py, requirements.txt, Dockerfile)
bot/              Telegram bot (bot.py, requirements.txt, Dockerfile)
scraper/          Multi-source scrapers (run_all.py, sources/*.py)
dbt_project/      dbt transformations (models/, seeds/, profiles.yml)
scripts/          Database init, cron scripts, pipeline runner
ui/               Internal development dashboard (index.html)
docker-compose.yml  5-service stack
CLAUDE.md         Monomind agent configuration
```
