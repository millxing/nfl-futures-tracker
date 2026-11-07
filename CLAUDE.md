# NFL Futures Tracker: agent notes

Static GitHub Pages site (`docs/`, served from `main`) showing how Kalshi and Polymarket NFL
futures move each week. Repo: github.com/millxing/nfl-futures-tracker.
See `README.md` for layout and the manual workflow. This file is the playbook
for the recurring "do the week N update" request.

## Weekly update: what to do

Each NFL week gets exactly two snapshots, all times Eastern:

| Snapshot | Timestamp | Label |
|---|---|---|
| Pre | Thursday of that week, 8:00 PM | `Pre Week N` |
| Post | Tuesday after, 1:00 AM (i.e. just after Monday night ends) | `Post Week N` |

Examples: Week 5 = `2026-10-08_2000` and `2026-10-13_0100`; Week 6 =
`2026-10-15_2000` and `2026-10-20_0100`. Check the date of the latest entry in
`snapshots/labels.json` to find the next week. If the user gives explicit times,
use theirs. If a week's pattern differs (bye weeks, Thursday game moved, holiday
schedule), ask or state the assumption in the final message.

Historical prices can be pulled for any past time, so a missing Pre snapshot can
be backfilled after the fact. If the user asks for a mid-week snapshot (e.g.
Monday morning), label it `{"label": "Mid Week N", "partial": true}`, and when
the Post snapshot is created, delete the mid-week file and its label entry.

## Steps

1. Generate each workbook headless (about 1 minute each, needs Python 3 and the
   Codex-bundled Node via the gitignored `snapshot_app/node_modules` symlink):

   ```bash
   cd snapshot_app && python3 - <<'EOF'
   import sys; sys.path.insert(0, '.')
   import nfl_snapshot_app as app
   for t in ("YYYY-MM-DDTHH:MM", "YYYY-MM-DDTHH:MM"):
       snap = app.parse_snapshot_time(t)
       dest = app.output_path(snap)
       assert not dest.exists(), dest
       r = app.build_snapshot(snap, dest)
       print(r["filename"], "Kalshi:", r["kalshi_rows"], "missing:", r["kalshi_missing"],
             "Polymarket:", r["polymarket_rows"], "missing:", r["polymarket_missing"])
   EOF
   ```

   Both sources are required on every update. Expect at least 452 Kalshi rows and
   298 Polymarket rows with 0 missing observations (counts may grow as markets open).
   Investigate missing observations before publishing. Output lands in `snapshots/`.
2. Add one entry per snapshot to `snapshots/labels.json`
   (`"YYYY-MM-DD_HHMM": "Pre Week N"`).
3. `python3 scripts/build_data.py` and confirm: snapshot count went up by two (or one when replacing a partial),
   Polymarket still has 266 markets, labels match. A missing label entry only warns, so check.
4. Compare the last two snapshots in `docs/data/data.json` (source price arrays are percent,
   one decimal). Check both `prices.kalshi` and `prices.polymarket` against the
   source sheets; unmatched markets legitimately have nulls for one source. Run
   `python3 -m unittest discover -s tests -v` and sanity-check the top movers.
5. For a data-only update, commit the new xlsx files, removed partial snapshot, `labels.json` and `docs/data/data.json`, then
   push to `main` (or merge the update PR). Include feature changes when requested.
   Pages redeploys on push.
6. Report top movers using full series names (e.g. "Offensive Rookie of the
   Year", not a truncated column). Say which assumptions you made.

## Gotchas

- Both source sheets are used. Kalshi uses midpoints; Average requires both source
  observations. Kalshi event mappings are season-specific in `scripts/build_data.py`.
  All 19 displayed categories, including all eight divisions, are required for
  both exchanges. The data build rejects missing category coverage and incomplete
  team fields. Award candidate lists differ between exchanges; do not invent
  prices for unmatched candidates. AFC/NFC #1 Seed series remain excluded (too illiquid).
- Filename tz is `EDT` or `EST` as the app computes it; the build regex accepts both.
- Stray or test xlsx files in `snapshots/` get published as extra points on the
  site. Move them out before building.
- Under auto mode, `git rm` and heredoc overwrites of `labels.json` have been
  blocked. Plain `rm` and the Edit tool work.
