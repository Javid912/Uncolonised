import json
import os
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Any, Optional

import asyncpg
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pydantic_settings import BaseSettings


# ── Settings ───────────────────────────────────────────────────
class Settings(BaseSettings):
    database_url: str
    allowed_origins: str = "*"
    ai_provider: str = "none"
    ai_model: str = "gemma3:12b"
    ai_endpoint: str = "http://localhost:11434/v1/chat/completions"
    ai_api_key: str = "ollama"

    class Config:
        env_file = ".env"


settings = Settings()
pool: asyncpg.Pool = None


# ── Pydantic models ────────────────────────────────────────────
class EventSummary(BaseModel):
    event_id: int
    source_id: int
    event_date: date
    time_start: Optional[str]
    time_end: Optional[str]
    postcode: Optional[str]
    district_name: Optional[str]
    street_address: Optional[str]
    title: Optional[str]
    event_type: str
    has_route: bool
    is_recurring: bool
    tags: list[Any]


class EventDetail(EventSummary):
    description: Optional[str]
    route_text: Optional[str]
    recurrence_note: Optional[str]


class PostSummary(BaseModel):
    post_id: int
    title: str
    excerpt: Optional[str]
    author_name: str
    slug: str
    published_at: Optional[datetime]
    tags: list[str]


class PostDetail(PostSummary):
    body_md: str
    created_at: datetime
    updated_at: datetime


class PostCreate(BaseModel):
    title: str
    body_md: str
    author_name: str
    slug: str
    excerpt: Optional[str] = None
    tags: list[str] = []


class SubmissionCreate(BaseModel):
    submission_type: str
    title: str
    description: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    event_date: Optional[date] = None
    event_location: Optional[str] = None
    tags: list[str] = []


class TagSummary(BaseModel):
    slug: str
    label_de: str
    label_en: str
    event_count: int


class SearchResult(BaseModel):
    type: str
    id: int
    title: Optional[str]
    excerpt: Optional[str]
    date: Optional[str]
    tags: Any
    rank: float


class AITagRequest(BaseModel):
    text: str


class AITagResponse(BaseModel):
    tags: list[str]
    summary: Optional[str]


# ── Helpers ────────────────────────────────────────────────────
def row_to_dict(row) -> dict:
    d = dict(row)
    if d.get("time_start") is not None:
        d["time_start"] = str(d["time_start"])
    if d.get("time_end") is not None:
        d["time_end"] = str(d["time_end"])
    if isinstance(d.get("tags"), str):
        d["tags"] = json.loads(d["tags"])
    return d


async def translate_query(q: str) -> str:
    words = q.strip().split()
    if not words:
        return q
    async with pool.acquire() as conn:
        translations = await conn.fetch(
            """
            SELECT en_term, de_term
            FROM search_translations
            WHERE lower(en_term) = ANY($1::text[])
            """,
            [w.lower() for w in words],
        )
    translation_map = {row["en_term"].lower(): row["de_term"] for row in translations}
    expanded = []
    for word in words:
        expanded.append(word)
        de = translation_map.get(word.lower())
        if de:
            expanded.append(de)
    return " ".join(expanded)


async def ai_tag(text: str) -> AITagResponse:
    if settings.ai_provider == "none":
        return AITagResponse(
            tags=[], summary=None
        )
    try:
        import httpx

        prompt = f"""You are an AI curator for an anti-colonial/anti-imperialist events platform.
Read the following text and:
1. Suggest up to 5 relevant tags (lowercase, single words or compound terms like "palestine", "climate-justice", "antifascism")
2. Write a one-sentence summary in English

Text:
{text[:2000]}

Respond ONLY with JSON: {{"tags": [...], "summary": "..."}}"""

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                settings.ai_endpoint,
                headers={
                    "Authorization": f"Bearer {settings.ai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.ai_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 200,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]

        # Extract JSON from response
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("\n", 1)[0]
        result = json.loads(content)
        return AITagResponse(
            tags=result.get("tags", []),
            summary=result.get("summary"),
        )
    except Exception as e:
        return AITagResponse(tags=[], summary=None)


# ── App lifecycle ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    pool = await asyncpg.create_pool(settings.database_url, min_size=2, max_size=10)
    yield
    await pool.close()


app = FastAPI(
    title="Uncolonised API",
    description="Anti-colonial / anti-imperialist events & blog platform for Berlin",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ─────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "project": "Uncolonised"}


# ── Events ─────────────────────────────────────────────────────
@app.get("/events", response_model=list[EventSummary])
async def list_events(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    district: Optional[str] = Query(None),
    postcode: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    has_route: Optional[bool] = Query(None),
    q: Optional[str] = Query(None, description="Search (German or English)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    upcoming: bool = Query(True),
):
    conditions = []
    params = []
    i = 1

    if upcoming:
        conditions.append("event_date >= CURRENT_DATE")
    if date_from:
        conditions.append(f"event_date >= ${i}")
        params.append(date_from)
        i += 1
    if date_to:
        conditions.append(f"event_date <= ${i}")
        params.append(date_to)
        i += 1
    if district:
        conditions.append(f"district_name = ${i}")
        params.append(district)
        i += 1
    if postcode:
        conditions.append(f"postcode = ${i}")
        params.append(postcode)
        i += 1
    if event_type:
        conditions.append(f"event_type = ${i}")
        params.append(event_type)
        i += 1
    if has_route is not None:
        conditions.append(f"has_route = ${i}")
        params.append(has_route)
        i += 1
    if tag:
        conditions.append(f"tags @> ${i}::jsonb")
        params.append(json.dumps([{"slug": tag}]))
        i += 1

    if q:
        expanded_q = await translate_query(q)
        conditions.append(
            f"search_vector @@ plainto_tsquery('german_unaccent', ${i})"
        )
        params.append(expanded_q)
        i += 1

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    if q:
        expanded_q_rank = await translate_query(q)
        order = f"""
            ORDER BY
                ts_rank(search_vector, plainto_tsquery('german_unaccent', ${i})) DESC,
                event_date ASC,
                time_start ASC NULLS LAST
        """
        params.append(expanded_q_rank)
        i += 1
    else:
        order = "ORDER BY event_date ASC, time_start ASC NULLS LAST"

    sql = f"""
        SELECT event_id, source_id, event_date, time_start, time_end,
               postcode, district_name, street_address,
               title, event_type, has_route, is_recurring, tags
        FROM mart_events_api
        {where}
        {order}
        LIMIT ${i} OFFSET ${i+1}
    """
    params.extend([limit, offset])

    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *params)
    return [row_to_dict(r) for r in rows]


@app.get("/events/{event_id}", response_model=EventDetail)
async def get_event(event_id: int):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM mart_events_api WHERE event_id = $1", event_id
        )
    if not row:
        raise HTTPException(status_code=404, detail="Event not found")
    return row_to_dict(row)


# ── Posts ──────────────────────────────────────────────────────
@app.get("/posts", response_model=list[PostSummary])
async def list_posts(
    tag: Optional[str] = Query(None),
    author: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="Full-text search"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    conditions = []
    params = []
    i = 1

    if tag:
        conditions.append(f"$${i} = ANY(tags)")
        params.append(tag)
        i += 1
    if author:
        conditions.append(f"author_name = $${i}")
        params.append(author)
        i += 1
    if q:
        expanded_q = await translate_query(q)
        conditions.append(
            f"search_vector @@ plainto_tsquery('german_unaccent', $${i})"
        )
        params.append(expanded_q)
        i += 1

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    if q:
        expanded_q_rank = await translate_query(q)
        order = f"""
            ORDER BY
                ts_rank(search_vector, plainto_tsquery('german_unaccent', $${i})) DESC,
                published_at DESC NULLS LAST
        """
        params.append(expanded_q_rank)
        i += 1
    else:
        order = "ORDER BY published_at DESC NULLS LAST"

    sql = f"""
        SELECT post_id, title, excerpt, author_name, slug,
               published_at, tags
        FROM mart_posts_api
        {where}
        {order}
        LIMIT $${i} OFFSET $${i+1}
    """
    params.extend([limit, offset])

    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *params)
    return [dict(r) for r in rows]


@app.get("/posts/{post_id}", response_model=PostDetail)
async def get_post(post_id: int):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT post_id, title, body_md, excerpt, author_name,
                   slug, published_at, tags, created_at, updated_at
            FROM mart_posts_api
            WHERE post_id = $1
            """,
            post_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Post not found")
    return dict(row)


@app.post("/posts", response_model=PostDetail, status_code=201)
async def create_post(post: PostCreate):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO raw_posts (title, body_md, excerpt, author_name, slug, tags, published, published_at)
            VALUES ($1, $2, $3, $4, $5, $6, true, now())
            RETURNING id, title, body_md, excerpt, author_name, slug, published_at, tags, created_at, updated_at
            """,
            post.title,
            post.body_md,
            post.excerpt or post.body_md[:200],
            post.author_name,
            post.slug,
            post.tags,
        )
    return dict(row)


# ── Submissions ────────────────────────────────────────────────
@app.post("/submit", status_code=201)
async def submit(submission: SubmissionCreate):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO submissions (submission_type, title, description, contact_name, contact_email, event_date, event_location, tags)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id, submission_type, title, status, created_at
            """,
            submission.submission_type,
            submission.title,
            submission.description,
            submission.contact_name,
            submission.contact_email,
            submission.event_date,
            submission.event_location,
            submission.tags,
        )
    return dict(row)


# ── Unified search ─────────────────────────────────────────────
@app.get("/search", response_model=list[SearchResult])
async def unified_search(
    q: str = Query(..., description="Search query"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    expanded_q = await translate_query(q)

    sql = f"""
        SELECT 'event' as type, event_id as id, title,
               description as excerpt,
               (event_date || ' ' || time_start)::text as date,
               tags, ts_rank(search_vector, plainto_tsquery('german_unaccent', $1)) as rank
        FROM mart_events_api
        WHERE search_vector @@ plainto_tsquery('german_unaccent', $1)
        UNION ALL
        SELECT 'post' as type, post_id as id, title,
               excerpt,
               published_at::text as date,
               to_jsonb(tags) as tags,
               ts_rank(search_vector, plainto_tsquery('german_unaccent', $1)) as rank
        FROM mart_posts_api
        WHERE search_vector @@ plainto_tsquery('german_unaccent', $1)
        ORDER BY rank DESC, date ASC NULLS LAST
        LIMIT $2 OFFSET $3
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, expanded_q, limit, offset)
    results = []
    for r in rows:
        d = dict(r)
        if isinstance(d.get("tags"), str):
            d["tags"] = json.loads(d["tags"])
        results.append(SearchResult(**d))
    return results


# ── Tags ───────────────────────────────────────────────────────
@app.get("/tags", response_model=list[TagSummary])
async def list_tags():
    sql = """
        SELECT t.slug, t.label_de, t.label_en, COUNT(*) as event_count
        FROM bridge_event_tags t
        JOIN mart_events_api e ON e.event_id = t.event_id
        WHERE e.event_date >= CURRENT_DATE
        GROUP BY t.slug, t.label_de, t.label_en
        ORDER BY event_count DESC
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql)
    return [dict(r) for r in rows]


# ── Districts ──────────────────────────────────────────────────
@app.get("/districts")
async def list_districts():
    sql = """
        SELECT district_name, COUNT(*) as event_count
        FROM mart_events_api
        WHERE event_date >= CURRENT_DATE
          AND district_name IS NOT NULL
          AND district_name <> 'Unknown'
        GROUP BY district_name
        ORDER BY event_count DESC
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql)
    return [dict(r) for r in rows]


# ── AI Director ────────────────────────────────────────────────
@app.post("/ai/suggest-tags", response_model=AITagResponse)
async def suggest_tags(request: AITagRequest):
    return await ai_tag(request.text)


@app.post("/ai/summarize")
async def summarize(request: AITagRequest):
    result = await ai_tag(request.text)
    if result.summary:
        return {"summary": result.summary}
    return {"summary": None}
