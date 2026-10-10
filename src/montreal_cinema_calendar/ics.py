from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .models import Screening, TZID


def escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")


def fold(line: str) -> list[str]:
    # RFC 5545 folds at 75 octets, never through a UTF-8 code point.
    out = []
    prefix = ""
    remaining = line
    while len((prefix + remaining).encode()) > 75:
        budget = 75 - len(prefix.encode())
        used = 0
        cut = 0
        for index, char in enumerate(remaining):
            size = len(char.encode())
            if used + size > budget:
                break
            used += size
            cut = index + 1
        out.append(prefix + remaining[:cut])
        remaining = remaining[cut:]
        prefix = " "
    out.append(prefix + remaining)
    return out


def render(events: list[Screening], generated_at: datetime | None = None) -> str:
    now = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Montréal Cinema Calendar//EN",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:Montréal Cinema",
        f"X-WR-TIMEZONE:{TZID}", "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
        "X-PUBLISHED-TTL:PT6H",
    ]
    for event in sorted(events, key=lambda e: (e.start, e.venue, e.title)):
        summary_prefix = "💚 " if event.admission == "BY DONATION" else ("🆓 " if event.admission == "FREE" else "🎬 ")
        details = [event.description]
        if event.language and f"Version: {event.language}" not in event.description:
            details.append(f"Version: {event.language}")
        details.append(f"Source: {event.url}")
        lines += ["BEGIN:VEVENT", f"UID:{event.uid}", f"DTSTAMP:{stamp}"]
        lines.append(f"DTSTART;TZID={TZID}:{event.start.strftime('%Y%m%dT%H%M%S')}")
        if event.runtime_minutes:
            end = event.start + timedelta(minutes=event.runtime_minutes)
            lines.append(f"DTEND;TZID={TZID}:{end.strftime('%Y%m%dT%H%M%S')}")
        lines += [
            f"SUMMARY:{escape(summary_prefix + event.title + ' | ' + event.venue)}",
            f"LOCATION:{escape(event.address)}", f"DESCRIPTION:{escape(chr(10).join(filter(None, details)))}",
            f"URL:{event.url}", f"STATUS:{event.status}", "TRANSP:TRANSPARENT",
            f"X-MONTREAL-CINEMA-SOURCE:{event.source}", f"X-MONTREAL-CINEMA-SOURCE-ID:{escape(event.source_id)}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    folded = [part for line in lines for part in fold(line)]
    return "\r\n".join(folded) + "\r\n"

