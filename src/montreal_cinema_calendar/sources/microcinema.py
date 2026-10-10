from __future__ import annotations

from datetime import date, datetime
import json
import re
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from ..models import Screening, TZID


VENUES = {
    "cinema-moderne": ("Cinéma Moderne", "5150 boul. Saint-Laurent, Montréal, QC H2T 1R8"),
    "j-a-de-seve-cinema": ("J.A. de Sève Cinema", "1400 boul. De Maisonneuve O, Montréal, QC H3G 1M8"),
    "salle-j-a-de-seve-universite-concordia": ("Salle J.A. de Sève — Université Concordia", "1400 boul. De Maisonneuve O, Montréal, QC H3G 1M8"),
    "blue-sunshine": ("Blue Sunshine", "Montréal, QC"),
}

PROGRAM_RE = re.compile(
    r"\b(?:RIDM|Rencontres internationales du documentaire|Festival du nouveau cin[eé]ma|"
    r"image\+nation|Festival international du film sur l.art|Cin[eé]ma sous les [eé]toiles|"
    r"Blue Sunshine|Cine-Campus|Cin[eé]-Campus)\b",
    re.IGNORECASE,
)


class MicrocinemaSource:
    name = "microcinema-film-clubs"
    base_url = "https://montreal.hasthings.com/api/events"

    def __init__(self, fetcher):
        self.fetcher = fetcher
        self.coverage_end: date | None = None

    def fetch(self, days: list[date]) -> list[Screening]:
        if not days:
            return []
        params = {"from": min(days).isoformat(), "to": max(days).isoformat(), "category": "film", "limit": 500}
        payload = json.loads(self.fetcher.get(f"{self.base_url}?{urlencode(params)}"))
        if payload.get("nextOffset") is not None:
            raise RuntimeError("film listing exceeded one API page")
        wanted = set(days)
        events: list[Screening] = []
        for item in payload.get("items", []):
            venue_data = item.get("venue") or {}
            slug = venue_data.get("slug", "")
            labels = [item.get("title", ""), venue_data.get("name", "")]
            labels.extend(item.get("sources") or [])
            labels.extend(tag.get("label", "") for tag in item.get("tags") or [])
            if slug not in VENUES and not PROGRAM_RE.search(" | ".join(labels)):
                continue
            start = datetime.fromisoformat(item["startsAt"].replace("Z", "+00:00")).astimezone(ZoneInfo(TZID))
            if start.date() not in wanted:
                continue
            venue, address = VENUES.get(slug, (venue_data.get("name") or "Montréal film event", "Montréal, QC"))
            tags = [tag.get("label", "") for tag in item.get("tags") or [] if tag.get("kind") != "provider"]
            description = " · ".join(filter(None, tags + ["Data: Has Things (hasthings.com), ODbL 1.0"]))
            events.append(Screening(
                source=self.name, source_id=item["id"], title=item["title"], start=start,
                venue=venue, address=address,
                url=item.get("ticketUrl") or item.get("url") or "https://montreal.hasthings.com/",
                description=description, format=" · ".join(tags),
                admission="FREE" if any(tag.lower() == "free" for tag in tags) else "",
                status="CANCELLED" if item.get("status") == "cancelled" else "CONFIRMED",
            ))
        self.coverage_end = max(days)
        return events
