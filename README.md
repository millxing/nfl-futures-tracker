# NFL Futures Tracker

Static GitHub Pages site that shows how each week of NFL games moves Polymarket's
implied probabilities for end-of-season outcomes (division winners, playoffs,
Super Bowl, awards). 298 markets across 21 series, snapshotted before and after
each NFL week.

Site lives in `docs/` (GitHub Pages source). Data pipeline is local.

## Weekly update workflow

1. Drop the new snapshot xlsx into `snapshots/`
   (filename format: `nfl_markets_snapshot_YYYY-MM-DD_HHMM_EDT.xlsx`).
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

Snapshots are auto-labeled from the filename date/time ("Sep 10, 8:00 PM ET").
To use friendly labels ("Pre Week 1"), create `snapshots/labels.json`:

```json
{
  "2026-09-10_2000": "Pre Week 1",
  "2026-09-14_0100": "After Week 1 SNF"
}
```

## Layout

- `snapshots/` — raw xlsx snapshot files (Polymarket sheet is used; Kalshi ignored)
- `scripts/build_data.py` — converts all snapshots to `docs/data/data.json`
- `docs/` — the site: `index.html`, `app.js`, `style.css`, `data/data.json`
