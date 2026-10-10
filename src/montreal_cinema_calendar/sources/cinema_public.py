from __future__ import annotations

from datetime import date, datetime
from html import unescape
import json
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from ..models import Screening, TZID


class CinemaPublicSource:
    name = "cinema-public"
    url = "https://cinemapublic.ca/horaire/"

    def __init__(self, fetcher):
        self.fetcher = fetcher
        self.coverage_end: date | None = None

    def fetch(self, days: list[date]) -> list[Screening]:
        wanted = set(days)
        soup = BeautifulSoup(self.fetcher.get(self.url), "html.parser")
        graph: dict = {}
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                payload = json.loads(script.string or script.get_text())
            except (TypeError, json.JSONDecodeError):
                continue
            candidate = payload.get("@graph", {}) if isinstance(payload, dict) else {}
            if isinstance(candidate, dict) and candidate.get("itemListElement"):
                graph = candidate
                break
        if not graph:
            raise RuntimeError("official schedule did not contain screening data")

        locations = {
            value.get("@id"): value
            for value in graph.values()
            if isinstance(value, dict) and "MovieTheater" in _types(value)
        }
        events: list[Screening] = []
        seen_dates: list[date] = []
        for wrapper in graph.get("itemListElement", []):
            item = wrapper.get("item", {})
            if "ScreeningEvent" not in _types(item):
                continue
            start = datetime.fromisoformat(item["startDate"]).astimezone(ZoneInfo(TZID))
            seen_dates.append(start.date())
            if start.date() not in wanted:
                continue
            movie = item.get("workPresented", {})
            location = locations.get((item.get("location") or {}).get("@id"), {})
            address = location.get("address", {})
            offer = item.get("offers", {})
            event_url = item.get("url") or movie.get("url") or self.url
            source_id = urlparse(item.get("@id", event_url)).path.rstrip("/").rsplit("/", 1)[-1]
            director = (movie.get("director") or {}).get("name", "")
            ticket_url = offer.get("url", "")
            description = f"Director: {unescape(director)}" if director else ""
            if ticket_url:
                description += ("\n" if description else "") + f"Tickets: {ticket_url}"
            events.append(Screening(
                source=self.name, source_id=source_id,
                title=unescape(movie.get("name") or item.get("name", "").replace(" — séance ", "")),
                start=start,
                venue=unescape(location.get("name", "Cinéma Public")),
                address=_address(address),
                url=event_url,
                description=description,
                language=movie.get("inLanguage", ""),
            ))
        if seen_dates:
            self.coverage_end = max(seen_dates)
        return events


def _types(item: dict) -> list[str]:
    value = item.get("@type", [])
    return value if isinstance(value, list) else [value]


def _address(value: dict) -> str:
    parts = [value.get("streetAddress"), value.get("addressLocality"), value.get("postalCode")]
    return ", ".join(unescape(part) for part in parts if part)
