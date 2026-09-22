# NFL Futures Tracker

Static GitHub Pages site that shows how each week of NFL games moves Polymarket's
implied probabilities for end-of-season outcomes (division winners, playoffs,
Super Bowl, awards). 298 markets across 21 series, snapshotted before and after
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
- `snapshots/` — raw xlsx snapshot files (Polymarket sheet is used; Kalshi ignored)
- `scripts/build_data.py` — converts all snapshots to `docs/data/data.json`
- `docs/` — the site: `index.html`, `app.js`, `style.css`, `data/data.json`
