# Uncolonised — Monomind Configuration

## Project Overview

Uncolonised is a curated digital magazine and event platform for anti-colonial, anti-imperialist movements in Berlin. Multi-source event aggregation, blog posts (curated submission pipeline), AI director, bilingual full-text search. **No public write endpoints** — all admin operations require API key authentication.

## Swarm Agents

| Agent | Type | Role |
|-------|------|------|
| project-manager | coordinator | Roadmap, sprint planning, task orchestration |
| editor | researcher | Editorial strategy, topic research, content calendar |
| content-reviewer | reviewer | Quality checks, moderation, anti-colonial lens, tone, submission review |
| builder | coder | Implements scrapers, dbt models, API endpoints, Docker |

## Memory Namespace: `uncolonised`

- `project-vision` — overall vision and tech stack
- `team-roles` — agent responsibilities
- `data-model` — bronze/silver/gold medallion schema
- `api-endpoints` — all available REST endpoints (public vs admin)
- `security-policy` — auth requirements, no open endpoints

## Key Patterns

### Data Flow
```
scrapers → raw_* (bronze) → dbt (silver) → mart_* (gold) → FastAPI (public read)
Telegram bot → submissions (bronze) → admin approval → raw_posts (draft) → publish → mart_posts_api
```

### Content Pipeline (Curated)
```
Contributor (Telegram) → submissions (pending) → content-reviewer agent (agent_review)
→ you approve/reject via admin API → raw_posts (draft) → you publish → live on site
```

### Security Rules
- **All public write endpoints are removed.** No `POST /posts`, no `POST /submit`.
- Admin endpoints require `Authorization: Bearer <ADMIN_API_KEY>` header.
- API key is set via `ADMIN_API_KEY` env var (default: `changeme` in dev).
- Telegram bot uses a whitelist of user IDs (`ALLOWED_USER_IDS`).
- The `content-reviewer` agent assists but does not auto-publish.

### Adding a Scraper
1. Create `scraper/sources/your_source.py` extending `BaseScraper`
2. Register in `scraper/run_all.py` `SOURCES` list
3. Create a raw table in `scripts/init_db.sql`

### Blog Post Lifecycle
1. Contributor sends article via Telegram bot → `submissions.status = 'pending'`
2. Admin triggers agent review → `submissions.status = 'agent_review'`
3. Admin approves → creates `raw_posts` row with `status = 'draft'`
4. Admin publishes → `raw_posts.status = 'published'`

### AI Director
Set `AI_PROVIDER=ollama` or `openai` in `.env`. Admin-only endpoints: `/admin/ai/suggest-tags`, `/admin/ai/summarize`.

### Unified Search
`GET /search?q=climate+housing` — searches events and published posts, ranked by ts_rank, bilingual (English terms auto-translated to German).

## Build & Test Commands

```bash
# Run scrapers
python -m scraper.run_all

# Start API
uvicorn api.main:app --reload

# dbt
cd dbt_project && dbt run --profiles-dir . && dbt test --profiles-dir .

# Docker
docker compose up

# Memory
monomind memory search --query "vision" --namespace uncolonised
monomind memory store --key "key" --value "data" --namespace uncolonised --tags "tag1,tag2"

# Agents
monomind agent list
monomind agent spawn -t <type> --name <name>

# Swarm
monomind swarm status
```

## Rules

- Always store project decisions in monomind memory under `uncolonised` namespace
- Use monograph before grep for code navigation
- Never commit .monomind/ to git (it's in .gitignore)
- Keep agents focused on their role
- **Never expose write endpoints without API key auth**
- Submission pipeline: Telegram → agent review → you approve → publish
