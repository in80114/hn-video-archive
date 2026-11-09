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
    if args.window_days <= 0 or args.days <= 0 or args.max_pages <= 0 or args.max_windows < 0:
        parser.error('days, window-days and max-pages must be positive; max-windows must be nonnegative')
    posts = read_json(POSTS, {})
    state = read_json(STATE, {'completed': [], 'backfill_complete': False})
    if args.mode == 'build':
        print('Videos:', build(posts, state))
        return
    now = dt.datetime.now(dt.timezone.utc)
    start = dt.datetime(2007, 2, 1, tzinfo=dt.timezone.utc) if args.mode == 'backfill' else now - dt.timedelta(days=args.days)
    end = dt.datetime(now.year, now.month, 1, tzinfo=dt.timezone.utc) if args.mode == 'backfill' else now
    windows = list(intervals(start, end, args.window_days))
    completed = set(state.get('completed', []))
    count = 0
    for a, b in windows:
        pending = [q for q in QUERIES if f'{a.isoformat()}|{b.isoformat()}|{q}' not in completed] if args.mode == 'backfill' else QUERIES
        if not pending:
            continue
        if args.mode == 'backfill' and args.max_windows and count >= args.max_windows:
            break
        for query in pending:
            key = f'{a.isoformat()}|{b.isoformat()}|{query}'
            print(f'Scanning {a.date()}..{b.date()} {query}', flush=True)
            scan_window(posts, a, b, query, args.max_pages, args.delay)
            if args.mode == 'backfill':
                completed.add(key)
                state['completed'].append(key)
            write_json(POSTS, posts)
            write_json(STATE, state)
        count += 1
    if args.mode == 'backfill':
        state['backfill_complete'] = all(f'{a.isoformat()}|{b.isoformat()}|{q}' in completed for a, b in windows for q in QUERIES)
    write_json(STATE, state)
    print('New windows scanned:', count)
    print('Videos:', build(posts, state))

if __name__ == '__main__':
    main()
