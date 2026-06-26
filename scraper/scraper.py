"""
Berlin Versammlungen Scraper
============================
Fetches all public assemblies from the Berlin Police JSON endpoint
and inserts raw rows into `raw_assemblies`.

Design principle: NO transformation here.
Store exactly what the API returns, as strings/nulls.
All cleaning, typing, and enrichment is dbt's job.

Run:
    python scraper.py

Env vars (or .env file):
    DATABASE_URL=postgresql://user:pass@localhost:5432/berlin_demos
"""

import logging
import os
import sys
from datetime import datetime, timezone

import psycopg2
import httpx
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# This endpoint returns ALL events in one shot (items_per_page: 99999)
JSON_URL = (
    "https://www.berlin.de/polizei/service/versammlungsbehoerde/"
    "versammlungen-aufzuege/index.php/index/all.json"
)


def fetch_events(url: str) -> list[dict]:
    """Download and parse the JSON endpoint."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Accept-Language": "de-DE,de;q=0.9",
    }
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        resp = client.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    items = data.get("index", [])
    log.info(
        "Fetched %d events (API reports count=%s)",
        len(items),
        data.get("results", {}).get("count", "?"),
    )
    return items


def write_to_db(events: list[dict], database_url: str) -> tuple[int, int]:
    """
    Insert raw rows into `raw_assemblies`.

    Deduplication strategy: the API provides a stable `id` field per event.
    We use (source_id, datum) as the unique key — same event on same date
    won't be re-inserted on a second scrape.

    ON CONFLICT DO NOTHING means running the scraper twice is always safe.
    """
    if not events:
        return 0, 0

    sql = """
        INSERT INTO raw_assemblies (
            scraped_at,
            source_id,
            datum,
            von,
            bis,
            thema,
            plz,
            strasse_nr,
            aufzugsstrecke
        ) VALUES (
            %(scraped_at)s,
            %(source_id)s,
            %(datum)s,
            %(von)s,
            %(bis)s,
            %(thema)s,
            %(plz)s,
            %(strasse_nr)s,
            %(aufzugsstrecke)s
        )
        ON CONFLICT (source_id, datum) DO NOTHING;
    """

    scraped_at = datetime.now(timezone.utc)
    rows = [
        {
            "scraped_at": scraped_at,
            "source_id": e["id"],
            "datum": e.get("datum"),           # "24.04.2026"
            "von": e.get("von"),               # "10:00"
            "bis": e.get("bis"),               # "18:00"
            "thema": e.get("thema"),           # full German description
            "plz": e.get("plz") or None,       # "10557" or null
            "strasse_nr": e.get("strasse_nr") or None,
            "aufzugsstrecke": e.get("aufzugsstrecke") or None,
        }
        for e in events
    ]

    conn = psycopg2.connect(database_url)
    try:
        with conn:
            with conn.cursor() as cur:
                inserted = 0
                for row in rows:
                    cur.execute(sql, row)
                    inserted += cur.rowcount
    finally:
        conn.close()

    skipped = len(rows) - inserted
    return inserted, skipped


def main():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        log.error("DATABASE_URL env var is not set.")
        sys.exit(1)

    log.info("Fetching events from JSON endpoint…")
    events = fetch_events(JSON_URL)

    if not events:
        log.warning("No events returned — check the endpoint.")
        sys.exit(0)

    log.info("Writing %d events to database…", len(events))
    inserted, skipped = write_to_db(events, database_url)
    log.info("Done.  inserted=%d  skipped(duplicate)=%d", inserted, skipped)


if __name__ == "__main__":
    main()
