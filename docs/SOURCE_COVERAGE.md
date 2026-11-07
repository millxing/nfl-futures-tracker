# Source coverage audit

Verified on 2026-11-07. Covers all 17 saved snapshots, Pre Week 1 through Pre Week 9.

All 19 displayed categories have observations from both exchanges at every snapshot. All 128 team outcomes are complete for both sources at every date. Individual award candidate pools differ between exchanges; missing candidate observations remain null, never zero-filled.

| Category | Kalshi outcomes at latest snapshot | Polymarket outcomes at latest snapshot | Both sources at all 17 snapshots |
| --- | ---: | ---: | --- |
| 2027 Champion | 32 | 32 | Yes |
| 2027 AFC Champion | 16 | 16 | Yes |
| 2027 NFC Champion | 16 | 16 | Yes |
| Team to Make Postseason | 32 | 32 | Yes |
| AFC East Champion | 4 | 4 | Yes |
| AFC North Champion | 4 | 4 | Yes |
| AFC South Champion | 4 | 4 | Yes |
| AFC West Champion | 4 | 4 | Yes |
| NFC East Champion | 4 | 4 | Yes |
| NFC North Champion | 4 | 4 | Yes |
| NFC South Champion | 4 | 4 | Yes |
| NFC West Champion | 4 | 4 | Yes |
| 2026 MVP Winner | 49 | 29 | Yes |
| 2026-27 AP Offensive Player of the Year Winner | 69 | 42 | Yes |
| 2026-27 AP Defensive Player of the Year Winner | 72 | 39 | Yes |
| 2026-27 AP Offensive Rookie of the Year Winner | 40 | 5 | Yes |
| 2026-27 AP Defensive Rookie of the Year Winner | 40 | 8 | Yes |
| 2026-27 AP Coach of the Year Winner | 33 | 9 | Yes |
| 2026-27 AP Comeback Player of the Year Winner | 21 | 6 | Yes |

## Backfill and validation

- Added 32 Kalshi division outcomes at each original timestamp: 544 observations, using bid/ask midpoints from the latest eligible one-minute candle at or before the requested time.
- Preserved every pre-existing workbook cell value and all previously published observations.
- Latest Kalshi API inventory contains 452 eligible markets across the 19 tracked categories, all present in the latest workbook after the backfill.
- Checked all 270 additional Polymarket entries omitted from the latest workbook against the existing historical-price lookup (up to seven days before that snapshot). None returned a historical observation; no request failed. These are predominantly Other and placeholder Player/Coach entries.
- Polymarket workbooks retain the two #1 Seed categories; those remain intentionally excluded from the displayed tracker because of illiquidity.
- The data build now rejects missing source/category coverage and incomplete team fields. Zero prices are valid observations.
- The UI keeps the selected exchange when viewing divisions. Average requires both source observations.

Sources: [Kalshi API](https://external-api.kalshi.com/trade-api/v2/markets), [Polymarket metadata API](https://gamma-api.polymarket.com), and [Polymarket historical prices](https://clob.polymarket.com/prices-history). Raw observations and their timestamps are in the snapshot workbooks.
