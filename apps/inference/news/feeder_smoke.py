"""Smoke test: pull HN, print top items, attempt user-relevance filtering.

Run with:
    cd apps/inference && source .venv/bin/activate
    python -m news.feeder_smoke
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from news.feeder import (  # noqa: E402
    DEFAULT_USER_ID,
    fetch_feed,
    relevant_for_user,
)

HN_URL = "https://news.ycombinator.com/rss"


def main() -> int:
    print("=== Daybook news feeder smoke test ===\n")

    print(f"[Test 1] fetch_feed({HN_URL})")
    t0 = time.monotonic()
    items = fetch_feed(HN_URL, limit=20)
    dt = time.monotonic() - t0
    print(f"  pulled {len(items)} items in {dt*1000:.0f}ms")

    if not items:
        print("  FAIL — feed returned 0 items (HN may have rate-limited)")
        return 1

    print("\n  Top 5 titles:")
    for it in items[:5]:
        print(f"    - {it.title}")
        if it.published_at:
            print(f"        ({it.published_at.isoformat()})")

    print("\n[Test 2] relevant_for_user — Aakash, no themes")
    t0 = time.monotonic()
    try:
        filtered = relevant_for_user(
            items,
            user_id=DEFAULT_USER_ID,
            top_k=5,
        )
        dt = time.monotonic() - t0
        print(f"  scored in {dt*1000:.0f}ms (includes embedding {len(items)} items)")
        if filtered:
            print(f"  {len(filtered)} items above threshold:")
            for it in filtered:
                print(f"    - {it.title}")
        else:
            print("  0 items above threshold — expected if user has few stored embeddings yet")
    except Exception as e:
        print(f"  FAIL — relevance scoring raised {type(e).__name__}: {e}")
        return 1

    print("\n[Test 3] relevant_for_user — with explicit themes")
    themes = ["dreams and the inner world", "sleep and consciousness", "cognitive science"]
    try:
        filtered2 = relevant_for_user(
            items,
            user_id=DEFAULT_USER_ID,
            top_k=5,
            query_themes=themes,
        )
        if filtered2:
            print(f"  {len(filtered2)} items above threshold (themes={themes}):")
            for it in filtered2:
                print(f"    - {it.title}")
        else:
            print(f"  0 items above threshold for themes {themes}")
    except Exception as e:
        print(f"  FAIL — themed scoring raised {type(e).__name__}: {e}")
        return 1

    print("\n=== News feeder smoke test complete ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
