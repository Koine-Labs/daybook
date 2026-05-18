"""Smoke test: run remark_on_image (logo) + remark_on_news (top HN).

Run with:
    cd apps && python -m wisp.walking_remark_smoke
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

APPS_DIR = Path(__file__).resolve().parent.parent
INFERENCE_DIR = APPS_DIR / "inference"
sys.path.insert(0, str(APPS_DIR))
sys.path.insert(0, str(INFERENCE_DIR))

from wisp.walking_remark import remark_on_image, remark_on_news  # noqa: E402
from news.feeder import fetch_feed  # noqa: E402

DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"
LOGO_PATH = Path(
    "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Logo/Clear-Koine-Wisp.png"
)
HN_URL = "https://news.ycombinator.com/rss"


def main() -> int:
    print("=== Daybook walking-remark smoke test ===\n")

    # --- Test 1: vision-based remark ---
    print("[Test 1] remark_on_image() with Koine wisp logo")
    if not LOGO_PATH.exists():
        print(f"  SKIP — logo not at {LOGO_PATH}")
    else:
        t0 = time.monotonic()
        result = remark_on_image(
            user_id=DEFAULT_USER_ID,
            image_path=LOGO_PATH,
            persist=False,
        )
        dt = time.monotonic() - t0
        print(f"  total: {dt:.1f}s    composition: {result['composition_seconds']:.1f}s")
        print(f"  vision_available: {result['vision_available']}")
        print(f"  mode: {result['mode']}")
        print(f"  description: {result['description']!r}")
        print(f"  Regis: {result['utterance']!r}\n")

    # --- Test 2: news-based remark ---
    print("[Test 2] remark_on_news() with top HN item")
    items = fetch_feed(HN_URL, limit=5)
    if not items:
        print("  SKIP — HN feed returned no items")
    else:
        top = items[0]
        print(f"  source item: {top.title!r}")
        print(f"    url: {top.url}")
        t0 = time.monotonic()
        result = remark_on_news(
            user_id=DEFAULT_USER_ID,
            feed_item=top,
            persist=False,
        )
        dt = time.monotonic() - t0
        print(f"  total: {dt:.1f}s    composition: {result['composition_seconds']:.1f}s")
        print(f"  mode: {result['mode']}")
        print(f"  Regis: {result['utterance']!r}\n")

    print("=== Walking-remark smoke test complete ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
