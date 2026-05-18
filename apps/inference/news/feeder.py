"""RSS / Atom feed pull + user-relevance filtering.

`fetch_feed` pulls one URL. `fetch_default_feeds` pulls a small editable list.
`relevant_for_user` filters items by semantic similarity to the user's stored
embeddings (dream_recalls + intents + chat_messages + regis_observations).
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import mktime
from typing import Sequence

import feedparser
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from embeddings import embed, embed_batch, retrieve_similar  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"

DEFAULT_FEEDS: tuple[str, ...] = (
    "https://news.ycombinator.com/rss",
    "https://www.theverge.com/rss/index.xml",
    "https://www.economist.com/europe/rss.xml",
)

DEFAULT_USER_AGENT = "Daybook/0.1 (+regis-news-feeder)"
DEFAULT_RELEVANT_SOURCE_TYPES: tuple[str, ...] = (
    "dream_recall",
    "intent",
    "chat_message",
    "regis_observation",
)


@dataclass
class FeedItem:
    title: str
    summary: str
    url: str
    published_at: datetime | None
    source_feed: str

    def embedding_text(self) -> str:
        """Title + summary joined for embedding."""
        if self.summary:
            return f"{self.title}\n\n{self.summary}"
        return self.title


def fetch_feed(url: str, *, limit: int = 20, timeout: float = 10.0) -> list[FeedItem]:
    """Pull and parse one RSS/Atom feed. Returns up to `limit` items."""
    try:
        with httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": DEFAULT_USER_AGENT},
        ) as client:
            res = client.get(url)
            res.raise_for_status()
            content = res.content
    except httpx.HTTPError as e:
        logger.warning("Feed fetch failed for %s: %s", url, e)
        return []

    parsed = feedparser.parse(content)
    if parsed.bozo and not parsed.entries:
        logger.warning("Feed parse failed for %s: %s", url, parsed.bozo_exception)
        return []

    items: list[FeedItem] = []
    for entry in parsed.entries[:limit]:
        items.append(
            FeedItem(
                title=_clean(getattr(entry, "title", "")),
                summary=_clean(
                    getattr(entry, "summary", "") or getattr(entry, "description", "")
                ),
                url=getattr(entry, "link", ""),
                published_at=_parse_published(entry),
                source_feed=url,
            )
        )
    return items


def fetch_default_feeds(
    *, limit_per_feed: int = 20, timeout: float = 10.0
) -> list[FeedItem]:
    """Pull each feed in `DEFAULT_FEEDS`. Skips feeds that fail."""
    out: list[FeedItem] = []
    for url in DEFAULT_FEEDS:
        items = fetch_feed(url, limit=limit_per_feed, timeout=timeout)
        out.extend(items)
    return out


def relevant_for_user(
    items: list[FeedItem],
    *,
    user_id: str,
    top_k: int = 5,
    query_themes: Sequence[str] | None = None,
    min_similarity: float = 0.25,
    source_types: Sequence[str] = DEFAULT_RELEVANT_SOURCE_TYPES,
) -> list[FeedItem]:
    """Filter items to those most semantically relevant to the user.

    For each item: embed title+summary, retrieve top-K similar memories, score
    by the best similarity. If `query_themes` are provided, also score by the
    max similarity to any theme. Return top_k items with combined score above
    `min_similarity`.
    """
    if not items:
        return []

    texts = [it.embedding_text() for it in items]
    item_vecs = embed_batch(texts)

    theme_vecs: list[list[float]] = []
    if query_themes:
        theme_vecs = embed_batch(list(query_themes))

    scored: list[tuple[float, FeedItem]] = []
    for item, vec in zip(items, item_vecs):
        memory_hits = retrieve_similar(
            vec,
            user_id=user_id,
            top_k=3,
            source_types=list(source_types),
        )
        memory_score = max((h.similarity for h in memory_hits), default=0.0)

        theme_score = 0.0
        if theme_vecs:
            theme_score = max(_cosine(vec, t) for t in theme_vecs)

        combined = max(memory_score, theme_score)
        if combined >= min_similarity:
            scored.append((combined, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [it for _, it in scored[:top_k]]


def _clean(text: str) -> str:
    """Strip HTML tags conservatively + collapse whitespace."""
    import re

    no_tags = re.sub(r"<[^>]+>", " ", text or "")
    return " ".join(no_tags.split())


def _parse_published(entry: object) -> datetime | None:
    parsed = getattr(entry, "published_parsed", None) or getattr(
        entry, "updated_parsed", None
    )
    if parsed is None:
        return None
    try:
        return datetime.fromtimestamp(mktime(parsed), tz=timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _cosine(a: list[float], b: list[float]) -> float:
    """BGE-M3 outputs are L2-normalized, so this collapses to a dot product."""
    return sum(x * y for x, y in zip(a, b))


def _cli() -> int:
    parser = argparse.ArgumentParser(
        description="Pull RSS feeds and (optionally) filter by user relevance."
    )
    parser.add_argument("--feed", action="append", help="Override feed URL(s)")
    parser.add_argument("--user", default=DEFAULT_USER_ID, help="User UUID for relevance filtering")
    parser.add_argument("--relevant", action="store_true", help="Filter by relevance")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--limit-per-feed", type=int, default=20)
    parser.add_argument("--theme", action="append", help="Optional query theme(s)")
    args = parser.parse_args()

    if args.feed:
        items: list[FeedItem] = []
        for url in args.feed:
            items.extend(fetch_feed(url, limit=args.limit_per_feed))
    else:
        items = fetch_default_feeds(limit_per_feed=args.limit_per_feed)

    print(f"Pulled {len(items)} items from {len(args.feed) if args.feed else len(DEFAULT_FEEDS)} feed(s).\n")

    if args.relevant:
        if not items:
            print("No items to filter.")
            return 0
        filtered = relevant_for_user(
            items,
            user_id=args.user,
            top_k=args.top_k,
            query_themes=args.theme,
        )
        if not filtered:
            print("(no items met the relevance threshold)")
            print("Top 5 by default ordering:")
            for it in items[:5]:
                print(f"  - {it.title}  [{it.source_feed}]")
            return 0
        print(f"Top {len(filtered)} relevant:")
        for it in filtered:
            print(f"  - {it.title}")
            print(f"      {it.url}")
            print(f"      [{it.source_feed}]")
        return 0

    for it in items:
        print(f"- {it.title}  [{it.source_feed}]")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
