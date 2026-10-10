from __future__ import annotations

from datetime import date, datetime
import json
import re
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from ..models import Screening, TZID

OFFICIAL_URL = "https://www.cinematheque.qc.ca/fr/programme/"
CINOCHE_URL = "https://www.cinoche.com/cinemas/cinematheque-quebecoise"
ADDRESS = "335 boulevard De Maisonneuve Est, Montréal, QC H2X 1K1"
MONTHS = {"janvier":1,"février":2,"mars":3,"avril":4,"mai":5,"juin":6,"juillet":7,"août":8,"septembre":9,"octobre":10,"novembre":11,"décembre":12}


def _decode_nuxt(payload: str) -> dict:
    """Decode Nuxt's flattened devalue payload without executing page code."""
    values = json.loads(payload)
    memo: dict[int, object] = {}

    def resolve(ref):
        if not isinstance(ref, int):
            return ref
        if ref < 0:
            return None
        if ref in memo:
            return memo[ref]
        value = values[ref]
        if isinstance(value, list):
            if value and value[0] in {"ShallowReactive", "Reactive", "ShallowRef", "Ref"}:
                return resolve(value[1]) if len(value) > 1 else None
            output: list = []
            memo[ref] = output
            output.extend(resolve(item) for item in value)
            return output
        if isinstance(value, dict):
            output: dict = {}
            memo[ref] = output
            output.update({key: resolve(item) for key, item in value.items()})
            return output
        return value

    decoded = resolve(0)
    if not isinstance(decoded, dict):
        raise ValueError("Unexpected Cinoche data payload")
    return decoded


def _runtime_minutes(value: str | None) -> int | None:
    if not value:
        return None
    match = re.fullmatch(r"(\d{1,2}):(\d{2}):\d{2}", value)
    return int(match[1]) * 60 + int(match[2]) if match else None


class CinemathequeSource:
    name = "cinematheque-quebecoise"

    def __init__(self, fetcher):
        self.fetcher = fetcher
        self.coverage_end: date | None = None
        self.provider = ""

    def fetch(self, days: list[date]) -> list[Screening]:
        errors = []
        try:
            events = self._fetch_cinoche(days)
            self.provider = "Cinoche"
            return events
        except Exception as exc:
            errors.append(f"Cinoche: {exc}")
        try:
            events = self._fetch_official(days)
            self.provider = "Cinémathèque québécoise"
            self.coverage_end = max(days)
            return events
        except Exception as exc:
            errors.append(f"Official programme: {exc}")
        raise RuntimeError("; ".join(errors))

    def _fetch_cinoche(self, days: list[date]) -> list[Screening]:
        soup = BeautifulSoup(self.fetcher.get(CINOCHE_URL), "html.parser")
        script = soup.find("script", id="__NUXT_DATA__")
        if not script or not script.string:
            raise RuntimeError("structured schedule payload missing")
        decoded = _decode_nuxt(script.string)
        schedule = decoded.get("data", {}).get("theater-cinematheque-quebecoise", {}).get("screenings", {})
        if not isinstance(schedule, dict) or not schedule:
            raise RuntimeError("schedule data missing")
        available_dates = [date.fromisoformat(value) for value in schedule]
        self.coverage_end = max(available_dates)
        allowed = set(days)
        events: dict[str, Screening] = {}
        for day_text, blocks in schedule.items():
            day = date.fromisoformat(day_text)
            if day not in allowed:
                continue
            for block in blocks or []:
                movies = {movie.get("id"): movie for movie in block.get("movies", [])}
                for group in block.get("screening_groups", []):
                    movie = movies.get(group.get("movie_id"))
                    if not movie:
                        continue
                    movie_id = str(movie["id"])
                    runtime = _runtime_minutes(movie.get("running_time"))
                    version = group.get("type") or {}
                    language = version.get("name", "")
                    slug = movie.get("slug") or movie_id
                    event_url = f"https://www.cinoche.com/films/{slug}"
                    synopsis = BeautifulSoup(movie.get("general_synopsis") or "", "html.parser").get_text(" ", strip=True)
                    for time_text in group.get("screenings", []):
                        hour, minute, _ = map(int, time_text.split(":"))
                        start = datetime(day.year, day.month, day.day, hour, minute, tzinfo=ZoneInfo(TZID))
                        source_id = f"cinoche:{movie_id}:{day.isoformat()}:{hour:02d}{minute:02d}"
                        events[source_id] = Screening(
                            source=self.name,
                            source_id=source_id,
                            title=movie.get("original_title") or "Cinémathèque screening",
                            start=start,
                            venue="Cinémathèque québécoise",
                            address=ADDRESS,
                            url=event_url,
                            description=(synopsis + "\n\n" if synopsis else "") + "Schedule source: Cinoche. Verify with the Cinémathèque before attending.",
                            runtime_minutes=runtime,
                            language=language,
                        )
        if not events:
            raise RuntimeError("no current screenings in structured schedule")
        return list(events.values())

    def _fetch_official(self, days: list[date]) -> list[Screening]:
        soup = BeautifulSoup(self.fetcher.get(OFFICIAL_URL), "html.parser")
        allowed = set(days)
        events: dict[str, Screening] = {}
        for link in soup.select("a[href]"):
            title = " ".join(link.get_text(" ", strip=True).split())
            if not title or title.lower() in {"billets", "suivant", "précédent"}:
                continue
            container = link.find_parent(["article", "li", "div"])
            if not container:
                continue
            text = " ".join(container.get_text(" ", strip=True).split())
            pattern = r"(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\s+(\d{1,2})\s+(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+(\d{4})\s*(?:à|a)\s*(\d{1,2}):(\d{2})"
            for match in re.finditer(pattern, text, re.I):
                day = date(int(match[3]), MONTHS[match[2].lower()], int(match[1]))
                if day not in allowed:
                    continue
                start = datetime(day.year, day.month, day.day, int(match[4]), int(match[5]), tzinfo=ZoneInfo(TZID))
                event_url = urljoin(OFFICIAL_URL, link.get("href", ""))
                slug = urlparse(event_url).path.rstrip("/").split("/")[-1]
                source_id = f"official:{slug}:{start:%Y%m%dT%H%M}"
                events[source_id] = Screening(
                    source=self.name, source_id=source_id, title=title, start=start,
                    venue="Cinémathèque québécoise", address=ADDRESS, url=event_url,
                    description="Cinémathèque québécoise screening.",
                    admission="FREE" if re.search(r"entrée libre|gratuit", text, re.I) else "",
                )
        if not events:
            raise RuntimeError("page returned no recognizable screenings")
        return list(events.values())
