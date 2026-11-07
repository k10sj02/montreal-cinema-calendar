from datetime import date

from montreal_cinema_calendar.sources.cinemaclock import CinemaClockSource


HTML = """
<script type="application/ld+json">
{"@type":"MovieTheater","name":"Cineplex Forum & VIP","address":{"streetAddress":"2313 Ste-Catherine Ouest","addressLocality":"Montréal","addressRegion":"QC","postalCode":"H3H 1N2"}}
</script>
<div class="showtimeblock movie">
  <h3 class="movietitle"><a href="/movies/wicker-2026">Wicker</a></h3>
  <span class="movietitleother"><i class="subt">English</i></span>
  <p class="moviegenre"><span class="rtQC">13+</span>1h45m Drama</p>
  <div class="filall">
    <p class="timesalso">Standard auditorium</p>
    <p class="timesalso ccad">Optional: Closed Captions</p>
    <p class="times"><u>Today <span class="timesdate">Nov 6</span></u><i><span class="tix tod" data-time="2210" id="tix23105180036250043">10:10</span></i></p>
    <p class="timesother"><s><u>Sat <span class="timesdate">Nov 7</span></u><i><span class="tix" data-time="1310" id="tix-next">1:10</span></i></s></p>
  </div>
</div>
"""


def test_parses_cinemaclock_same_day_showtime():
    source = CinemaClockSource(None)
    events, covered = source._parse_theatre(
        "/movie-theaters/cineplex-forum-vip", HTML,
        {(11, 6): date(2026, 11, 6)},
    )
    assert covered == [date(2026, 11, 6)]
    assert len(events) == 1
    event = events[0]
    assert event.title == "Wicker"
    assert event.start.isoformat() == "2026-11-06T22:10:00-05:00"
    assert event.source_id == "tix23105180036250043"
    assert event.runtime_minutes == 105
    assert event.venue == "Cineplex Forum & VIP"
    assert event.language == "English"
    assert event.format == "Standard auditorium · Optional: Closed Captions"
    assert "Québec rating: 13+" in event.description
