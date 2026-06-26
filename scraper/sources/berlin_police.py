"""
Berlin Police Versammlungsbehorde scraper.

Fetches all public assemblies from the Berlin Police JSON endpoint
and inserts raw rows into `raw_assemblies`.
"""

import logging
from datetime import datetime, timezone

import httpx
import psycopg2

from scraper.sources.base import BaseScraper

log = logging.getLogger(__name__)

JSON_URL = (
    "https://www.berlin.de/polizei/service/versammlungsbehoerde/"
    "versammlungen-aufzuege/index.php/index/all.json"
)


class BerlinPoliceScraper(BaseScraper):

    @property
    def name(self) -> str:
        return "berlin_police"

    def fetch(self) -> list[dict]:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            "Accept": "application/json",
            "Accept-Language": "de-DE,de;q=0.9",
        }
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            resp = client.get(JSON_URL, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        items = data.get("index", [])
        log.info(
            "Berlin Police: fetched %d events (count=%s)",
            len(items),
            data.get("results", {}).get("count", "?"),
        )
        return items

    def write_to_db(self, events: list[dict], database_url: str) -> tuple[int, int]:
        if not events:
            return 0, 0

        sql = """
            INSERT INTO raw_assemblies (
                scraped_at, source_id, datum, von, bis,
                thema, plz, strasse_nr, aufzugsstrecke
            ) VALUES (
                %(scraped_at)s, %(source_id)s, %(datum)s,
                %(von)s, %(bis)s, %(thema)s, %(plz)s,
                %(strasse_nr)s, %(aufzugsstrecke)s
            )
            ON CONFLICT (source_id, datum) DO NOTHING;
        """

        scraped_at = datetime.now(timezone.utc)
        rows = [
            {
                "scraped_at": scraped_at,
                "source_id": e["id"],
                "datum": e.get("datum"),
                "von": e.get("von"),
                "bis": e.get("bis"),
                "thema": e.get("thema"),
                "plz": e.get("plz") or None,
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
