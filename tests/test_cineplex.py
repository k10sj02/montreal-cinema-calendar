from datetime import date

from montreal_cinema_calendar.sources.cineplex import CineplexForumSource


class FakeFetcher:
    def __init__(self, payload):
        self.payload = payload
        self.request = None

    def get_json(self, url, *, headers=None):
        self.request = (url, headers)
        return self.payload


def test_forum_showtime_metadata_and_stable_session_id():
    fetcher = FakeFetcher([{
        "theatre": "Cinéma Cineplex Forum et VIP",
        "theatreId": 9109,
        "dates": [{
            "startDate": "2026-11-06T00:00:00",
            "movies": [{
                "id": 61767,
                "name": "Wicker",
                "runtimeInMinutes": 105,
                "localRating": "13ans+",
                "warnings": ["Sexual Content"],
                "language": "English",
                "detailPageUrl": "https://www.cineplex.com/movie/wicker",
                "experiences": [{
                    "experienceTypes": ["Recliner"],
                    "isCcEnabled": True,
                    "isDsEnabled": False,
                    "sessions": [{
                        "vistaSessionId": 123456,
                        "showStartDateTime": "2026-11-06T22:10:00",
                        "auditorium": "Cinema 4",
                        "ticketingUrl": "https://tickets.example/123456",
                    }],
                }],
            }],
        }],
    }])

    source = CineplexForumSource(fetcher)
    events = source.fetch([date(2026, 11, 6)])

    assert len(events) == 1
    event = events[0]
    assert event.title == "Wicker"
    assert event.source_id == "123456"
    assert event.start.isoformat() == "2026-11-06T22:10:00-05:00"
    assert event.runtime_minutes == 105
    assert event.language == "English"
    assert event.format == "Recliner, CC"
    assert event.room == "Cinema 4"
    assert "Rating: 13ans+" in event.description
    assert source.coverage_end == date(2026, 11, 6)
    assert fetcher.request[1]["Ocp-Apim-Subscription-Key"]


def test_forum_ignores_dates_outside_requested_window():
    fetcher = FakeFetcher([{
        "theatreId": 9109,
        "dates": [{"startDate": "2027-01-01T00:00:00", "movies": []}],
    }])
    source = CineplexForumSource(fetcher)
    assert source.fetch([date(2026, 11, 6)]) == []
    assert source.coverage_end == date(2027, 1, 1)
