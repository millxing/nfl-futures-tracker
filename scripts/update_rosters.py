#!/usr/bin/env python3
"""Refresh cached ESPN team rosters. Preserve the last complete cache on failure."""
import json
import os
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/data/rosters.json'
BASE = 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams'
# Tracked candidates with names shared by another NFL player. Athlete IDs keep
# these associations correct even when the players change teams.
CANDIDATE_IDS = {'Justin Jefferson': '4262921', 'DeVonta Smith': '4241478', 'Byron Young': '4875196'}


def normalize(name):
    return ''.join(c for c in unicodedata.normalize('NFKD', name).casefold() if c.isalnum())


def fetch(url):
    with urlopen(url, timeout=30) as response:
        return json.load(response)


def roster(entry):
    team = entry['team']
    name = team['displayName']
    url = f"{BASE}/{team['id']}/roster"
    data = fetch(url)
    players = [p['displayName'] for group in data['athletes'] for p in group['items']
               if p['displayName'] not in CANDIDATE_IDS or p['id'] == CANDIDATE_IDS[p['displayName']]]
    coaches = [' '.join([c['firstName'], c['lastName']]) for c in data.get('coach', [])]
    if not players:
        raise ValueError(f'Empty roster: {name}')
    return {'id': team['abbreviation'].lower(), 'name': name, 'players': players, 'coaches': coaches, 'source': url}


def main():
    try:
        teams = fetch(BASE + '?limit=100')['sports'][0]['leagues'][0]['teams']
        with ThreadPoolExecutor(max_workers=6) as pool:
            rosters = sorted(pool.map(roster, teams), key=lambda t: t['name'])
        if len(rosters) != 32:
            raise ValueError(f'Expected 32 teams, got {len(rosters)}')
        markets = json.loads((ROOT / 'docs/data/data.json').read_text())
        candidates = {normalize(m['name']) for m in markets['markets'] if m['series'] not in markets['teamSeries']}
        owners = {}
        for team in rosters:
            for player in team['players']:
                key = normalize(player)
                if key in candidates and key in owners and owners[key] != team['id']:
                    raise ValueError(f'Ambiguous roster membership: {player}')
                owners[key] = team['id']
        data = {'updated': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'), 'teams': rosters}
        tmp = OUT.with_suffix('.tmp')
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
        os.replace(tmp, OUT)
        print(f'Updated {len(rosters)} team rosters')
    except Exception as error:
        if not OUT.exists():
            raise
        print(f'WARNING: keeping cached rosters: {error}', file=sys.stderr)


if __name__ == '__main__':
    main()
