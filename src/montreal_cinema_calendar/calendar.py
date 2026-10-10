from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
import json
from pathlib import Path

from .models import Screening


def date_window(today: date, days: int) -> list[date]:
    return [today + timedelta(days=i) for i in range(days)]


def merge(events: list[Screening]) -> list[Screening]:
    by_uid: dict[str, Screening] = {}
    for event in events:
        current = by_uid.get(event.uid)
        if current is None or len(event.description) > len(current.description):
            by_uid[event.uid] = event
    return list(by_uid.values())


def load_state(path: Path) -> dict[str, Screening]:
    if not path.exists():
        return {}
    return {item["uid"]: Screening.from_dict(item["event"]) for item in json.loads(path.read_text())["events"]}


def reconcile(current: list[Screening], previous: dict[str, Screening], successful_sources: set[str], today: date, coverage_ends: dict[str, date] | None = None) -> list[Screening]:
    coverage_ends = coverage_ends or {}
    output = {event.uid: event for event in current}
    for uid, old in previous.items():
        if uid in output or old.start.date() < today:
            continue
        covered = old.source not in coverage_ends or old.start.date() <= coverage_ends[old.source]
        if old.source in successful_sources and covered:
            # Missing from a successfully refreshed source means removed/cancelled.
            output[uid] = replace(old, status="CANCELLED", description=old.description + "\nRemoved from the official schedule.")
        else:
            # Source outage: retain last known data, never create false cancellations.
            output[uid] = old
    return list(output.values())


def save_state(path: Path, events: list[Screening]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema": 1, "events": [{"uid": e.uid, "fingerprint": e.fingerprint, "event": e.to_dict()} for e in events]}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

