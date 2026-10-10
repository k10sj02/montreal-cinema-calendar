from __future__ import annotations

from datetime import date, datetime
from concurrent.futures import ThreadPoolExecutor
import html
import re
from zoneinfo import ZoneInfo

from ..models import Screening, TZID

URL = "https://cinemacinema.ca/fr/horaire?date={day}"
VENUES = {
    1: ("Cinéma Beaubien", "2396 rue Beaubien Est, Montréal, QC H2G 1N2"),
    2: ("Cinéma du Parc", "3575 avenue du Parc, bureau 6100, Montréal, QC H2X 3P9"),
    3: ("Cinéma du Musée", "1379-A rue Sherbrooke Ouest, Montréal, QC H3G 1K3"),
}

# The Svelte page embeds these records in its hydration payload. Field names and
# stable representation_id values come directly from Cinéma Cinéma's backend.
REP = re.compile(
    r"\{cinema_id:(?P<cinema>\d+),representation_id:(?P<rid>\d+),film_id:(?P<film>\d+),"
    r'titre:"(?P<title>(?:\\.|[^"\\])*)",representation_date:"(?P<date>\d{4}-\d{2}-\d{2})[^\"]*",'
    r'version:"(?P<version>(?:\\.|[^"\\])*)",heure_debut:"(?P<time>\d{1,2}) h (?P<minute>\d{2})",'
    r'format:"(?P<format>(?:\\.|[^"\\])*)",salle:(?P<room>\d+)',
)
DURATION_BLOCK = re.compile(r'duree:(?P<duration>\d+),representations:\[(?P<reps>.*?)\](?=,slug|\}|$)', re.S)


def _js_text(value: str) -> str:
    return html.unescape(bytes(value, "utf-8").decode("unicode_escape")) if "\\" in value else html.unescape(value)


class CinemaCinemaSource:
    name = "cinemacinema"

    def __init__(self, fetcher):
        self.fetcher = fetcher

    def fetch(self, days: list[date]) -> list[Screening]:
        found: dict[str, Screening] = {}
        def get_day(day):
            url = URL.format(day=day.isoformat())
            return url, self.fetcher.get(url)

        # Date pages are independent. A small pool keeps a full refresh quick while
        # remaining modest toward the official server (the workflow runs every 6h).
        with ThreadPoolExecutor(max_workers=6) as pool:
            pages = pool.map(get_day, days)
            for page_url, text in pages:
                durations = {}
                for block in DURATION_BLOCK.finditer(text):
                    film = re.search(r"film_id:(\d+)", block["reps"])
                    if film:
                        durations[int(film[1])] = int(block["duration"])
                for match in REP.finditer(text):
                    cinema = int(match["cinema"])
                    if cinema not in VENUES:
                        continue
                    venue, address = VENUES[cinema]
                    start = datetime.fromisoformat(f'{match["date"]}T{int(match["time"]):02d}:{match["minute"]}:00').replace(tzinfo=ZoneInfo(TZID))
                    rid = match["rid"]
                    language = _js_text(match["version"])
                    fmt = _js_text(match["format"])
                    room = match["room"]
                    found[rid] = Screening(
                        source=self.name, source_id=rid, title=_js_text(match["title"]), start=start,
                        venue=venue, address=address, url=page_url,
                        description=f"Version: {language}; format: {fmt}; salle {room}.",
                        runtime_minutes=durations.get(int(match["film"])), language=language,
                        format=fmt, room=room,
                    )
        if not found:
            raise RuntimeError("Cinéma Cinéma returned no recognizable screenings")
        return list(found.values())
