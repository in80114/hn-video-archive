#!/usr/bin/env python3
"""Build a resumable HN YouTube-video index from Algolia's public HN API.

Historical backfill: python scripts/index_hn.py --mode backfill
Daily updates:     python scripts/index_hn.py --mode recent --days 4
No external dependencies. Network access required when running.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlparse, parse_qs, urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
STATE = DATA / 'index_state.json'
POSTS = DATA / 'posts.json'
OUTPUT = DATA / 'videos.json'
API = 'https://hn.algolia.com/api/v1/search_by_date'
VIDEO_ID = re.compile(r'^[A-Za-z0-9_-]{11}$')
QUERIES = ['youtube.com', 'youtu.be', 'youtube-nocookie.com']
CATEGORIES = [
 ('AI', r'\b(ai|llm|neural|machine learning|deep learning|gpt|transformer)\b'),
 ('程式設計', r'\b(programming|coding|software|compiler|linux|javascript|python|rust|computer science)\b'),
 ('創業', r'\b(startup|founder|business|entrepreneur|company)\b'),
 ('科學', r'\b(physics|math|science|biology|space|astronomy)\b'),
 ('演講', r'\b(lecture|talk|keynote|interview|presentation)\b'),
]

def video_id(url):
    try:
        u = urlparse(url)
        host = (u.hostname or '').lower()
        if host in ('youtu.be', 'www.youtu.be'):
            value = u.path.strip('/').split('/')[0]
        elif host in ('youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com', 'youtube-nocookie.com', 'www.youtube-nocookie.com'):
            parts = u.path.strip('/').split('/')
            if parts[0] == 'watch':
                value = parse_qs(u.query).get('v', [''])[0]
            elif parts[0] in ('embed', 'shorts', 'live', 'v') and len(parts) > 1:
                value = parts[1]
            else:
                return None
        else:
            return None
        return value if VIDEO_ID.fullmatch(value) else None
    except (ValueError, TypeError):
        return None

def category(title):
    for name, pattern in CATEGORIES:
        if re.search(pattern, title or '', flags=re.I):
            return name
    return '科技'

def read_json(path, default):
    if not path.exists():
        return default
    with path.open(encoding='utf-8') as f:
        return json.load(f)

def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    with temp.open('w', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
        f.write('\n')
    os.replace(temp, path)

def request(params, retries=5):
    url = API + '?' + urlencode(params)
    for attempt in range(retries):
        try:
            with urlopen(Request(url, headers={'User-Agent': 'HNVideoArchive/1.0 (public archive indexer)'}), timeout=30) as response:
                return json.load(response)
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(min(2 ** attempt * 2, 30))

def intervals(start, end, days):
    cursor = start
    while cursor < end:
        nxt = min(cursor + dt.timedelta(days=days), end)
        yield cursor, nxt
        cursor = nxt

def ingest(posts, hit):
    hn_id = str(hit.get('objectID') or '')
    vid = video_id(hit.get('url') or '')
    if not hn_id or not vid:
        return
    posts[hn_id] = {
        'hn_id': hn_id, 'video_id': vid,
        'title': str(hit.get('title') or '')[:500],
        'points': int(hit.get('points') or 0),
        'created_at_i': int(hit.get('created_at_i') or 0),
    }

def scan_window(posts, start, end, query, max_pages, delay):
    """Return True only if every result page was processed.

    Split oversized windows recursively to avoid Algolia's deep pagination limit.
    """
    start_i, end_i = int(start.timestamp()), int(end.timestamp())
    params = {'query': query, 'tags': 'story', 'numericFilters': f'created_at_i>={start_i},created_at_i<{end_i}', 'hitsPerPage': 100}
    first = request({**params, 'page': 0})
    total_pages = int(first.get('nbPages') or 0)
    if total_pages > max_pages:
        if (end - start) <= dt.timedelta(hours=1):
            raise RuntimeError(f'Window exceeds pagination limit even at 1h: {start} {query} ({total_pages} pages). Manual intervention required.')
        mid = start + (end - start) / 2
        scan_window(posts, start, mid, query, max_pages, delay)
        scan_window(posts, mid, end, query, max_pages, delay)
        return True
    for page in range(total_pages):
        data = first if page == 0 else request({**params, 'page': page})
        for hit in data.get('hits', []):
            ingest(posts, hit)
        if delay:
            time.sleep(delay)
    return True

def build(posts, state):
    groups = {}
    for p in posts.values():
        groups.setdefault(p['video_id'], []).append(p)
    videos = []
    for vid, sources in groups.items():
        if len(sources) < 2:
            continue
        ranked = sorted(sources, key=lambda p: (-p['points'], -p['created_at_i']))
        videos.append({
            'id': vid, 'title': ranked[0]['title'] or '未命名影片',
            'category': category(' '.join(p['title'] for p in ranked[:5])),
            'count': len(sources), 'points': sum(max(0, p['points']) for p in sources),
            'first_seen': min(p['created_at_i'] for p in sources),
            'last_seen': max(p['created_at_i'] for p in sources),
            'posts': [{'id': p['hn_id'], 'title': p['title'], 'points': p['points'], 'created_at_i': p['created_at_i']} for p in ranked],
        })
    videos.sort(key=lambda v: (-v['count'], -v['points'], v['id']))
    result = {'metadata': {'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'min_posts': 2, 'post_count': len(posts), 'video_count': len(videos), 'backfill_complete': bool(state.get('backfill_complete')), 'scope': 'HN story URLs matching YouTube domains; not comments or text-only links', 'methodology': 'Distinct HN story IDs grouped by normalized YouTube video ID'}, 'videos': videos}
    write_json(OUTPUT, result)
    return len(videos)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['backfill', 'recent', 'build'], default='recent')
    parser.add_argument('--days', type=int, default=4, help='Recent overlap window in days')
    parser.add_argument('--window-days', type=int, default=30)
    parser.add_argument('--max-pages', type=int, default=8)
    parser.add_argument('--delay', type=float, default=0.15)
    parser.add_argument('--max-windows', type=int, default=0, help='Limit new backfill windows for CI runs; 0 means all')
    args = parser.parse_args()
    posts = read_json(POSTS, {})
    state = read_json(STATE, {'completed': [], 'backfill_complete': False})
    if args.mode == 'build':
        print('Videos:', build(posts, state))
        return
    now = dt.datetime.now(dt.timezone.utc)
    start = dt.datetime(2007, 2, 1, tzinfo=dt.timezone.utc) if args.mode == 'backfill' else now - dt.timedelta(days=args.days)
    end = dt.datetime(now.year, now.month, 1, tzinfo=dt.timezone.utc) if args.mode == 'backfill' else now
    windows = list(intervals(start, end, args.window_days))
    count = 0
    for a, b in windows:
        for query in QUERIES:
            key = f'{a.isoformat()}|{b.isoformat()}|{query}'
            if args.mode == 'backfill' and key in state['completed']:
                continue
            print(f'Scanning {a.date()}..{b.date()} {query}', flush=True)
            scan_window(posts, a, b, query, args.max_pages, args.delay)
            if args.mode == 'backfill':
                state['completed'].append(key)
            write_json(POSTS, posts)
            write_json(STATE, state)
        count += 1
        if args.max_windows and count >= args.max_windows:
            break
    if args.mode == 'backfill' and all(f'{a.isoformat()}|{b.isoformat()}|{q}' in state['completed'] for a, b in windows for q in QUERIES):
        state['backfill_complete'] = True
    write_json(STATE, state)
    print('Videos:', build(posts, state))

if __name__ == '__main__':
    main()
