from __future__ import annotations

import argparse
from datetime import date, datetime
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

from .calendar import date_window, load_state, merge, reconcile, save_state
from .http import Fetcher
from .ics import render
from .models import TZID
from .sources import CinemaCinemaSource, CinemaPublicSource, CinemathequeSource, CinemaPoliticaSource, MicrocinemaSource


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="public/montreal-cinema.ics")
    parser.add_argument("--state", default="data/state.json")
    parser.add_argument("--days", type=int, default=45)
    parser.add_argument("--today", type=date.fromisoformat)
    parser.add_argument("--strict", action="store_true", help="fail if any source fails")
    args = parser.parse_args()
    today = args.today or datetime.now(ZoneInfo(TZID)).date()
    days = date_window(today, args.days)
    fetcher = Fetcher()
    sources = [
        CinemaCinemaSource(fetcher),
        CinemathequeSource(fetcher),
        CinemaPoliticaSource(fetcher),
        CinemaPublicSource(fetcher),
        MicrocinemaSource(fetcher),
    ]
    collected, errors, successful, coverage_ends = [], {}, set(), {}
    for source in sources:
        try:
            events = source.fetch(days)
            collected.extend(events)
            successful.add(source.name)
            if getattr(source, "coverage_end", None):
                coverage_ends[source.name] = source.coverage_end
            print(f"{source.name}: {len(events)} screenings", file=sys.stderr)
        except Exception as exc:
            errors[source.name] = str(exc)
            print(f"WARNING {source.name}: {exc}", file=sys.stderr)
    if args.strict and errors:
        return 2
    state_path = Path(args.state)
    events = reconcile(merge(collected), load_state(state_path), successful, today, coverage_ends)
    if not events:
        print("ERROR: no current or retained events; refusing to publish an empty feed", file=sys.stderr)
        return 3
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(events), newline="")
    save_state(state_path, events)
    report = {"generated": datetime.now(ZoneInfo(TZID)).isoformat(), "count": len(events), "sources_ok": sorted(successful), "errors": errors}
    report_path = output.with_suffix(".json")
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

