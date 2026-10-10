from __future__ import annotations

from datetime import date, datetime
import json
import re
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from ..models import Screening, TZID

OFFICIAL_URL = "https://www.cinematheque.qc.ca/fr/programme/"
OFFICIAL_TEXT_URL = f"https://r.jina.ai/{OFFICIAL_URL}"
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
        errors: list[str] = []
        cinoche: list[Screening] = []
        official: list[Screening] = []
        try:
            cinoche = self._fetch_cinoche(days)
        except Exception as exc:
            errors.append(f"Cinoche: {exc}")
        try:
            official = self._fetch_official(days)
        except Exception as exc:
            errors.append(f"Official programme: {exc}")
        if not cinoche and not official:
            raise RuntimeError("; ".join(errors))

        # Cinoche adds runtime, synopsis, and language metadata. Keep those
        # records when both sources describe the same screening, then add the
        # longer-range official schedule around them.
        seen = {(event.title.casefold(), event.start) for event in cinoche}
        combined = cinoche + [
            event for event in official
            if (event.title.casefold(), event.start) not in seen
        ]
        self.provider = "Cinémathèque québécoise + Cinoche" if cinoche and official else ("Cinoche" if cinoche else "Cinémathèque québécoise")
        return combined

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
        allowed = set(days)
        events: dict[str, Screening] = {}
        first_page = self.fetcher.get(OFFICIAL_TEXT_URL)
        page_numbers = [int(value) for value in re.findall(r"programme/\?page=(\d+)", first_page)]
        pages = [first_page]
        for page_number in range(2, max(page_numbers, default=1) + 1):
            pages.append(self.fetcher.get(f"{OFFICIAL_TEXT_URL}?page={page_number}"))

        weekday = r"(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)"
        date_text = rf"{weekday}\s+(\d{{1,2}})\s+({'|'.join(MONTHS)})\s+(\d{{4}})\s+(?:à|a)\s+(\d{{1,2}}):(\d{{2}})"
        link_pattern = re.compile(rf"\[({date_text})\]\((https://omniwebticketing\.com/cinematheque/\?[^)]+)\)", re.I)
        block_pattern = re.compile(rf"(?m)^([^\n\[\]#]+)\n\n((?:\[{weekday}[^\n]+\]\(https://omniwebticketing\.com/cinematheque/\?[^)]+\))+)$", re.I)
        covered_dates: list[date] = []
        for page in pages:
            for block in block_pattern.finditer(page):
                title = " ".join(block[1].split())
                if re.match(r"^(?:Le|Du) \d", title, re.I):
                    continue
                for match in link_pattern.finditer(block[2]):
                    day = date(int(match[4]), MONTHS[match[3].lower()], int(match[2]))
                    covered_dates.append(day)
                    if day not in allowed:
                        continue
                    start = datetime(day.year, day.month, day.day, int(match[5]), int(match[6]), tzinfo=ZoneInfo(TZID))
                    event_url = match[7]
                    ticket_id = parse_qs(urlparse(event_url).query).get("perfix", [""])[0]
                    source_id = f"official:{ticket_id or title.casefold()}:{start:%Y%m%dT%H%M}"
                    events[source_id] = Screening(
                        source=self.name, source_id=source_id, title=title, start=start,
                        venue="Cinémathèque québécoise", address=ADDRESS, url=event_url,
                        description="Official Cinémathèque québécoise programme.",
                    )
        if not events:
            raise RuntimeError("page returned no recognizable screenings")
        dates_in_window = [value for value in covered_dates if value in allowed]
        if dates_in_window:
            self.coverage_end = max(dates_in_window)
        return list(events.values())
