# Montréal Cinema Calendar

**Website:** https://k10sj02.github.io/montreal-cinema-calendar/

**Calendar subscription:** https://k10sj02.github.io/montreal-cinema-calendar/montreal-cinema.ics

An automated, subscribable calendar of **individual screenings** at and from:

- Cinéma Beaubien
- Cinéma du Parc
- Cinéma du Musée
- Cinémathèque québécoise
- Cinema Politica Concordia
- Cinéma Public
- Cinéma Moderne
- selected university and microcinema screenings
- seasonal RIDM, FNC, image+nation, FIFA, and outdoor-cinema listings when published

The feed uses the official venue pages, `America/Toronto` local time, stable UIDs, RFC 5545 line folding, published runtimes, source links, language/format/room metadata, and 🆓 `FREE` / 💚 `BY DONATION` labels when the source publishes them. It does not manufacture events or infer a recurring Cinema Politica screening without an individual event page.

## Run locally

Python 3.11 or newer is required.

```sh
python -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
pytest
montreal-cinema-calendar
```

Outputs:

- `public/montreal-cinema.ics` — the subscription feed
- `public/montreal-cinema.json` — health report and per-source errors
- `data/state.json` — prior event state, required for cancellation detection

By default, the generator requests the next 45 days. A source failure retains its previous events instead of falsely cancelling them. An event disappears only after that source was refreshed successfully; the feed then emits the same UID with `STATUS:CANCELLED`. Past events naturally age out.

## Deploy with GitHub Pages

1. Create an empty GitHub repository and push this folder to its `main` branch.
2. In **Settings → Pages → Build and deployment**, select **GitHub Actions**.
3. Run **Actions → Update calendar → Run workflow** once.
4. Subscribe to:

   `https://YOUR-GITHUB-USER.github.io/YOUR-REPOSITORY/montreal-cinema.ics`

The workflow tests and refreshes the calendar every six hours, commits the feed and state history, and deploys `public/` to Pages. Replace the contact URL in `src/montreal_cinema_calendar/http.py` after creating the repository so venue operators can identify the crawler.

## Operational notes

- Cinéma Cinéma publishes all three commercial venues from one Svelte schedule; its stable `representation_id` is used for each event UID.
- Cinema Politica events are discovered from the Concordia local page, then verified on each individual screening page. The listing's “all screenings are by donation” policy is preserved.
- Cinéma Public is read from its official structured schedule. Cinéma Moderne, university/film-club screenings, outdoor cinema and named seasonal festivals are selected from Has Things' Montréal film dataset (ODbL 1.0, attribution included in each event). Blue Sunshine is included whenever a dated listing is published there; no recurring dates are invented.
- Cinémathèque québécoise occasionally returns a Cloudflare block to automated clients. The adapter retries; if it remains blocked, the update is marked degraded and the prior Cinémathèque events remain intact. Check `montreal-cinema.json` after deployment. If GitHub-hosted requests are consistently blocked, ask the venue to allow the documented user agent rather than proxying or copying third-party data.
- A missing runtime means the ICS event has a start but no fabricated end time. Calendar software supports this valid form.

## Useful commands

```sh
# Reproduce a date window
montreal-cinema-calendar --today 2026-10-10 --days 45

# CI health check: fail if any source cannot be refreshed
montreal-cinema-calendar --strict
```

Please keep requests modest. The scheduled job runs only four times daily and reuses the official date pages.

