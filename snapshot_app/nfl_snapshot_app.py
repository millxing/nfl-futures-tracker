#!/usr/bin/env python3
"""Combined local web app for historical Kalshi and Polymarket NFL snapshots."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT.parent / "snapshots"
BUILDER = ROOT / "build_snapshot_workbook.mjs"
KALSHI_API = "https://external-api.kalshi.com/trade-api/v2"
POLY_GAMMA = "https://gamma-api.polymarket.com"
POLY_CLOB = "https://clob.polymarket.com"
EASTERN = ZoneInfo("America/New_York")

KALSHI_SERIES = [
    "KXSB", "KXNFLAFCCHAMP", "KXNFLNFCCHAMP", "KXNFLMVP", "KXNFLOPOTY",
    "KXNFLDPOTY", "KXNFLOROTY", "KXNFLDROTY", "KXNFLCOTY", "KXNFLCPOTY",
    "KXNFLPLAYOFF",
]

POLYMARKET_EVENTS = [
    "pro-football-2027-champion-20260729185915366",
    "pro-football-2027-afc-champion",
    "pro-football-2027-nfc-champion",
    "nfl-team-to-make-postseason",
    "pro-football-2026-27-afc-1-seed",
    "pro-football-2026-27-nfc-1-seed",
    "pro-football-afc-east-champion",
    "pro-football-afc-north-champion",
    "pro-football-afc-south-champion",
    "pro-football-afc-west-champion",
    "pro-football-nfc-east-champion",
    "pro-football-nfc-north-champion",
    "pro-football-nfc-south-champion",
    "pro-football-nfc-west-champion",
    "pro-football-2026-mvp-winner",
    "pro-football-2026-27-ap-offensive-player-of-the-year-winner",
    "pro-football-2026-27-ap-defensive-player-of-the-year-winner",
    "pro-football-2026-27-ap-offensive-rookie-of-the-year-winner",
    "pro-football-2026-27-ap-defensive-rookie-of-the-year-winner",
    "pro-football-2026-27-ap-coach-of-the-year-winner",
    "pro-football-2026-27-ap-comeback-player-of-the-year-winner",
]

KALSHI_COLUMNS = [
    "requested_snapshot_et", "requested_snapshot_timezone", "requested_snapshot_utc",
    "observed_at_utc", "observation_lag_seconds", "series_ticker", "series_title",
    "ticker", "event_ticker", "market_title", "outcome", "data_status", "yes_bid",
    "yes_ask", "midpoint", "last_trade_price", "minute_volume", "open_interest",
    "market_open_time", "market_close_time",
]

POLYMARKET_COLUMNS = [
    "requested_snapshot_et", "requested_snapshot_timezone", "requested_snapshot_utc",
    "observed_at_utc", "observation_lag_seconds", "event_id", "event_slug", "event_title",
    "market_id", "condition_id", "market_slug", "market_question", "outcome", "token_id",
    "data_status", "price", "market_open_time", "market_close_time",
]


def request_json(url: str, query: dict[str, Any] | None = None, attempts: int = 3) -> Any:
    if query:
        url += "?" + urllib.parse.urlencode(query)
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "NFLSnapshot/2.0"})
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            last_error = error
            if attempt + 1 < attempts:
                time.sleep(0.5 * (2**attempt))
    raise RuntimeError(f"Request failed for {url}: {last_error}")


def parse_iso(value: Any, fallback: float) -> float:
    if not value:
        return fallback
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return fallback


def parse_snapshot_time(value: str) -> datetime:
    try:
        naive = datetime.strptime(value, "%Y-%m-%dT%H:%M")
    except ValueError as error:
        raise ValueError("Choose a valid snapshot date and time.") from error
    candidates = [naive.replace(tzinfo=EASTERN, fold=fold) for fold in (0, 1)]
    valid = [candidate for candidate in candidates if candidate.astimezone(timezone.utc).astimezone(EASTERN).replace(tzinfo=None) == naive]
    if not valid:
        raise ValueError("That Eastern time does not exist because of daylight saving time.")
    if len(valid) == 2 and valid[0].utcoffset() != valid[1].utcoffset():
        raise ValueError("That Eastern time is ambiguous because of daylight saving time.")
    return valid[0]


def output_path(snapshot: datetime) -> Path:
    return DATA_DIR / f"nfl_markets_snapshot_{snapshot.strftime('%Y-%m-%d_%H%M')}_{snapshot.tzname()}.xlsx"


def number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def candle_value(candle: dict[str, Any] | None, group: str, key: str) -> float | None:
    if not candle:
        return None
    nested = candle.get(group) or {}
    return number(nested.get(key))


def fetch_kalshi_series(series_ticker: str, target_epoch: int) -> list[dict[str, Any]]:
    try:
        metadata = request_json(f"{KALSHI_API}/series/{urllib.parse.quote(series_ticker)}")
        series_title = (metadata.get("series") or {}).get("title") or series_ticker
    except RuntimeError:
        series_title = series_ticker
    markets: list[dict[str, Any]] = []
    cursor = ""
    while True:
        query: dict[str, Any] = {"series_ticker": series_ticker, "limit": 1000}
        if cursor:
            query["cursor"] = cursor
        payload = request_json(f"{KALSHI_API}/markets", query)
        for market in payload.get("markets", []):
            opened = parse_iso(market.get("open_time") or market.get("created_time"), 0)
            closed = parse_iso(market.get("close_time") or market.get("expiration_time"), float("inf"))
            if opened <= target_epoch < closed:
                markets.append({**market, "_series_ticker": series_ticker, "_series_title": series_title})
        cursor = payload.get("cursor") or ""
        if not cursor:
            break
    return markets


def collect_kalshi(snapshot: datetime) -> list[list[Any]]:
    target_epoch = int(snapshot.timestamp())
    markets: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(fetch_kalshi_series, ticker, target_epoch): ticker for ticker in KALSHI_SERIES}
        for future in as_completed(futures):
            for market in future.result():
                markets[market["ticker"]] = market

    candles: dict[str, dict[str, Any] | None] = {}
    market_list = sorted(markets.values(), key=lambda market: (market["_series_ticker"], market.get("yes_sub_title") or ""))
    for start in range(0, len(market_list), 60):
        chunk = market_list[start : start + 60]
        payload = request_json(f"{KALSHI_API}/markets/candlesticks", {
            "market_tickers": ",".join(market["ticker"] for market in chunk),
            "start_ts": target_epoch - 60,
            "end_ts": target_epoch,
            "period_interval": 1,
            "include_latest_before_start": "true",
        })
        for item in payload.get("markets", []):
            eligible = [c for c in item.get("candlesticks", []) if int(c.get("end_period_ts", 0)) <= target_epoch]
            candles[item["market_ticker"]] = max(eligible, key=lambda c: int(c.get("end_period_ts", 0)), default=None)

    requested_et = snapshot.strftime("%Y-%m-%d %H:%M")
    requested_utc = snapshot.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    rows: list[list[Any]] = []
    for market in market_list:
        candle = candles.get(market["ticker"])
        observed_epoch = int(candle["end_period_ts"]) if candle else None
        bid = candle_value(candle, "yes_bid", "close_dollars")
        ask = candle_value(candle, "yes_ask", "close_dollars")
        midpoint = (bid + ask) / 2 if bid is not None and ask is not None else None
        last = candle_value(candle, "price", "close_dollars")
        if last is None:
            last = candle_value(candle, "price", "previous_dollars")
        values = {
            "requested_snapshot_et": requested_et,
            "requested_snapshot_timezone": snapshot.tzname(),
            "requested_snapshot_utc": requested_utc,
            "observed_at_utc": datetime.fromtimestamp(observed_epoch, timezone.utc).isoformat().replace("+00:00", "Z") if observed_epoch else "",
            "observation_lag_seconds": target_epoch - observed_epoch if observed_epoch else None,
            "series_ticker": market["_series_ticker"], "series_title": market["_series_title"],
            "ticker": market.get("ticker"), "event_ticker": market.get("event_ticker"),
            "market_title": market.get("title"), "outcome": market.get("yes_sub_title"),
            "data_status": "ok" if candle else "no_candlestick", "yes_bid": bid, "yes_ask": ask,
            "midpoint": midpoint, "last_trade_price": last, "minute_volume": number((candle or {}).get("volume_fp")),
            "open_interest": number((candle or {}).get("open_interest_fp")),
            "market_open_time": market.get("open_time"), "market_close_time": market.get("close_time"),
        }
        rows.append([values[column] for column in KALSHI_COLUMNS])
    return rows


def parse_array(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value or "[]")
        return parsed if isinstance(parsed, list) else []
    except (TypeError, json.JSONDecodeError):
        return []


def fetch_polymarket_event(slug: str, target_epoch: int) -> list[dict[str, Any]]:
    event = request_json(f"{POLY_GAMMA}/events/slug/{urllib.parse.quote(slug)}")
    found: list[dict[str, Any]] = []
    for market in event.get("markets", []):
        opened = parse_iso(market.get("startDate") or market.get("createdAt") or event.get("startDate"), 0)
        closed = parse_iso(market.get("endDate") or event.get("endDate"), float("inf"))
        outcomes = parse_array(market.get("outcomes"))
        token_ids = parse_array(market.get("clobTokenIds"))
        yes_index = next((index for index, outcome in enumerate(outcomes) if str(outcome).lower() == "yes"), 0)
        if opened <= target_epoch < closed and yes_index < len(token_ids):
            found.append({**market, "_event_id": event.get("id"), "_event_slug": slug,
                          "_event_title": event.get("title") or slug, "_yes_token": token_ids[yes_index],
                          "_yes_outcome": outcomes[yes_index] if yes_index < len(outcomes) else "Yes"})
    return found


def fetch_polymarket_history(token: str, target_epoch: int) -> tuple[str, dict[str, Any] | None, str | None]:
    received_response = False
    last_error: str | None = None
    for seconds, fidelity in ((3600, 1), (86400, 15), (7 * 86400, 60)):
        try:
            payload = request_json(f"{POLY_CLOB}/prices-history", {
                "market": token, "startTs": target_epoch - seconds, "endTs": target_epoch, "fidelity": fidelity,
            }, attempts=4)
            received_response = True
            eligible = [point for point in payload.get("history", []) if int(point.get("t", 0)) <= target_epoch]
            point = max(eligible, key=lambda item: int(item.get("t", 0)), default=None)
            if point:
                return token, point, None
        except RuntimeError as error:
            last_error = str(error)
    return token, None, None if received_response else last_error


def collect_polymarket(snapshot: datetime) -> list[list[Any]]:
    target_epoch = int(snapshot.timestamp())
    markets: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(fetch_polymarket_event, slug, target_epoch) for slug in POLYMARKET_EVENTS]
        for future in as_completed(futures):
            for market in future.result():
                markets[str(market.get("id"))] = market
    market_list = sorted(markets.values(), key=lambda market: (market["_event_slug"], market.get("groupItemTitle") or market.get("question") or ""))

    history: dict[str, dict[str, Any] | None] = {}
    errors: set[str] = set()
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = [pool.submit(fetch_polymarket_history, str(market["_yes_token"]), target_epoch) for market in market_list]
        for future in as_completed(futures):
            token, point, error = future.result()
            history[token] = point
            if error:
                errors.add(token)

    if errors:
        raise RuntimeError(f"Polymarket history requests failed for {len(errors)} markets; no workbook was written.")

    requested_et = snapshot.strftime("%Y-%m-%d %H:%M")
    requested_utc = snapshot.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    rows: list[list[Any]] = []
    for market in market_list:
        token = str(market["_yes_token"])
        point = history.get(token)
        if not point:
            continue
        observed_epoch = int(point["t"]) if point else None
        values = {
            "requested_snapshot_et": requested_et, "requested_snapshot_timezone": snapshot.tzname(),
            "requested_snapshot_utc": requested_utc,
            "observed_at_utc": datetime.fromtimestamp(observed_epoch, timezone.utc).isoformat().replace("+00:00", "Z") if observed_epoch else "",
            "observation_lag_seconds": target_epoch - observed_epoch if observed_epoch else None,
            "event_id": market.get("_event_id"), "event_slug": market.get("_event_slug"),
            "event_title": market.get("_event_title"), "market_id": market.get("id"),
            "condition_id": market.get("conditionId"), "market_slug": market.get("slug"),
            "market_question": market.get("question"),
            "outcome": market.get("groupItemTitle") or market.get("_yes_outcome"), "token_id": token,
            "data_status": "ok", "price": number(point.get("p")),
            "market_open_time": market.get("startDate"), "market_close_time": market.get("endDate"),
        }
        rows.append([values[column] for column in POLYMARKET_COLUMNS])
    return rows


def node_binary() -> str:
    bundled = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
    if bundled.exists():
        return str(bundled)
    found = shutil.which("node")
    if found:
        return found
    raise RuntimeError("Node.js is required to create the Excel workbook.")


def build_snapshot(snapshot: datetime, destination: Path) -> dict[str, Any]:
    kalshi_rows = collect_kalshi(snapshot)
    polymarket_rows = collect_polymarket(snapshot)
    payload = {
        "metadata": {"snapshot_et": snapshot.strftime("%Y-%m-%d %H:%M %Z"), "created_at_utc": datetime.now(timezone.utc).isoformat()},
        "kalshi": {"columns": KALSHI_COLUMNS, "rows": kalshi_rows},
        "polymarket": {"columns": POLYMARKET_COLUMNS, "rows": polymarket_rows},
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="nfl-snapshot-") as temporary:
        temporary_path = Path(temporary)
        input_path = temporary_path / "snapshot.json"
        output = temporary_path / destination.name
        input_path.write_text(json.dumps(payload), encoding="utf-8")
        completed = subprocess.run([node_binary(), str(BUILDER), str(input_path), str(output)],
                                   capture_output=True, text=True, timeout=240)
        if completed.returncode:
            raise RuntimeError((completed.stderr or completed.stdout or "Workbook creation failed").strip())
        os.replace(output, destination)
    return {
        "path": str(destination), "filename": destination.name,
        "kalshi_rows": len(kalshi_rows), "polymarket_rows": len(polymarket_rows),
        "kalshi_missing": sum(row[KALSHI_COLUMNS.index("data_status")] != "ok" for row in kalshi_rows),
        "polymarket_missing": sum(row[POLYMARKET_COLUMNS.index("data_status")] != "ok" for row in polymarket_rows),
    }


HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>NFL Market Snapshot</title><style>
:root{--ink:#102635;--paper:#f7f5ef;--line:#cbd4d8;--green:#08783f;--purple:#4c54e8;--red:#a12b2b;--muted:#64747d}
*{box-sizing:border-box}body{margin:0;min-width:320px;background:var(--ink);color:var(--ink);font-family:"Avenir Next","Helvetica Neue",Arial,sans-serif}
.shell{width:min(760px,calc(100% - 32px));margin:8vh auto}.brand{color:white;margin:0 0 24px;font:800 clamp(34px,6vw,58px)/1 Georgia,serif;letter-spacing:-.04em}
.card{background:var(--paper);border-radius:8px;box-shadow:0 24px 70px rgba(0,0,0,.3);overflow:hidden}.top{padding:36px 40px 30px;border-bottom:1px solid var(--line)}
.eyebrow{color:var(--muted);font-size:11px;letter-spacing:.14em;text-transform:uppercase}.top h2{margin:8px 0 8px;font:750 25px/1.2 inherit}.top p{margin:0;color:var(--muted);line-height:1.5}
.sources{display:grid;grid-template-columns:1fr 1fr;border-bottom:1px solid var(--line)}.source{padding:20px 40px}.source+ .source{border-left:1px solid var(--line)}
.source strong{display:block;font-size:28px}.source span{color:var(--muted);font-size:12px}.kalshi strong{color:var(--green)}.poly strong{color:var(--purple)}
.action{padding:30px 40px 36px}.field{display:grid;grid-template-columns:1fr auto;gap:12px;margin-top:8px}label{font-weight:750}input{height:52px;padding:10px 14px;border:1px solid #aebcc3;border-radius:5px;background:#fff;font:inherit}
button{min-height:52px;padding:0 24px;border:0;border-radius:5px;background:var(--green);color:#fff;font:750 15px inherit;cursor:pointer}button:hover{background:#066533}button:disabled{opacity:.55;cursor:wait}
.status{display:flex;gap:10px;align-items:flex-start;min-height:42px;margin-top:20px;color:var(--muted);font-size:13px;line-height:1.45}.dot{width:10px;height:10px;margin-top:4px;border-radius:50%;background:#8b9aa2}.busy{background:#b77700;animation:pulse .8s alternate infinite}.ok{background:var(--green)}.error{background:var(--red)}
.path{display:block;margin-top:4px;color:var(--ink);font-family:ui-monospace,Menlo,monospace;font-size:11px;overflow-wrap:anywhere}
dialog{width:min(500px,calc(100% - 32px));padding:0;border:0;border-radius:7px;box-shadow:0 25px 80px rgba(0,0,0,.4)}dialog::backdrop{background:rgba(5,20,29,.65)}.modal{padding:28px}.modal h3{margin:0 0 10px;font-size:22px}.modal p{color:var(--muted);line-height:1.5}.modal-actions{display:flex;justify-content:flex-end;gap:10px;margin-top:24px}.secondary{background:#e8edef;color:var(--ink)}.danger{background:var(--red)}
@keyframes pulse{to{opacity:.35}}@media(max-width:620px){.shell{width:100%;margin:0}.brand{padding:24px 20px;margin:0}.card{border-radius:0}.top,.action,.source{padding-left:22px;padding-right:22px}.field{grid-template-columns:1fr}.sources{grid-template-columns:1fr}.source+.source{border-left:0;border-top:1px solid var(--line)}}
</style></head><body><main class="shell"><h1 class="brand">NFL Market Snapshot</h1><section class="card">
<div class="top"><div class="eyebrow">One moment · two exchanges · one workbook</div><h2>Create a historical snapshot</h2><p>Choose an Eastern date and time. The app collects every configured NFL futures market and saves a two-sheet Excel workbook in the snapshots folder.</p></div>
<div class="sources"><div class="source kalshi"><strong>11</strong><span>Kalshi series</span></div><div class="source poly"><strong>21</strong><span>Polymarket event groups</span></div></div>
<div class="action"><label for="snapshotTime">Snapshot time (ET)</label><div class="field"><input id="snapshotTime" type="datetime-local"><button id="create">Create Excel snapshot</button></div>
<div class="status"><span id="dot" class="dot"></span><div><span id="message">Ready. The workbook will be saved in NFL_Information/snapshots.</span><span id="path" class="path"></span></div></div></div></section></main>
<dialog id="overwrite"><div class="modal"><h3>Replace existing snapshot?</h3><p id="overwriteText"></p><div class="modal-actions"><button id="cancel" class="secondary">Cancel</button><button id="replace" class="danger">Overwrite file</button></div></div></dialog>
<script>(()=>{"use strict";const time=document.querySelector("#snapshotTime"),button=document.querySelector("#create"),dot=document.querySelector("#dot"),message=document.querySelector("#message"),path=document.querySelector("#path"),dialog=document.querySelector("#overwrite"),overwriteText=document.querySelector("#overwriteText");
const now=new Date();now.setMinutes(now.getMinutes()-now.getTimezoneOffset());time.value=now.toISOString().slice(0,16);
function state(kind,text,detail=""){dot.className="dot "+kind;message.textContent=text;path.textContent=detail}
async function create(overwrite=false){if(!time.value)return;button.disabled=true;state("busy","Collecting Kalshi and Polymarket history. This can take a few minutes…");try{const response=await fetch("/snapshot",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({snapshot_time:time.value,overwrite})});const data=await response.json();if(response.status===409){overwriteText.textContent=`${data.filename} already exists in the Data folder.`;dialog.showModal();state("","Existing file found. Choose whether to overwrite it.",data.path);return}if(!response.ok)throw new Error(data.error||`Request failed (${response.status})`);state("ok",`Saved ${data.kalshi_rows.toLocaleString()} Kalshi rows and ${data.polymarket_rows.toLocaleString()} Polymarket rows.`,data.path+` · Missing observations: ${data.kalshi_missing+data.polymarket_missing}`)}catch(error){state("error",error.message)}finally{button.disabled=false}}
button.addEventListener("click",()=>create(false));document.querySelector("#cancel").addEventListener("click",()=>dialog.close());document.querySelector("#replace").addEventListener("click",()=>{dialog.close();create(true)});
const lifecycle=new EventSource("/lifecycle"),heartbeat=()=>fetch("/heartbeat",{method:"POST",cache:"no-store",keepalive:true}).catch(()=>{});heartbeat();setInterval(heartbeat,5000);addEventListener("pagehide",()=>{lifecycle.close();navigator.sendBeacon("/disconnect")});})();</script></body></html>"""


class SnapshotServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], handler: type[BaseHTTPRequestHandler]) -> None:
        super().__init__(address, handler)
        self.page_seen = False
        self.last_heartbeat = time.monotonic()
        self.shutdown_at: float | None = None
        self.lifecycle_lock = threading.Lock()
        self.snapshot_lock = threading.Lock()

    def handle_error(self, request: object, client_address: tuple[str, int]) -> None:
        if isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError)):
            return
        super().handle_error(request, client_address)

    def heartbeat(self) -> None:
        with self.lifecycle_lock:
            self.page_seen = True
            self.last_heartbeat = time.monotonic()
            self.shutdown_at = None

    def disconnect(self) -> None:
        with self.lifecycle_lock:
            self.shutdown_at = time.monotonic() + 8

    def watch_lifecycle(self) -> None:
        while True:
            time.sleep(1)
            with self.lifecycle_lock:
                now = time.monotonic()
                should_stop = self.page_seen and (now - self.last_heartbeat > 90 or (self.shutdown_at is not None and now >= self.shutdown_at))
            if should_stop:
                print("Browser closed; stopping local server.")
                self.shutdown()
                return


class Handler(BaseHTTPRequestHandler):
    server: SnapshotServer

    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/lifecycle":
            self.server.heartbeat()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            try:
                while True:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    time.sleep(2)
            except (BrokenPipeError, ConnectionResetError):
                self.server.disconnect()
            return
        if self.path in {"/", "/index.html"}:
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def do_POST(self) -> None:
        if self.path == "/heartbeat":
            self.server.heartbeat()
            self.send_response(204)
            self.end_headers()
            return
        if self.path == "/disconnect":
            self.server.disconnect()
            self.send_response(204)
            self.end_headers()
            return
        if self.path != "/snapshot":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            request = json.loads(self.rfile.read(length) or b"{}")
            snapshot = parse_snapshot_time(str(request.get("snapshot_time", "")))
            destination = output_path(snapshot)
            if destination.exists() and not request.get("overwrite"):
                self.send_json(409, {"exists": True, "filename": destination.name, "path": str(destination)})
                return
            if not self.server.snapshot_lock.acquire(blocking=False):
                self.send_json(409, {"error": "A snapshot is already being created."})
                return
            try:
                result = build_snapshot(snapshot, destination)
            finally:
                self.server.snapshot_lock.release()
            self.send_json(200, result)
        except (ValueError, RuntimeError, subprocess.SubprocessError) as error:
            self.send_json(500, {"error": str(error)})
        except Exception as error:
            self.send_json(500, {"error": f"Unexpected error: {error}"})

    def log_message(self, format: str, *args: object) -> None:
        print("%s - %s" % (self.log_date_time_string(), format % args), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the combined NFL market snapshot app.")
    parser.add_argument("--port", type=int, default=0, help="Local port; defaults to an available port")
    parser.add_argument("--no-open", action="store_true", help="Do not open the browser automatically")
    args = parser.parse_args()
    if not BUILDER.exists():
        raise SystemExit(f"Missing workbook builder: {BUILDER}")
    server = SnapshotServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"NFL Market Snapshot running at {url}", flush=True)
    print("The server will stop when the browser closes.", flush=True)
    threading.Thread(target=server.watch_lifecycle, daemon=True).start()
    if not args.no_open:
        threading.Timer(0.35, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
