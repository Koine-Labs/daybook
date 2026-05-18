"""RSS feed pull + user-relevance filtering for Regis world awareness."""

from .feeder import (
    DEFAULT_FEEDS,
    FeedItem,
    fetch_default_feeds,
    fetch_feed,
    relevant_for_user,
)

__all__ = [
    "DEFAULT_FEEDS",
    "FeedItem",
    "fetch_default_feeds",
    "fetch_feed",
    "relevant_for_user",
]
