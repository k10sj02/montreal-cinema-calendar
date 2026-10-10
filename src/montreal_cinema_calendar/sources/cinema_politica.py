from __future__ import annotations

from datetime import date, datetime
import re
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from ..models import Screening, TZID

LIST_URL = "https://www.cinemapolitica.org/local/concordia/"
ADDRESS = "Concordia University, Room H-110, 1455 boulevard De Maisonneuve Ouest, Montréal, QC H3G 1M8"


class CinemaPoliticaSource:
    name = "cinema-politica-concordia"

    def __init__(self, fetcher):
        self.fetcher = fetcher

    def fetch(self, days: list[date]) -> list[Screening]:
        allowed = set(days)
        soup = BeautifulSoup(self.fetcher.get(LIST_URL), "html.parser")
        urls = sorted({urljoin(LIST_URL, a["href"]) for a in soup.select('a[href*="/screening/"]')})
        events = []
        for url in urls:
            detail = BeautifulSoup(self.fetcher.get(url), "html.parser")
            title_el = detail.select_one("h1") or detail.select_one(".elementor-page-title")
            title = title_el.get_text(" ", strip=True) if title_el else urlparse(url).path.rstrip("/").split("/")[-1].replace("-", " ").title()
            text = " ".join(detail.stripped_strings)
            match = re.search(r"(?:Monday|Mon\.),?\s+([A-Z][a-z]+\.?\s+\d{1,2})(?:,\s*(\d{4}))?[,\s]+(?:at\s+)?(\d{1,2}:\d{2})\s*(am|pm)", text, re.I)
            if not match:
                continue
            year = int(match[2]) if match[2] else min(days).year
            start = date_parser.parse(f"{match[1]} {year} {match[3]} {match[4]}").replace(tzinfo=ZoneInfo(TZID))
            if start.date() not in allowed:
                continue
            post = detail.select_one("article[id^=post-]")
            source_id = post.get("id", "").replace("post-", "") if post else urlparse(url).path.rstrip("/").split("/")[-1]
            runtime = None
            runtime_match = re.search(r"(?:runtime|duration)\s*:?\s*(\d{2,3})\s*(?:min|minutes)", text, re.I)
            if runtime_match:
                runtime = int(runtime_match[1])
            events.append(Screening(
                source=self.name, source_id=source_id, title=title, start=start,
                venue="Cinema Politica Concordia", address=ADDRESS, url=url,
                description="Cinema Politica Concordia screening. Admission: by donation.",
                runtime_minutes=runtime, room="H-110", admission="BY DONATION",
            ))
        return events

