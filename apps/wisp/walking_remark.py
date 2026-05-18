"""End-to-end walking-remark behavior.

Two flavors:
  - `remark_on_image`: vision frame -> describe_image -> composer -> Regis comment
  - `remark_on_news`:  RSS item -> composer -> Regis comment

Both delegate composition to `wisp.composer.compose_utterance`. If Phase 1's
audio module ships a `speak()` function, callers can opt into TTS playback
via `speak_aloud=True`.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

WISP_DIR = Path(__file__).resolve().parent
APPS_DIR = WISP_DIR.parent
INFERENCE_DIR = APPS_DIR / "inference"
sys.path.insert(0, str(APPS_DIR))
sys.path.insert(0, str(INFERENCE_DIR))

from wisp.composer import compose_utterance  # noqa: E402

from llm.vision import (  # noqa: E402
    VisionNotAvailableError,
    describe_image,
)
from news.feeder import FeedItem  # noqa: E402


VISION_FALLBACK_DESCRIPTION = (
    "image was provided but vision is not available — speak abstractly about "
    "presence and the act of walking through the world"
)


def remark_on_image(
    *,
    user_id: str,
    image_path: Path | str,
    persist: bool = False,
    session_id: str | None = None,
    speak_aloud: bool = False,
    vision_prompt: str = "Describe what you see in 1-2 plain sentences. Be concrete about objects, light, mood.",
) -> dict[str, Any]:
    """Vision -> composer -> Regis remark.

    Returns: {utterance, description, mode, model, composition_seconds, regis_moment_id, vision_available}
    """
    path = Path(image_path)
    description: str
    vision_available: bool

    try:
        description = describe_image(image_path=path, prompt=vision_prompt)
        vision_available = True
    except VisionNotAvailableError as e:
        description = VISION_FALLBACK_DESCRIPTION
        vision_available = False
        print(f"[walking_remark] vision unavailable: {e}")
    except Exception as e:
        description = VISION_FALLBACK_DESCRIPTION
        vision_available = False
        print(f"[walking_remark] vision call failed ({type(e).__name__}): {e}")

    explicit_context = (
        f"You glanced at the world for a moment. What you saw: {description}\n"
        "Remark briefly. One short sentence — dry, observed, not announced."
    )

    composed = compose_utterance(
        user_id=user_id,
        moment_kind="walking_remark",
        explicit_context=explicit_context,
        retrieval_query=description,
        retrieval_source_types=("dream_recall", "intent", "regis_observation"),
        persist=persist,
        session_id=session_id,
        reasoning_effort="low",
        verbosity="low",
    )

    if speak_aloud:
        _maybe_speak(composed.text)

    return {
        "utterance": composed.text,
        "description": description,
        "mode": composed.mode,
        "model": composed.model,
        "backend": composed.backend,
        "composition_seconds": composed.composition_seconds,
        "regis_moment_id": composed.persisted_moment_id,
        "vision_available": vision_available,
    }


def remark_on_news(
    *,
    user_id: str,
    feed_item: FeedItem,
    persist: bool = False,
    session_id: str | None = None,
    speak_aloud: bool = False,
) -> dict[str, Any]:
    """News item -> composer -> Regis remark.

    Returns: {utterance, url, mode, model, composition_seconds, regis_moment_id}
    """
    summary_block = feed_item.summary.strip()
    summary_clip = summary_block[:600] if len(summary_block) > 600 else summary_block

    explicit_context = (
        f"Something passed across the wires. Title: {feed_item.title}\n"
        + (f"Summary: {summary_clip}\n" if summary_clip else "")
        + "Remark briefly — one or two short sentences. Observed, not announced. "
        "Do not summarize the article; react to it."
    )

    composed = compose_utterance(
        user_id=user_id,
        moment_kind="news_pull_comment",
        explicit_context=explicit_context,
        retrieval_query=feed_item.embedding_text(),
        retrieval_source_types=("regis_observation", "intent", "chat_message"),
        persist=persist,
        session_id=session_id,
        reasoning_effort="low",
        verbosity="low",
    )

    if speak_aloud:
        _maybe_speak(composed.text)

    return {
        "utterance": composed.text,
        "url": feed_item.url,
        "title": feed_item.title,
        "mode": composed.mode,
        "model": composed.model,
        "backend": composed.backend,
        "composition_seconds": composed.composition_seconds,
        "regis_moment_id": composed.persisted_moment_id,
    }


def _maybe_speak(text: str) -> None:
    """Best-effort TTS through Phase 1's audio module if it exists."""
    try:
        from inference.audio import speak  # type: ignore
    except ImportError:
        try:
            sys.path.insert(0, str(INFERENCE_DIR))
            from audio import speak  # type: ignore
        except ImportError:
            print("[walking_remark] audio.speak not available; skipping speak_aloud")
            return

    try:
        speak(text)
    except Exception as e:
        print(f"[walking_remark] speak() raised {type(e).__name__}: {e}")
