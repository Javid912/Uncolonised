"""
Uncolonised — run all configured scrapers.

Add new scrapers by creating a class in scraper/sources/
and registering it in the SOURCES list below.

Usage:
    python scraper/run_all.py
"""

import logging
import os
import sys

from dotenv import load_dotenv

from scraper.sources.berlin_police import BerlinPoliceScraper

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# Register new scrapers here
SOURCES = [
    BerlinPoliceScraper(),
]


def main():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        log.error("DATABASE_URL env var is not set.")
        sys.exit(1)

    log.info("Starting %d scraper(s)…", len(SOURCES))

    for scraper in SOURCES:
        result = scraper.run(database_url)
        if result.error:
            log.error("  %-20s  ERROR: %s", result.source_name, result.error)
        else:
            log.info(
                "  %-20s  inserted=%d  skipped=%d",
                result.source_name,
                result.inserted,
                result.skipped,
            )

    log.info("All scrapers complete.")


if __name__ == "__main__":
    main()
