#!/usr/bin/env python3
"""Generate a bounded set of crawlable HN video pages and sitemap (stdlib only)."""
import datetime as dt
import html
import json
from pathlib import Path
import re
import shutil
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://hn-video-archive.vercel.app'
PAGES = ROOT / 'video'
LIMIT = 200
VALID_ID = re.compile(r'^[A-Za-z0-9_-]{11}$')

def esc(value):
    return html.escape(str(value), quote=True)

def build():
    data = json.loads((ROOT / 'data/videos.json').read_text(encoding='utf-8'))
    videos = [v for v in data['videos'] if VALID_ID.fullmatch(v.get('id', '')) and v.get('count', 0) >= 2]
    videos.sort(key=lambda v: (-v['count'], -v['points'], v['id']))
    selected = videos[:LIMIT]
    PAGES.mkdir(exist_ok=True)
    ids = {v['id'] for v in selected}
    for old in PAGES.glob('*.html'):
        if old.stem not in ids:
            old.unlink()
    for v in selected:
        vid = v['id']
        title = str(v['title'])[:180]
        url = f'{BASE}/video/{vid}'
        desc = f'{title}：在 Hacker News 被 {v["count"]} 篇不同貼文推薦，累計 {v["points"]} 點。查看原始討論與影片。'
        posts = v.get('posts', [])[:30]
        links = '\n'.join(f'<li><a href="https://news.ycombinator.com/item?id={quote(str(p["id"]))}" rel="noopener noreferrer">{esc(p.get("title") or "HN 討論")}</a> · {int(p.get("points") or 0)} 點</li>' for p in posts)
        structured = {'@context':'https://schema.org','@type':'VideoObject','name':title,'description':desc,'thumbnailUrl':f'https://i.ytimg.com/vi/{vid}/hqdefault.jpg','embedUrl':f'https://www.youtube-nocookie.com/embed/{vid}','url':url}
        ld = json.dumps(structured, ensure_ascii=False).replace('<', '\\u003c')
        page = f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)} | HN Video Archive</title><meta name="description" content="{esc(desc)}"><link rel="canonical" href="{url}"><meta property="og:type" content="video.other"><meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}"><meta property="og:image" content="https://i.ytimg.com/vi/{vid}/hqdefault.jpg"><script type="application/ld+json">{ld}</script><style>body{{background:#10141b;color:#edf1f7;font:16px/1.7 system-ui,sans-serif;max-width:860px;margin:0 auto;padding:24px}}a{{color:#91c6ff}}iframe{{width:100%;aspect-ratio:16/9;border:0}}h1{{line-height:1.3}}li{{margin:10px 0}}.meta{{color:#aebaca}}.back{{display:inline-block;margin-bottom:20px}}</style></head><body><a class="back" href="/">← 返回 HN Video Archive</a><main><h1>{esc(title)}</h1><p class="meta">分類：{esc(v['category'])} · {v['count']} 篇 HN 推薦 · 累計 {v['points']} 點</p><iframe loading="lazy" src="https://www.youtube-nocookie.com/embed/{vid}" title="{esc(title)}" allow="encrypted-media; picture-in-picture" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe><p><a href="https://www.youtube.com/watch?v={vid}" rel="noopener noreferrer">在 YouTube 觀看</a></p><h2>Hacker News 原始討論</h2><p>以下為推薦這部影片的 Hacker News 貼文，依原始貼文分數排序。</p><ul>{links}</ul></main></body></html>'''
        (PAGES / f'{vid}.html').write_text(page, encoding='utf-8')
    urls = [f'{BASE}/'] + [f'{BASE}/video/{v["id"]}' for v in selected]
    sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + ''.join(f'  <url><loc>{esc(url)}</loc></url>\n' for url in urls) + '</urlset>\n'
    (ROOT / 'sitemap.xml').write_text(sitemap, encoding='utf-8')
    print(f'Generated {len(selected)} video pages and {len(urls)} sitemap URLs')

if __name__ == '__main__':
    build()
