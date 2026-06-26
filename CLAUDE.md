# Uncolonised — Monomind Configuration

## Project Overview

Uncolonised is a collectively written digital magazine and event platform for anti-colonial, anti-imperialist movements in Berlin. Multi-source event aggregation, blog posts, community submissions, AI curation, bilingual full-text search.

## Swarm Agents

| Agent | Type | Role |
|-------|------|------|
| project-manager | coordinator | Roadmap, sprint planning, task orchestration |
| editor | researcher | Editorial strategy, topic research, content calendar |
| content-reviewer | reviewer | Quality checks, moderation, anti-colonial lens, tone |
| builder | coder | Implements scrapers, dbt models, API endpoints, Docker |

## Memory Namespace: `uncolonised`

- `project-vision` — overall vision and tech stack
- `team-roles` — agent responsibilities
- `data-model` — bronze/silver/gold medallion schema
- `api-endpoints` — all available REST endpoints

## Key Patterns

### Data Flow
```
scrapers → raw_* (bronze) → dbt (silver) → mart_* (gold) → FastAPI
```

### Adding a Scraper
1. Create `scraper/sources/your_source.py` extending `BaseScraper`
2. Register in `scraper/run_all.py` `SOURCES` list
3. Create a raw table in `scripts/init_db.sql`

### Adding a Blog Post
`POST /posts` with title, body_md, author_name, slug, tags — no auth.

### Submissions
`POST /submit` — lands in `submissions` table with `status = 'pending'`.

### AI Director
Set `AI_PROVIDER=ollama` (default, local) or `openai` in `.env`. Endpoints: `/ai/suggest-tags`, `/ai/summarize`.

### Unified Search
`GET /search?q=climate+housing` — searches both events and posts, ranked by ts_rank, bilingual (English terms auto-translated to German).

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
- Keep agents focused on their role: project-manager directs, editor researches, content-reviewer polishes, builder codes
