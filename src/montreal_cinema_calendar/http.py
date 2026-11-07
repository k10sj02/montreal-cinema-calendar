from __future__ import annotations

import time
import httpx

USER_AGENT = (
    "MontrealCinemaCalendar/1.0 (+https://github.com/k10sj02/montreal-cinema-calendar; "
    "public cultural schedule index)"
)


class Fetcher:
    def __init__(self, timeout: float = 30.0, attempts: int = 3):
        self.attempts = attempts
        self.client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "fr-CA,fr;q=0.9,en;q=0.7"},
        )

    def get(self, url: str, *, headers: dict[str, str] | None = None) -> str:
        return self._request(url, headers=headers).text

    def get_json(self, url: str, *, headers: dict[str, str] | None = None):
        return self._request(url, headers=headers).json()

    def _request(self, url: str, *, headers: dict[str, str] | None = None) -> httpx.Response:
        last: Exception | None = None
        for attempt in range(self.attempts):
            try:
                response = self.client.get(url, headers=headers)
                response.raise_for_status()
                if "cloudflare" in response.text[:7000].lower() and "blocked" in response.text[:7000].lower():
                    raise RuntimeError(f"Cloudflare blocked {url}")
                return response
            except Exception as exc:
                last = exc
                if attempt + 1 < self.attempts:
                    time.sleep(2**attempt)
        raise RuntimeError(f"Unable to fetch {url}: {last}") from last

