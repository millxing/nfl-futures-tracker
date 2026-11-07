#!/usr/bin/env python3
"""Convert snapshot xlsx files into docs/data/data.json for the site.

Usage: python3 scripts/build_data.py
Reads every snapshots/nfl_markets_snapshot_*.xlsx (Kalshi and Polymarket sheets),
sorted chronologically by the datetime in the filename.
Optional snapshots/labels.json maps snapshot id -> friendly label,
e.g. {"2026-09-10_2000": "Pre Week 1"}.
"""

import glob
import json
import os
import re
import sys
from datetime import datetime, timezone

from openpyxl import load_workbook

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAPSHOT_DIR = os.path.join(ROOT, "snapshots")
OUT_PATH = os.path.join(ROOT, "docs", "data", "data.json")
SHEET = "Polymarket series"

# Display order: team series first (macro -> divisions), then individual awards.
SERIES_ORDER = [
    "Pro Football: 2027 Champion",
    "Pro Football: 2027 AFC Champion",
    "Pro Football: 2027 NFC Champion",
    "Pro Football: Team to Make Postseason",
    "Pro Football: AFC East Champion",
    "Pro Football: AFC North Champion",
    "Pro Football: AFC South Champion",
    "Pro Football: AFC West Champion",
    "Pro Football: NFC East Champion",
    "Pro Football: NFC North Champion",
    "Pro Football: NFC South Champion",
    "Pro Football: NFC West Champion",
    "Pro Football: 2026 MVP Winner",
    "Pro Football: 2026-27 AP Offensive Player of the Year Winner",
    "Pro Football: 2026-27 AP Defensive Player of the Year Winner",
    "Pro Football: 2026-27 AP Offensive Rookie of the Year Winner",
    "Pro Football: 2026-27 AP Defensive Rookie of the Year Winner",
    "Pro Football: 2026-27 AP Coach of the Year Winner",
    "Pro Football: 2026-27 AP Comeback Player of the Year Winner",
]
TEAM_SERIES = set(SERIES_ORDER[:12])

# Tracked on Polymarket but too illiquid for prices to read as probabilities.
EXCLUDED_SERIES = {
    "Pro Football: 2026-27 AFC #1 Seed",
    "Pro Football: 2026-27 NFC #1 Seed",
}

# Explicit season mapping prevents future contracts joining this season's prices.
KALSHI_EVENTS = dict(zip(
    ["KXSB-27", "KXNFLAFCCHAMP-27", "KXNFLNFCCHAMP-27", "KXNFLPLAYOFF-27",
     "KXNFLMVP-27", "KXNFLOPOTY-27", "KXNFLDPOTY-27", "KXNFLOROTY-27",
     "KXNFLDROTY-27", "KXNFLCOTY-27", "KXNFLCPOTY-27"],
    SERIES_ORDER[:4] + SERIES_ORDER[12:],
))
NAME_ALIASES = {
    "pat surtain": "Patrick Surtain II",
    "kenneth walker": "Kenneth Walker III",
    "jaxson smithnjigba": "Jaxon Smith-Njigba",
}


def name_key(name):
    key = re.sub(r"[^a-z0-9 ]", "", name.lower())
    return re.sub(r"[^a-z0-9]", "", NAME_ALIASES.get(key, key).lower())


def read_sheet(path, sheet):
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        if sheet not in wb.sheetnames:
            return []
        rows = wb[sheet].iter_rows(values_only=True)
        next(rows)
        next(rows)
        header = next(rows)
        return [dict(zip(header, row)) for row in rows if any(v is not None for v in row)]
    finally:
        wb.close()


def merge_kalshi(path, poly, lookup, team_names):
    result = {mid: {**row, "polymarket": row["price"], "kalshi": None}
              for mid, row in poly.items()}
    seen = set()
    kalshi_rows = read_sheet(path, "Kalshi series")
    if not kalshi_rows:
        raise ValueError(f"Missing or empty Kalshi sheet: {path}")
    for row in kalshi_rows:
        series = KALSHI_EVENTS.get(row["event_ticker"])
        if series is None:
            raise ValueError(f"Unmapped Kalshi event: {row['event_ticker']}")
        name = str(row["outcome"]).strip()
        if series in TEAM_SERIES:
            matches = [team for team in team_names if team.startswith(name + " ") or team == name
                       or (name in ("Los Angeles C", "Los Angeles R", "New York G", "New York J")
                           and team.startswith(name))]
            if len(matches) != 1:
                raise ValueError(f"Ambiguous or unknown Kalshi team: {name}")
            name = matches[0]
        match = lookup.get((series, name_key(name)))
        mid = match[0] if match else "kalshi:" + row["ticker"]
        if mid in seen:
            raise ValueError(f"Duplicate Kalshi match: {mid}")
        seen.add(mid)
        if mid not in result:
            result[mid] = {"series": series, "name": match[1]["name"] if match else name,
                           "question": match[1]["question"] if match else row["market_title"],
                           "polymarket": None, "kalshi": None}
        price = row["midpoint"]
        result[mid]["kalshi"] = round(float(price) * 100, 1) if row["data_status"] == "ok" and price is not None else None
    return result

FNAME_RE = re.compile(
    r"nfl_markets_snapshot_(\d{4}-\d{2}-\d{2})_(\d{4})_E[SD]T\.xlsx$"
)


def snapshot_files():
    files = []
    for path in glob.glob(os.path.join(SNAPSHOT_DIR, "nfl_markets_snapshot_*.xlsx")):
        base = os.path.basename(path)
        if base.startswith("~$"):
            continue
        m = FNAME_RE.search(base)
        if not m:
            print(f"WARNING: skipping unrecognized filename {base}", file=sys.stderr)
            continue
        dt = datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H%M")
        files.append((dt, f"{m.group(1)}_{m.group(2)}", path))
    files.sort()
    return files


def auto_label(dt):
    hour = dt.strftime("%I:%M %p").lstrip("0")
    return f"{dt.strftime('%b %-d')}, {hour} ET"


def read_snapshot(path):
    """Return {market_id: row-dict} for the Polymarket sheet."""
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb[SHEET]
    rows = ws.iter_rows(values_only=True)
    next(rows)  # title
    next(rows)  # created
    header = [str(h) if h is not None else "" for h in next(rows)]
    idx = {name: i for i, name in enumerate(header)}
    out = {}
    for row in rows:
        if row is None or row[idx["market_id"]] is None:
            continue
        if str(row[idx["event_title"]]).strip() in EXCLUDED_SERIES:
            continue
        mid = str(row[idx["market_id"]])
        price = row[idx["price"]]
        status = row[idx["data_status"]]
        out[mid] = {
            "series": str(row[idx["event_title"]]).strip(),
            "name": str(row[idx["outcome"]]).strip(),
            "question": str(row[idx["market_question"]]).strip(),
            "price": round(float(price) * 100, 1)
            if status == "ok" and price is not None
            else None,
        }
    wb.close()
    return out


def main():
    files = snapshot_files()
    if not files:
        sys.exit("No snapshot files found in snapshots/")

    labels = {}
    labels_path = os.path.join(SNAPSHOT_DIR, "labels.json")
    if os.path.exists(labels_path):
        with open(labels_path) as f:
            labels = json.load(f)

    # Match against all snapshots so a market keeps its identity through gaps.
    poly_snapshots = [read_snapshot(path) for _, _, path in files]
    lookup = {}
    team_names = set()
    for snap in poly_snapshots:
        for mid, row in snap.items():
            key = (row["series"], name_key(row["name"]))
            if key in lookup and lookup[key][0] != mid:
                raise ValueError(f"Ambiguous Polymarket match: {key}")
            lookup[key] = (mid, row)
            if row["series"] in TEAM_SERIES:
                team_names.add(row["name"])

    snapshots = []
    per_snapshot = []
    for file_idx, (dt, sid, path) in enumerate(files):
        # labels.json entry: "Pre Week 1" or {"label": "Mid Week 2", "partial": true}
        entry = labels.get(sid)
        if isinstance(entry, str):
            entry = {"label": entry}
        elif entry is None:
            entry = {}
            print(f"WARNING: no labels.json entry for {sid}; using timestamp label", file=sys.stderr)
        snapshots.append(
            {
                "id": sid,
                "label": entry.get("label", auto_label(dt)),
                "time": auto_label(dt),
                "partial": bool(entry.get("partial")),
                "et": dt.strftime("%Y-%m-%d %H:%M"),
            }
        )
        per_snapshot.append(merge_kalshi(path, poly_snapshots[file_idx], lookup, team_names))
        print(f"  {sid}: {len(per_snapshot[-1])} markets")

    # Collect all markets across snapshots; metadata from latest appearance.
    meta = {}
    for snap in per_snapshot:
        for mid, row in snap.items():
            meta[mid] = row

    series_seen = {m["series"] for m in meta.values()}
    unknown = series_seen - set(SERIES_ORDER)
    if unknown:
        print(f"WARNING: series not in SERIES_ORDER (appended): {unknown}", file=sys.stderr)
    series = [s for s in SERIES_ORDER if s in series_seen] + sorted(unknown)
    series_rank = {s: i for i, s in enumerate(series)}

    markets = []
    for mid, m in meta.items():
        markets.append(
            {
                "id": mid,
                "series": m["series"],
                "name": m["name"],
                "question": m["question"],
                "prices": {source: [snap.get(mid, {}).get(source) for snap in per_snapshot]
                           for source in ("polymarket", "kalshi")},
            }
        )
    markets.sort(key=lambda m: (series_rank[m["series"]], m["name"]))

    data = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "snapshots": snapshots,
        "series": series,
        "teamSeries": sorted(TEAM_SERIES & series_seen, key=series_rank.get),
        "markets": markets,
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(data, f, separators=(",", ":"))

    print(f"Wrote {OUT_PATH}")
    print(f"  snapshots: {len(snapshots)}")
    print(f"  series:    {len(series)}")
    print(f"  markets:   {len(markets)}")


if __name__ == "__main__":
    main()
