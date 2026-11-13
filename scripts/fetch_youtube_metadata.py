#!/usr/bin/env python3
"""Cache authentic YouTube video publication dates for SEO pages (stdlib only)."""
import json
import os
from pathlib import Path
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
VIDEOS = ROOT / 'data/videos.json'
CACHE = ROOT / 'data/youtube_metadata.json'
VALID_ID = re.compile(r'^[A-Za-z0-9_-]{11}$')
LIMIT = 200


def main():
    key = os.environ.get('YOUTUBE_API_KEY', '').strip()
    if not key:
        raise SystemExit('YOUTUBE_API_KEY is missing from the environment')
    data = json.loads(VIDEOS.read_text(encoding='utf-8'))
    videos = [v for v in data['videos'] if VALID_ID.fullmatch(v.get('id', '')) and v.get('count', 0) >= 2]
    videos.sort(key=lambda v: (-v['count'], -v['points'], v['id']))
    ids = [v['id'] for v in videos[:LIMIT]]
    cache = json.loads(CACHE.read_text(encoding='utf-8')) if CACHE.exists() else {}
    missing = [vid for vid in ids if not isinstance(cache.get(vid), dict) or not cache[vid].get('publishedAt')]
    updated = 0
    for offset in range(0, len(missing), 50):
        batch = missing[offset:offset + 50]
        params = urlencode({'part': 'snippet', 'id': ','.join(batch), 'key': key})
        req = Request('https://www.googleapis.com/youtube/v3/videos?' + params,
                      headers={'User-Agent': 'HNVideoArchive/1.0'})
        with urlopen(req, timeout=40) as response:
            result = json.load(response)
        for item in result.get('items', []):
            published = item.get('snippet', {}).get('publishedAt')
            if published:
                cache[item['id']] = {'publishedAt': published}
                updated += 1
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    print(f'YouTube dates added: {updated}; cached: {len(cache)}; selected: {len(ids)}')


if __name__ == '__main__':
    main()
