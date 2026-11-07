from __future__ import annotations

from datetime import date, datetime
import os
from zoneinfo import ZoneInfo

from ..models import Screening, TZID


class CineplexForumSource:
    name = "cineplex-forum"
    theatre_id = 9109
    venue = "Cinéma Cineplex Forum et VIP"
    address = "2313 rue Sainte-Catherine Ouest Suite 101, Montréal, QC H3H 1N2"
    api_url = (
        "https://apis.cineplex.com/prod/cpx/theatrical/api/v1/showtimes"
        f"?LocationId={theatre_id}"
    )
    # This is Cineplex's public website client key, not an account credential.
    # The environment override makes a future key rotation deployable immediately.
    api_key = os.environ.get("CINEPLEX_API_KEY", "dcdac5601d864addbc2675a2e96cb1f8")

    def __init__(self, fetcher):
        self.fetcher = fetcher
        self.coverage_end: date | None = None

    def fetch(self, days: list[date]) -> list[Screening]:
        wanted = set(days)
        payload = self.fetcher.get_json(
            self.api_url,
            headers={"Ocp-Apim-Subscription-Key": self.api_key},
        )
        if not isinstance(payload, list):
            raise RuntimeError("official Cineplex schedule returned an unexpected response")

        events: list[Screening] = []
        published_dates: list[date] = []
        for theatre in payload:
            if theatre.get("theatreId") != self.theatre_id:
                continue
            for day in theatre.get("dates", []):
                day_date = datetime.fromisoformat(day["startDate"]).date()
                published_dates.append(day_date)
                if day_date not in wanted:
                    continue
                for movie in day.get("movies", []):
                    events.extend(self._screenings(movie))

        if published_dates:
            self.coverage_end = max(published_dates)
        return events

    def _screenings(self, movie: dict) -> list[Screening]:
        results: list[Screening] = []
        for experience in movie.get("experiences", []):
            formats = [str(value) for value in experience.get("experienceTypes", []) if value]
            if experience.get("isCcEnabled"):
                formats.append("CC")
            if experience.get("isDsEnabled"):
                formats.append("DS")
            format_label = ", ".join(dict.fromkeys(formats))
            for session in experience.get("sessions", []):
                session_id = session.get("vistaSessionId")
                start_value = session.get("showStartDateTime")
                if session_id is None or not start_value:
                    continue
                start = datetime.fromisoformat(start_value).replace(tzinfo=ZoneInfo(TZID))
                ticket_url = session.get("ticketingUrl", "")
                details = []
                if movie.get("localRating"):
                    details.append(f"Rating: {movie['localRating']}")
                if movie.get("warnings"):
                    details.append("Warnings: " + ", ".join(movie["warnings"]))
                if ticket_url:
                    details.append(f"Tickets: {ticket_url}")
                results.append(Screening(
                    source=self.name,
                    source_id=str(session_id),
                    title=movie.get("name", "Untitled screening"),
                    start=start,
                    venue=self.venue,
                    address=self.address,
                    url=movie.get("detailPageUrl") or ticket_url or self.api_url,
                    description="\n".join(details),
                    runtime_minutes=movie.get("runtimeInMinutes"),
                    language=movie.get("language", ""),
                    format=format_label,
                    room=session.get("auditorium", ""),
                ))
        return results
