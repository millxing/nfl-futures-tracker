"""Verify historical source coverage and conservative market matching."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_data as build
sys.path.insert(0, str(ROOT / "snapshot_app"))
import nfl_snapshot_app as collector


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

    def test_collector_includes_every_mapped_category(self):
        self.assertEqual({event.rsplit('-', 1)[0] for event in build.KALSHI_EVENTS},
                         set(collector.KALSHI_SERIES))

    def test_all_categories_have_both_sources_in_every_snapshot(self):
        data = json.loads((ROOT / 'docs/data/data.json').read_text())
        self.assertEqual(set(build.KALSHI_EVENTS.values()), set(build.SERIES_ORDER))
        for i, snapshot in enumerate(data['snapshots']):
            rows = {m['id']: {'series': m['series'], **{source: m['prices'][source][i]
                    for source in ('kalshi', 'polymarket')}} for m in data['markets']}
            build.validate_coverage(rows, snapshot['id'])

    def test_coverage_rejects_partial_division_and_missing_award(self):
        rows = {}
        for i, series in enumerate(build.SERIES_ORDER):
            count = 4 if 4 <= i < 12 else 16 if i in (1, 2) else 32 if i < 4 else 1
            for j in range(count):
                rows[f'{i}:{j}'] = {'series': series, 'kalshi': 0, 'polymarket': 0}
        build.validate_coverage(rows, 'test')
        rows['4:0']['kalshi'] = None
        with self.assertRaisesRegex(ValueError, 'kalshi.*AFC East'):
            build.validate_coverage(rows, 'test')
        rows['4:0']['kalshi'] = 0
        rows['12:0']['polymarket'] = None
        with self.assertRaisesRegex(ValueError, 'polymarket.*MVP'):
            build.validate_coverage(rows, 'test')

    def test_aliases(self):
        for a, b in [('Pat Surtain', 'Patrick Surtain II'), ('Kenneth Walker', 'Kenneth Walker III'),
                     ('C.J. Stroud', 'CJ Stroud'), ('Jaxson Smith-Njigba', 'Jaxon Smith-Njigba')]:
            self.assertEqual(build.name_key(a), build.name_key(b))
        self.assertNotEqual(build.name_key('Josh Allen'), build.name_key('Josh Hines-Allen'))


if __name__ == '__main__':
    unittest.main()
