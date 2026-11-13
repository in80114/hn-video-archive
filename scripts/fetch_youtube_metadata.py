
#!/usr/bin/env python3
"""Fetch and cache YouTube publication dates for HN Video Archive."""

import json
import os
import re
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
VIDEOS = ROOT / "data/videos.json"
CACHE = ROOT / "data/youtube_metadata.json"

API_URL = "https://www.googleapis.com/youtube/v3/videos"
VALID_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")

LIMIT = 200
BATCH_SIZE = 50


def read_json(path, default):
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        f.write("\n")
    os.replace(temp, path)


def fetch_batch(ids, api_key):
    params = urlencode({
        "part": "snippet",
        "id": ",".join(ids),
        "key": api_key,
    })

    url = API_URL + "?" + params

    request = Request(
        url,
        headers={
            "User-Agent": "HNVideoArchive/1.0",
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=40) as response:
            return json.load(response)

    except HTTPError as error:
        raw = error.read().decode(
            "utf-8",
            errors="replace",
        )

        # Prevent accidental exposure of the API key.
        safe_error = raw.replace(api_key, "[REDACTED]")

        print(
            f"YouTube API HTTP Error: {error.code}",
            flush=True,
        )

        try:
            details = json.loads(safe_error)
            info = details.get("error", {})

            print(
                "Google error message:",
                info.get("message", "Unknown"),
                flush=True,
            )

            for item in info.get("errors", []):
                print(
                    "Reason:",
                    item.get("reason", "Unknown"),
                    flush=True,
                )
                print(
                    "Domain:",
                    item.get("domain", "Unknown"),
                    flush=True,
                )

            if "status" in info:
                print(
                    "Status:",
                    info["status"],
                    flush=True,
                )

            for item in info.get("details", []):
                print(
                    "Detail:",
                    json.dumps(item, ensure_ascii=False),
                    flush=True,
                )

        except (ValueError, TypeError):
            print("Response:", safe_error[:2000], flush=True)

        raise SystemExit(
            "YouTube API request failed. Check the error above."
        ) from None

    except URLError as error:
        print(
            "Network error:",
            str(error.reason),
            flush=True,
        )
        raise SystemExit(1) from None


def main():
    api_key = os.environ.get(
        "YOUTUBE_API_KEY", ""
    ).strip()

    if not api_key:
        raise SystemExit(
            "ERROR: YOUTUBE_API_KEY is missing."
        )

    data = read_json(VIDEOS, {"videos": []})

    videos = [
        v for v in data.get("videos", [])
        if VALID_ID.fullmatch(v.get("id", ""))
        and v.get("count", 0) >= 2
    ]

    videos.sort(
        key=lambda v: (
            -v["count"],
            -v["points"],
            v["id"],
        )
    )

    ids = [v["id"] for v in videos[:LIMIT]]

    cache = read_json(CACHE, {})

    missing = [
        vid for vid in ids
        if not isinstance(cache.get(vid), dict)
        or not cache[vid].get("publishedAt")
    ]

    print(
        f"Selected videos: {len(ids)}",
        flush=True,
    )
    print(
        f"Already cached: {len(ids) - len(missing)}",
        flush=True,
    )
    print(
        f"Need API lookup: {len(missing)}",
        flush=True,
    )

    updated = 0

    for offset in range(0, len(missing), BATCH_SIZE):
        batch = missing[offset:offset + BATCH_SIZE]

        print(
            f"Fetching YouTube metadata: "
            f"{offset + 1}-{offset + len(batch)} "
            f"of {len(missing)}",
            flush=True,
        )

        result = fetch_batch(batch, api_key)

        for item in result.get("items", []):
            video_id = item.get("id")
            published = item.get(
                "snippet", {}
            ).get("publishedAt")

            if video_id and published:
                cache[video_id] = {
                    "publishedAt": published
                }
                updated += 1

        # Persist successful batches before continuing.
        write_json(CACHE, cache)

        time.sleep(0.2)

    write_json(CACHE, cache)

    print("YouTube metadata update completed.")
    print(f"New dates fetched: {updated}")
    print(f"Total cached videos: {len(cache)}")
    print(f"SEO videos selected: {len(ids)}")


if __name__ == "__main__":
    main()
