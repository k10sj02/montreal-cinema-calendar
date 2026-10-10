from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from icalendar import Calendar

from montreal_cinema_calendar.calendar import merge, reconcile
from montreal_cinema_calendar.ics import render
from montreal_cinema_calendar.models import Screening, TZID
from montreal_cinema_calendar.sources.cinemacinema import CinemaCinemaSource
from montreal_cinema_calendar.sources.cinema_politica import CinemaPoliticaSource


class FakeFetcher:
    def __init__(self, pages): self.pages = pages
    def get(self, url):
        for key, value in self.pages.items():
            if key in url: return value
        raise KeyError(url)


def sample(source="x", source_id="42"):
    return Screening(source, source_id, "Montréal, ma belle", datetime(2026,10,21,18,30,tzinfo=ZoneInfo(TZID)), "Venue", "1 rue Test, Montréal, QC", "https://example.test/e", runtime_minutes=90)


def test_valid_ics_timezone_utf8_and_duration():
    raw = render([sample()], datetime(2026,10,10,tzinfo=ZoneInfo("UTC")))
    parsed = Calendar.from_ical(raw)
    event = parsed.walk("VEVENT")[0]
    assert event["UID"] == sample().uid
    assert event.decoded("DTSTART").tzinfo.key == TZID
    assert event.decoded("DTEND").hour == 20
    assert max(len(line.encode()) for line in raw.splitlines()) <= 75


def test_uid_stable_across_title_and_time_correction():
    original = sample()
    corrected = Screening(**{**original.__dict__, "title":"Corrected", "start":original.start.replace(hour=19)})
    assert original.uid == corrected.uid


def test_merge_and_cancellation_only_after_successful_refresh():
    old = sample("venue", "gone")
    assert reconcile([], {old.uid:old}, set(), date(2026,10,10))[0].status == "CONFIRMED"
    assert reconcile([], {old.uid:old}, {"venue"}, date(2026,10,10))[0].status == "CANCELLED"
    assert len(merge([old, old])) == 1


def test_cinemacinema_embedded_records():
    # Field shape captured from the official Svelte hydration payload.
    page = '''film_id:2190,cinema_id:1,titre:"NITASSINAN",genre1:"Documentaire",duree:78,representations:[{cinema_id:1,representation_id:52620,film_id:2190,titre:"NITASSINAN",representation_date:"2026-10-10T00:00:00.000Z",version:"VOSTF",heure_debut:"14 h 30",format:"2D",salle:4,salle_desc:""}]'''
    got = CinemaCinemaSource(FakeFetcher({"cinemacinema":page})).fetch([date(2026,10,10)])
    assert [(e.source_id,e.venue,e.start.hour,e.runtime_minutes) for e in got] == [("52620","Cinéma Beaubien",14,78)]


def test_cinema_politica_individual_detail():
    listing = '<a href="/screening/film-name/">Mon., Oct. 19</a>'
    detail = '<article id="post-58203"><h1>STEAL THIS STORY, PLEASE! – with guests</h1><h4>Monday, Oct. 19, 7:00pm</h4></article>'
    got = CinemaPoliticaSource(FakeFetcher({"local/concordia":listing,"screening/film-name":detail})).fetch([date(2026,10,19)])
    assert got[0].start.hour == 19
    assert got[0].admission == "BY DONATION"
    assert got[0].source_id == "58203"
