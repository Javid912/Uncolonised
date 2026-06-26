import hashlib
import json
import os
import secrets
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Any, Optional

import asyncpg
from fastapi import FastAPI, HTTPException, Query, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from pydantic_settings import BaseSettings


# ── Settings ───────────────────────────────────────────────────
class Settings(BaseSettings):
    database_url: str
    allowed_origins: str = "*"
    admin_api_key: str = ""
    ai_provider: str = "none"
    ai_model: str = "gemma3:12b"
    ai_endpoint: str = "http://localhost:11434/v1/chat/completions"
    ai_api_key: str = "ollama"

    class Config:
        env_file = ".env"


settings = Settings()
pool: asyncpg.Pool = None
security = HTTPBearer(auto_error=False)


# ── Auth ───────────────────────────────────────────────────────
async def verify_admin_key(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    x_api_key: Optional[str] = Header(None),
):
    provided = ""
    if credentials:
        provided = credentials.credentials
    elif x_api_key:
        provided = x_api_key

    if not provided or not settings.admin_api_key:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not secrets.compare_digest(provided, settings.admin_api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    return provided


# ── Pydantic models (public read) ──────────────────────────────
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


# ── Pydantic models (admin) ────────────────────────────────────
class SubmissionOut(BaseModel):
    id: int
    created_at: datetime
    submission_type: str
    title: str
    body_md: Optional[str]
    description: Optional[str]
    author_name: Optional[str]
    contact_name: Optional[str]
    contact_email: Optional[str]
    telegram_uid: Optional[int]
    telegram_username: Optional[str]
    tags: list[str]
    status: str
    agent_notes: Optional[str]
    admin_notes: Optional[str]


class AdminPostOut(BaseModel):
    id: int
    created_at: datetime
    title: str
    body_md: str
    excerpt: Optional[str]
    author_name: str
    slug: str
    status: str
    published_at: Optional[datetime]
    tags: list[str]
    submission_id: Optional[int]
    editor_notes: Optional[str]


class DashboardStats(BaseModel):
    total_events: int
    upcoming_events: int
    total_posts: int
    published_posts: int
    pending_submissions: int
    total_scrapers: int
    api_status: str


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
        return AITagResponse(tags=[], summary=None)
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

        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("\n", 1)[0]
        result = json.loads(content)
        return AITagResponse(
            tags=result.get("tags", []),
            summary=result.get("summary"),
        )
    except Exception:
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
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════
# PUBLIC READ ENDPOINTS (no auth required)
# ═══════════════════════════════════════════════════════════════

# ── Health ─────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "project": "Uncolonised", "version": "2.0.0"}


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


# ── Posts (published only — public) ────────────────────────────
@app.get("/posts", response_model=list[PostSummary])
async def list_posts(
    tag: Optional[str] = Query(None),
    author: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="Full-text search"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    conditions = ["status = 'published'"]
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

    where = "WHERE " + " AND ".join(conditions)

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
            WHERE post_id = $1 AND status = 'published'
            """,
            post_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Post not found")
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
          AND status = 'published'
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


# ═══════════════════════════════════════════════════════════════
# ADMIN ENDPOINTS (API key required)
# ═══════════════════════════════════════════════════════════════

# ── Dashboard stats ────────────────────────────────────────────
@app.get("/admin/stats", response_model=DashboardStats)
async def admin_stats(_=Depends(verify_admin_key)):
    async with pool.acquire() as conn:
        total_events = await conn.fetchval("SELECT COUNT(*) FROM mart_events_api")
        upcoming = await conn.fetchval(
            "SELECT COUNT(*) FROM mart_events_api WHERE event_date >= CURRENT_DATE"
        )
        total_posts = await conn.fetchval("SELECT COUNT(*) FROM raw_posts")
        published = await conn.fetchval(
            "SELECT COUNT(*) FROM raw_posts WHERE status = 'published'"
        )
        pending = await conn.fetchval(
            "SELECT COUNT(*) FROM submissions WHERE status = 'pending'"
        )
    return DashboardStats(
        total_events=total_events or 0,
        upcoming_events=upcoming or 0,
        total_posts=total_posts or 0,
        published_posts=published or 0,
        pending_submissions=pending or 0,
        total_scrapers=1,
        api_status="ok",
    )


# ── Submissions management ─────────────────────────────────────
@app.get("/admin/submissions", response_model=list[SubmissionOut])
async def list_submissions(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _=Depends(verify_admin_key),
):
    where = ""
    params = []
    if status:
        where = "WHERE status = $1"
        params.append(status)

    sql = f"""
        SELECT id, created_at, submission_type, title, body_md, description,
               author_name, contact_name, contact_email,
               telegram_uid, telegram_username,
               tags, status, agent_notes, admin_notes
        FROM submissions
        {where}
        ORDER BY created_at DESC
        LIMIT ${2 if status else 1} OFFSET ${3 if status else 2}
    """
    params.extend([limit, offset])

    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *params)
    results = []
    for r in rows:
        d = dict(r)
        if isinstance(d.get("tags"), str):
            d["tags"] = json.loads(d["tags"])
        results.append(SubmissionOut(**d))
    return results


@app.post("/admin/submissions", status_code=201)
async def create_submission(
    submission_type: str,
    title: str,
    body_md: Optional[str] = None,
    description: Optional[str] = None,
    author_name: Optional[str] = None,
    contact_name: Optional[str] = None,
    contact_email: Optional[str] = None,
    telegram_uid: Optional[int] = None,
    telegram_username: Optional[str] = None,
    tags: Optional[str] = None,
    _=Depends(verify_admin_key),
):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO submissions
                (submission_type, title, body_md, description, author_name,
                 contact_name, contact_email, telegram_uid, telegram_username, tags,
                 status)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, 'pending')
            RETURNING id, submission_type, title, status, created_at
            """,
            submission_type,
            title,
            body_md,
            description,
            author_name,
            contact_name,
            contact_email,
            telegram_uid,
            telegram_username,
            [t.strip() for t in tags.split(",")] if tags else [],
        )
    return dict(row)


@app.post("/admin/submissions/{submission_id}/approve", status_code=201)
async def approve_submission(
    submission_id: int,
    editor_notes: Optional[str] = None,
    _=Depends(verify_admin_key),
):
    async with pool.acquire() as conn:
        sub = await conn.fetchrow(
            "SELECT * FROM submissions WHERE id = $1", submission_id
        )
        if not sub:
            raise HTTPException(status_code=404, detail="Submission not found")
        if sub["status"] not in ("pending", "agent_review", "needs_revision"):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot approve submission in status '{sub['status']}'",
            )

        base_slug = sub["title"].lower().replace(" ", "-")[:80]
        base_slug = "".join(c for c in base_slug if c.isalnum() or c == "-") or "untitled"
        slug = base_slug

        collision = await conn.fetchval(
            "SELECT 1 FROM raw_posts WHERE slug = $1", slug
        )
        suffix = 2
        while collision:
            slug = f"{base_slug}-{suffix}"
            collision = await conn.fetchval(
                "SELECT 1 FROM raw_posts WHERE slug = $1", slug
            )
            suffix += 1

        post = await conn.fetchrow(
            """
            INSERT INTO raw_posts
                (title, body_md, excerpt, author_name, slug, tags,
                 status, submission_id, editor_notes)
            VALUES ($1, $2, $3, $4, $5, $6, 'draft', $7, $8)
            RETURNING id, title, status, created_at
            """,
            sub["title"],
            sub["body_md"] or "",
            sub["description"] or sub["title"],
            sub["author_name"] or sub["contact_name"] or "Anonymous",
            slug,
            sub["tags"],
            submission_id,
            editor_notes,
        )

        await conn.execute(
            "UPDATE submissions SET status = 'approved', admin_notes = $2 WHERE id = $1",
            submission_id,
            editor_notes,
        )

    return {"submission_id": submission_id, "post_id": post["id"], "status": "draft"}


@app.post("/admin/submissions/{submission_id}/reject")
async def reject_submission(
    submission_id: int,
    reason: Optional[str] = None,
    _=Depends(verify_admin_key),
):
    async with pool.acquire() as conn:
        sub = await conn.fetchrow(
            "SELECT * FROM submissions WHERE id = $1", submission_id
        )
        if not sub:
            raise HTTPException(status_code=404, detail="Submission not found")

        await conn.execute(
            "UPDATE submissions SET status = 'rejected', admin_notes = $2 WHERE id = $1",
            submission_id,
            reason,
        )

    return {"submission_id": submission_id, "status": "rejected"}


@app.post("/admin/submissions/{submission_id}/agent-review")
async def agent_review_submission(
    submission_id: int,
    _=Depends(verify_admin_key),
):
    async with pool.acquire() as conn:
        sub = await conn.fetchrow(
            "SELECT * FROM submissions WHERE id = $1", submission_id
        )
        if not sub:
            raise HTTPException(status_code=404, detail="Submission not found")

        text = f"{sub['title']}\n\n{sub['body_md'] or sub['description'] or ''}"
        result = await ai_tag(text)

        await conn.execute(
            """
            UPDATE submissions
            SET status = 'agent_review', agent_notes = $2
            WHERE id = $1
            """,
            submission_id,
            json.dumps({"suggested_tags": result.tags, "summary": result.summary}),
        )

        await conn.execute(
            """
            INSERT INTO review_log (submission_id, agent_name, action, notes)
            VALUES ($1, 'content-reviewer', 'review', $2)
            """,
            submission_id,
            f"Tags: {result.tags}, Summary: {result.summary}",
        )

    return {
        "submission_id": submission_id,
        "status": "agent_review",
        "suggested_tags": result.tags,
        "summary": result.summary,
    }


# ── Posts management ───────────────────────────────────────────
@app.get("/admin/posts", response_model=list[AdminPostOut])
async def admin_list_posts(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _=Depends(verify_admin_key),
):
    where = ""
    params = []
    if status:
        where = "WHERE status = $1"
        params.append(status)

    sql = f"""
        SELECT id, created_at, title, body_md, excerpt, author_name,
               slug, status, published_at, tags, submission_id, editor_notes
        FROM raw_posts
        {where}
        ORDER BY created_at DESC
        LIMIT ${2 if status else 1} OFFSET ${3 if status else 2}
    """
    params.extend([limit, offset])

    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *params)
    return [dict(r) for r in rows]


@app.post("/admin/posts/{post_id}/publish")
async def publish_post(
    post_id: int,
    _=Depends(verify_admin_key),
):
    async with pool.acquire() as conn:
        post = await conn.fetchrow(
            "SELECT * FROM raw_posts WHERE id = $1", post_id
        )
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        if post["status"] not in ("draft", "approved"):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot publish post in status '{post['status']}'",
            )

        await conn.execute(
            """
            UPDATE raw_posts
            SET status = 'published', published_at = now(), updated_at = now()
            WHERE id = $1
            """,
            post_id,
        )

    return {"post_id": post_id, "status": "published"}


@app.post("/admin/posts/{post_id}/unpublish")
async def unpublish_post(
    post_id: int,
    _=Depends(verify_admin_key),
):
    async with pool.acquire() as conn:
        post = await conn.fetchrow(
            "SELECT * FROM raw_posts WHERE id = $1", post_id
        )
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        if post["status"] != "published":
            raise HTTPException(
                status_code=400, detail="Post is not published"
            )

        await conn.execute(
            "UPDATE raw_posts SET status = 'draft', updated_at = now() WHERE id = $1",
            post_id,
        )

    return {"post_id": post_id, "status": "draft"}


# ── AI Director (admin only) ───────────────────────────────────
@app.post("/admin/ai/suggest-tags", response_model=AITagResponse)
async def admin_suggest_tags(
    request: AITagRequest,
    _=Depends(verify_admin_key),
):
    return await ai_tag(request.text)


@app.post("/admin/ai/summarize")
async def admin_summarize(
    request: AITagRequest,
    _=Depends(verify_admin_key),
):
    result = await ai_tag(request.text)
    if result.summary:
        return {"summary": result.summary}
    return {"summary": None}
