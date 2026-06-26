import json
from contextlib import asynccontextmanager
from datetime import date
from typing import Any, Optional

import asyncpg
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    allowed_origins: str = "*"
    class Config:
        env_file = ".env"

settings = Settings()
pool: asyncpg.Pool = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    pool = await asyncpg.create_pool(settings.database_url, min_size=2, max_size=10)
    yield
    await pool.close()

app = FastAPI(
    title="Berlin Demos API",
    description="Public assemblies and demonstrations in Berlin",
    version="1.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


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

class TagSummary(BaseModel):
    slug: str
    label_de: str
    label_en: str
    event_count: int


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
    """
    Look up each word in the search_translations table.
    If a word has a German translation, append it to the query
    so both the English and German stems are searched.

    Example: "climate housing" becomes "climate Klima housing Wohnen"
    Then plainto_tsquery('german_unaccent', ...) stems all words,
    and 'Klima' → 'klima' which matches the vector.
    """
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
            [w.lower() for w in words]
        )

    translation_map = {row["en_term"].lower(): row["de_term"] for row in translations}

    expanded = []
    for word in words:
        expanded.append(word)
        de = translation_map.get(word.lower())
        if de:
            expanded.append(de)  # append German equivalent

    return " ".join(expanded)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/events", response_model=list[EventSummary])
async def list_events(
    date_from:   Optional[date] = Query(None),
    date_to:     Optional[date] = Query(None),
    district:    Optional[str]  = Query(None),
    postcode:    Optional[str]  = Query(None),
    event_type:  Optional[str]  = Query(None),
    tag:         Optional[str]  = Query(None),
    has_route:   Optional[bool] = Query(None),
    q:           Optional[str]  = Query(None, description="Search (German or English)"),
    limit:       int  = Query(50, ge=1, le=200),
    offset:      int  = Query(0, ge=0),
    upcoming:    bool = Query(True),
):
    conditions = []
    params = []
    i = 1

    if upcoming:
        conditions.append("event_date >= CURRENT_DATE")
    if date_from:
        conditions.append(f"event_date >= ${i}"); params.append(date_from); i += 1
    if date_to:
        conditions.append(f"event_date <= ${i}"); params.append(date_to); i += 1
    if district:
        conditions.append(f"district_name = ${i}"); params.append(district); i += 1
    if postcode:
        conditions.append(f"postcode = ${i}"); params.append(postcode); i += 1
    if event_type:
        conditions.append(f"event_type = ${i}"); params.append(event_type); i += 1
    if has_route is not None:
        conditions.append(f"has_route = ${i}"); params.append(has_route); i += 1
    if tag:
        conditions.append(f"tags @> ${i}::jsonb")
        params.append(json.dumps([{"slug": tag}])); i += 1

    if q:
        # Expand English terms to also include German equivalents
        expanded_q = await translate_query(q)
        conditions.append(
            f"search_vector @@ plainto_tsquery('german_unaccent', ${i})"
        )
        params.append(expanded_q); i += 1

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    if q:
        expanded_q_rank = await translate_query(q)
        order = f"""
            ORDER BY
                ts_rank(search_vector, plainto_tsquery('german_unaccent', ${i})) DESC,
                event_date ASC,
                time_start ASC NULLS LAST
        """
        params.append(expanded_q_rank); i += 1
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