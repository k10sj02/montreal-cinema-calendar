from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from icalendar import Calendar

from montreal_cinema_calendar.calendar import merge, reconcile
from montreal_cinema_calendar.ics import render
from montreal_cinema_calendar.models import Screening, TZID
from montreal_cinema_calendar.sources.cinemacinema import CinemaCinemaSource
from montreal_cinema_calendar.sources.cinema_politica import CinemaPoliticaSource
from montreal_cinema_calendar.sources.cinematheque import CinemathequeSource


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


def test_partial_source_only_cancels_dates_in_coverage():
    visible = sample("venue", "visible")
    later = Screening(**{**sample("venue", "later").__dict__, "start": datetime(2026,11,1,18,30,tzinfo=ZoneInfo(TZID))})
    got = reconcile([], {visible.uid: visible, later.uid: later}, {"venue"}, date(2026,10,10), {"venue": date(2026,10,25)})
    by_id = {item.source_id: item for item in got}
    assert by_id["visible"].status == "CANCELLED"
    assert by_id["later"].status == "CONFIRMED"


def test_cinematheque_cinoche_nuxt_payload():
    payload = '[["ShallowReactive",1],{"data":2},["ShallowReactive",3],{"theater-cinematheque-quebecoise":4},{"screenings":5},{"2026-10-14":6},[7],{"movies":8,"screening_groups":15},[9],{"id":10,"original_title":11,"slug":12,"running_time":13,"general_synopsis":14},43735,"6 portraits néoréalistes","6-portraits-neorealistes","01:16:00","<p>Synopsis</p>",[16],{"movie_id":10,"screenings":17,"type":19},[18],"14:15:00",{"name":20},"Version originale en français"]'
    page = f'<script id="__NUXT_DATA__" type="application/json">{payload}</script>'
    got = CinemathequeSource(FakeFetcher({"cinoche.com": page})).fetch([date(2026,10,14)])
    assert len(got) == 1
    assert got[0].title == "6 portraits néoréalistes"
    assert got[0].start.hour == 14 and got[0].start.minute == 15
    assert got[0].runtime_minutes == 76


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
