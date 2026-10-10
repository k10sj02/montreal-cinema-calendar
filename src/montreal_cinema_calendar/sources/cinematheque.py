from __future__ import annotations

from datetime import date, datetime
import re
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from ..models import Screening, TZID

URL = "https://www.cinematheque.qc.ca/fr/programme/"
ADDRESS = "335 boulevard De Maisonneuve Est, Montréal, QC H2X 1K1"
MONTHS = {"janvier":1,"février":2,"mars":3,"avril":4,"mai":5,"juin":6,"juillet":7,"août":8,"septembre":9,"octobre":10,"novembre":11,"décembre":12}


class CinemathequeSource:
    name = "cinematheque-quebecoise"

    def __init__(self, fetcher):
        self.fetcher = fetcher

    def fetch(self, days: list[date]) -> list[Screening]:
        soup = BeautifulSoup(self.fetcher.get(URL), "html.parser")
        allowed = set(days)
        events: dict[str, Screening] = {}
        # Programme cards contain a work link followed by one or more French
        # long-form date/time strings, including text split across nested tags.
        for link in soup.select("a[href]"):
            title = " ".join(link.get_text(" ", strip=True).split())
            if not title or title.lower() in {"billets", "suivant", "précédent"}:
                continue
            container = link.find_parent(["article", "li", "div"])
            if not container:
                continue
            text = " ".join(container.get_text(" ", strip=True).split())
            matches = list(re.finditer(r"(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\s+(\d{1,2})\s+(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+(\d{4})\s*(?:à|a)\s*(\d{1,2}):(\d{2})", text, re.I))
            if not matches:
                continue
            event_url = urljoin(URL, link.get("href", ""))
            slug = urlparse(event_url).path.rstrip("/").split("/")[-1]
            free = bool(re.search(r"entrée libre|gratuit", text, re.I))
            for m in matches:
                d = date(int(m[3]), MONTHS[m[2].lower()], int(m[1]))
                if d not in allowed:
                    continue
                start = datetime(d.year,d.month,d.day,int(m[4]),int(m[5]),tzinfo=ZoneInfo(TZID))
                source_id = f"{slug}|{start:%Y%m%dT%H%M}"
                events[source_id] = Screening(
                    source=self.name, source_id=source_id, title=title, start=start,
                    venue="Cinémathèque québécoise", address=ADDRESS, url=event_url,
                    description=("Admission: free / entrée libre." if free else "Cinémathèque québécoise screening."),
                    admission=("FREE" if free else ""),
                )
        if not events:
            raise RuntimeError("Cinémathèque page returned no recognizable screenings")
        return list(events.values())

