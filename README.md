# Uncolonised

A collectively written digital magazine and event platform for anti-colonial, anti-imperialist movements in Berlin. Aggregates demos, protests, and content from multiple sources — with powerful search, community submissions, AI-driven curation, and a shared blog written by a group of young people.

## Architecture

```
Multiple sources (Police API, RSS feeds, grassroots calendars, etc.)
    |  scrapers run daily
raw_events + raw_posts tables  (Bronze — raw, no transformation)
    |  dbt run
stg → int → fct  (Silver — cleaned, enriched, search vectors)
    |  dbt run
mart_events_api  +  mart_posts_api  (Gold — indexed, joined, API-ready)
    |  asyncpg
FastAPI  —  /events  /posts  /search  /submit  /ai/*
```

## Tech Stack

- **Scrapers**: Python 3.12, httpx
- **Database**: PostgreSQL 16 with full-text search (custom unaccent configs)
- **Transformations**: dbt-core 1.8 (Postgres adapter)
- **API**: FastAPI + asyncpg + Pydantic v2
- **AI Director**: LLM-based (Ollama / OpenAI) — auto-tagging, summarization, moderation
- **Containerization**: Docker + docker-compose

## Setup

```bash
createdb berlin_demos
psql berlin_demos -f scripts/init_db.sql
python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
cd dbt_project && dbt seed --profiles-dir . && dbt run --profiles-dir .
```

## Running

```bash
# All scrapers
python scraper/run_all.py

# Start the API
uvicorn api.main:app --reload

# Full pipeline (Docker)
docker compose up
```

## API

| Endpoint | Description |
|---|---|
| `GET /health` | Health check |
| `GET /events` | List/filter events (date, district, tag, full-text search, source) |
| `GET /events/{id}` | Single event detail |
| `GET /posts` | List blog posts (tag, author, search) |
| `GET /posts/{id}` | Single post |
| `POST /posts` | Publish a post (open, no auth) |
| `POST /submit` | Submit an event or article idea (moderation queue) |
| `GET /search` | Unified search across events + posts |
| `GET /tags` | List all tags with counts |
| `GET /districts` | List all districts with event counts |
| `POST /ai/suggest-tags` | AI auto-tag text |
| `POST /ai/summarize` | AI summarize an event or post |
