"""Verify historical source coverage and conservative market matching."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_data as build


class SourceHistoryTests(unittest.TestCase):
    def test_all_historical_observations_preserved(self):
        data = json.loads((ROOT / 'docs/data/data.json').read_text())
        by_id = {m['id']: m for m in data['markets']}
        for i, (_, sid, path) in enumerate(build.snapshot_files()):
            self.assertEqual(data['snapshots'][i]['id'], sid)
            poly = build.read_snapshot(path)
            for mid, row in poly.items():
                self.assertEqual(by_id[mid]['prices']['polymarket'][i], row['price'])
            raw = build.read_sheet(path, 'Kalshi series')
            expected = sorted(round(r['midpoint'] * 100, 1) for r in raw
                              if r['data_status'] == 'ok' and r['midpoint'] is not None)
            actual = sorted(m['prices']['kalshi'][i] for m in data['markets']
                            if m['prices']['kalshi'][i] is not None)
            self.assertEqual(actual, expected, sid)

    def test_matching_and_missing_midpoint(self):
        series = build.SERIES_ORDER[0]
        meta = {'series': series, 'name': 'Los Angeles Chargers', 'question': 'Win?', 'price': 0}
        row = {'event_ticker': 'KXSB-27', 'outcome': 'Los Angeles C', 'ticker': 'KXSB-27-LAC',
               'market_title': 'Win?', 'data_status': 'ok', 'midpoint': 0}
        lookup = {(series, build.name_key(meta['name'])): ('123', meta)}
        with patch.object(build, 'read_sheet', return_value=[row]):
            merged = build.merge_kalshi('', {'123': meta}, lookup, {'Los Angeles Chargers', 'Los Angeles Rams'})
            self.assertEqual(merged['123']['kalshi'], 0)
            row['midpoint'] = None
            self.assertIsNone(build.merge_kalshi('', {}, lookup, {'Los Angeles Chargers'})['123']['kalshi'])
            row['event_ticker'] = 'KXSB-28'
            with self.assertRaises(ValueError):
                build.merge_kalshi('', {}, lookup, set())

    def test_missing_kalshi_is_rejected(self):
        with patch.object(build, 'read_sheet', return_value=[]):
            with self.assertRaisesRegex(ValueError, 'Missing or empty Kalshi'):
                build.merge_kalshi('snapshot.xlsx', {}, {}, set())

    def test_aliases(self):
        for a, b in [('Pat Surtain', 'Patrick Surtain II'), ('Kenneth Walker', 'Kenneth Walker III'),
                     ('C.J. Stroud', 'CJ Stroud'), ('Jaxson Smith-Njigba', 'Jaxon Smith-Njigba')]:
            self.assertEqual(build.name_key(a), build.name_key(b))
        self.assertNotEqual(build.name_key('Josh Allen'), build.name_key('Josh Hines-Allen'))


if __name__ == '__main__':
    unittest.main()
