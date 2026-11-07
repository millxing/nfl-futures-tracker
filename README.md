# NFL Futures Tracker

Static GitHub Pages site that shows how each week of NFL games moves Kalshi and Polymarket
implied probabilities for end-of-season outcomes (division winners, playoffs,
Super Bowl, awards). Markets across 19 series, snapshotted before and after
each NFL week.

Site lives in `docs/` (GitHub Pages source). Data pipeline is local.

## Weekly update workflow

1. Create the snapshot xlsx in `snapshots/`
   (filename format: `nfl_markets_snapshot_YYYY-MM-DD_HHMM_EDT.xlsx`).
   Easiest: double-click `snapshot_app/NFL Snapshot.app`, pick the Eastern
   date/time, click **Create Excel snapshot**. It saves straight into
   `snapshots/`. (First launch: Control-click → Open, since it's unsigned.
   Or run `snapshot_app/NFL Snapshot.command` from a terminal.)
   Add a `labels.json` entry for it (see below).
2. Rebuild the JSON:

   ```bash
   python3 scripts/build_data.py
   ```

3. Commit and push:

   ```bash
   git add -A && git commit -m "Add snapshot" && git push
   ```

GitHub Pages redeploys automatically on push.

## Snapshot labels

Each snapshot gets a friendly label from `snapshots/labels.json`; the exact
date/time (from the filename) is preserved and shown alongside it in the UI.
Add an entry for every new snapshot — a plain string, or an object with
`"partial": true` for a mid-week snapshot that predates the week's last game:

```json
{
  "2026-09-10_2000": "Pre Week 1",
  "2026-09-17_0100": { "label": "Mid Week 2", "partial": true },
  "2026-09-18_0100": "Post Week 2"
}
```

Partial snapshots are tagged "(partial)" throughout the site. A snapshot with
no entry falls back to its timestamp label (the build script warns).

## Layout

- `snapshot_app/` — local web app that generates a snapshot xlsx for any Eastern
  date/time from Kalshi + Polymarket history (copied from the KalshiNFL project;
  needs Python 3 and the Codex-bundled Node via the `node_modules` symlink)
- `snapshots/` — raw xlsx snapshot files (both Kalshi and Polymarket sheets are used)
- `scripts/build_data.py` — converts all snapshots to `docs/data/data.json`
- `docs/` — the site: `index.html`, `app.js`, `style.css`, `data/data.json`

## Price sources

The Kalshi / Polymarket / Average selector applies to movers, charts, tooltips,
and tables. Average is the default. Switching sources preserves the row order; changing
the comparison or clicking a sort heading re-sorts using the selected source. Kalshi uses the historical yes bid/ask
midpoint; Average is the equal-weight mean of both sources at the same snapshot.
The build rejects missing or empty Kalshi sheets so future updates cannot silently
drop Kalshi. Both prices are required for Average; missing observations stay blank (never zero
or filled forward). Source-only markets appear in their respective source mode.

All existing snapshot workbooks are rebuilt, so Kalshi history starts at the same
September 10, 2026 snapshot as Polymarket. Markets that opened later retain gaps.
The saved Kalshi sheets do not include division markets. Matching uses explicit
2026-season event mappings, team names, and player aliases; unknown Kalshi events
fail the build instead of silently joining another season.

Validation: `python3 -m unittest discover -s tests -v`.

## Teams and favorites

The Teams tab groups team futures and tracked player/coach awards by current NFL
roster. Team links can be bookmarked (for example, `#teams/buffalo-bills`). Star
a team to follow all its matched markets, or star individual markets from
Weekly Movers, Time Series, or a team page. Favorites are saved in this browser
under `nfl-futures-favorites-v1`, separately from NBA favorites.

Refresh the cached affiliations with `python3 scripts/update_rosters.py`. This
fetches all 32 ESPN NFL rosters and coaches and preserves the previous cache if
a refresh fails. Shared-name candidates are disambiguated using ESPN athlete
IDs; name variations are mapped in `docs/app.js`. Candidates absent from the
current roster cache are still available as individual markets. Historical
award prices follow the person, including time with previous teams.
