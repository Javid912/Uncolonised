"""
Base scraper interface for Uncolonised multi-source event ingestion.

Each source subclasses BaseScraper and implements:
    - name: human-readable source name
    - fetch(): return list of raw event dicts
    - write_to_db(events): persist to the appropriate raw table
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ScrapeResult:
    source_name: str
    inserted: int
    skipped: int
    error: str | None = None


class BaseScraper(ABC):

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def fetch(self) -> list[dict]:
        ...

    @abstractmethod
    def write_to_db(self, events: list[dict], database_url: str) -> tuple[int, int]:
        ...

    def run(self, database_url: str) -> ScrapeResult:
        try:
            events = self.fetch()
            if not events:
                return ScrapeResult(self.name, 0, 0)
            inserted, skipped = self.write_to_db(events, database_url)
            return ScrapeResult(self.name, inserted, skipped)
        except Exception as e:
            return ScrapeResult(self.name, 0, 0, error=str(e))
