from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from html import unescape
import json
import re
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from ..models import Screening, TZID


class CinemaClockSource:
    """Citywide fallback for cinemas not covered by a direct venue source."""

    name = "cinemaclock-montreal"
    base_url = "https://www.cinemaclock.com"
    listing_url = f"{base_url}/montreal-qc/movie-theaters"

    def __init__(self, fetcher):
        self.fetcher = fetcher
        self.coverage_end: date | None = None

    def fetch(self, days: list[date]) -> list[Screening]:
        listing = BeautifulSoup(self._get(self.listing_url), "html.parser")
        paths = sorted({
            link.get("href")
            for link in listing.select('a[href^="/movie-theaters/"]')
            if link.get("href")
        })
        if not paths:
            raise RuntimeError("CinemaClock Montréal cinema list contained no venues")

        wanted = {(value.month, value.day): value for value in days}
        with ThreadPoolExecutor(max_workers=6) as pool:
            pages = list(pool.map(self._fetch_page, paths))

        events: list[Screening] = []
        covered_dates: list[date] = []
        for path, html in pages:
            parsed, dates = self._parse_theatre(path, html, wanted)
            events.extend(parsed)
            covered_dates.extend(dates)
        if covered_dates:
            self.coverage_end = max(covered_dates)
        return events

    def _fetch_page(self, path: str) -> tuple[str, str]:
        url = f"{self.base_url}/montreal-qc{path}"
        return path, self._get(url)

    def _get(self, url: str) -> str:
        return self.fetcher.get(url, headers={"Accept-Language": "en-CA,en;q=0.9"})

    def _parse_theatre(
        self, path: str, html: str, wanted: dict[tuple[int, int], date]
    ) -> tuple[list[Screening], list[date]]:
        soup = BeautifulSoup(html, "html.parser")
        theatre = _theatre_details(soup) or _theatre_details_raw(html)
        if not theatre:
            raise RuntimeError(f"CinemaClock venue page lacked theatre metadata: {path}")
        venue, address = theatre
        page_url = f"{self.base_url}/montreal-qc{path}"
        events: list[Screening] = []
        covered_dates: list[date] = []

        for block in soup.select("div.showtimeblock.movie"):
            title_link = block.select_one("h3.movietitle a")
            if not title_link:
                continue
            title = unescape(title_link.get_text(" ", strip=True))
            movie_url = urljoin(self.base_url, title_link.get("href", page_url))
            runtime = _runtime(block)
            rating = block.select_one(".moviegenre .rtQC")
            language = _language(block)
            movie_description = f"Québec rating: {rating.get_text(' ', strip=True)}" if rating else ""

            for presentation in block.select("div.filall"):
                format_label = _format(presentation)
                for paragraph in presentation.select("p.times, p.timesother"):
                    for date_label in paragraph.select("u"):
                        match = re.search(
                            r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})",
                            date_label.get_text(" ", strip=True),
                        )
                        if not match:
                            continue
                        event_date = wanted.get((_MONTHS[match.group(1)], int(match.group(2))))
                        if not event_date:
                            continue
                        covered_dates.append(event_date)
                        times = date_label.find_next_sibling("i")
                        if times is None:
                            continue
                        for showtime in times.select("span.tix[data-time]"):
                            raw_time = showtime.get("data-time", "").zfill(4)
                            if not raw_time.isdigit() or len(raw_time) != 4:
                                continue
                            start = datetime(
                                event_date.year, event_date.month, event_date.day,
                                int(raw_time[:2]), int(raw_time[2:]), tzinfo=ZoneInfo(TZID),
                            )
                            source_id = showtime.get("id")
                            if not source_id:
                                continue
                            events.append(Screening(
                                source=self.name, source_id=source_id, title=title, start=start,
                                venue=venue, address=address, url=movie_url,
                                description=movie_description, runtime_minutes=runtime,
                                language=language, format=format_label,
                            ))
        return events, covered_dates


def _theatre_details(soup: BeautifulSoup) -> tuple[str, str] | None:
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            value = json.loads(script.string or script.get_text())
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(value, dict) and value.get("@type") == "MovieTheater":
            address = value.get("address") or {}
            parts = [address.get("streetAddress"), address.get("addressLocality"),
                     address.get("addressRegion"), address.get("postalCode")]
            return unescape(value.get("name", "")), ", ".join(str(part) for part in parts if part)
    title = soup.select_one("#h1title h1")
    address = soup.select_one("#h1address")
    if title and address:
        address_text = address.get_text(" ", strip=True).replace("...", "")
        address_text = re.sub(r"\s+", " ", address_text).strip(" ,·")
        return unescape(title.get_text(" ", strip=True)), unescape(address_text)
    return None


def _theatre_details_raw(html: str) -> tuple[str, str] | None:
    title = re.search(r'<div id="h1title".*?<h1>(.*?)</h1>', html, re.DOTALL)
    address = re.search(r'<div id="h1address"[^>]*>(.*?)<svg', html, re.DOTALL)
    if not title or not address:
        return None
    title_text = BeautifulSoup(title.group(1), "html.parser").get_text(" ", strip=True)
    address_text = BeautifulSoup(address.group(1), "html.parser").get_text(" ", strip=True)
    address_text = re.sub(r"\s+", " ", address_text).replace("...", "").strip(" ,·")
    return unescape(title_text), unescape(address_text)


def _runtime(block) -> int | None:
    genre = block.select_one(".moviegenre")
    match = re.search(r"(?:(\d+)h)?(\d+)m", genre.get_text(" ", strip=True) if genre else "")
    return (int(match.group(1) or 0) * 60 + int(match.group(2))) if match else None


def _language(block) -> str:
    value = block.select_one(".movietitleother .subt")
    if not value:
        return ""
    return re.sub(r"^(?:in|version of)\s+", "", value.get_text(" ", strip=True), flags=re.IGNORECASE)


def _format(presentation) -> str:
    values = [node.get_text(" ", strip=True) for node in presentation.select("p.timesalso")]
    return " · ".join(value for value in values if value)


_MONTHS = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
           "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}
