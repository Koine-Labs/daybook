"""Core chat loop. handle_user_message() owns one full turn."""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from . import _paths  # noqa: F401
from db import get_conn  # noqa: E402
from embeddings import embed, embed_and_store  # noqa: E402
from llm import ChatClient  # noqa: E402
from llm.codex_client import CodexStreamError  # noqa: E402

from . import observer, trait_drift
from .retrieval import gather_context


logger = logging.getLogger(__name__)


@dataclass
class AssistantResponse:
    user_message_id: str
    assistant_message_id: str
    text: str
    model: str
    backend: str
    context_assembled: dict[str, Any] = field(default_factory=dict)
    elapsed_ms: int = 0
    observation_extracted: str | None = None
    trait_deltas: list[dict[str, Any]] = field(default_factory=list)


def handle_user_message(
    *,
    user_id: str,
    conversation_id: str,
    user_text: str,
    client: ChatClient | None = None,
    extract_observation: bool = True,
    apply_drift: bool = True,
    reasoning_effort: str = "medium",
    verbosity: str = "medium",
) -> AssistantResponse:
    """Run one full turn end-to-end."""
    t0 = time.monotonic()
    user_text = user_text.strip()
    if not user_text:
        raise ValueError("user_text is empty")

    user_vec = embed(user_text)

    user_msg_id = _insert_message(
        conversation_id=conversation_id,
        user_id=user_id,
        role="user",
        content=user_text,
        metadata={},
    )
    user_emb_id = _embed_and_link(
        user_id=user_id,
        message_id=user_msg_id,
        vector=user_vec,
        text=user_text,
    )

    prior_user_msgs = _prior_user_messages(
        conversation_id=conversation_id, exclude_id=user_msg_id, limit=10
    )

    context = gather_context(
        user_id=user_id,
        conversation_id=conversation_id,
        user_text=user_text,
        user_embedding=user_vec,
    )

    persona = _load_persona()
    user_prompt = _build_prompt(user_text=user_text, context=context)

    if client is None:
        client = ChatClient.auto()

    llm_t0 = time.monotonic()
    try:
        assistant_text = client.chat(
            system=persona,
            user=user_prompt,
            reasoning_effort=reasoning_effort,
            verbosity=verbosity,
        ).strip()
    except Exception as e:
        logger.exception("LLM call failed")
        assistant_text = (
            "I'm having trouble reaching the language layer right now. Try me again in a moment."
        )
    llm_ms = int((time.monotonic() - llm_t0) * 1000)

    assistant_meta = {
        "model": client.model,
        "backend": client.backend,
        "retrieval_ms": context.get("_retrieval_ms"),
        "llm_ms": llm_ms,
    }
    assistant_msg_id = _insert_message(
        conversation_id=conversation_id,
        user_id=user_id,
        role="assistant",
        content=assistant_text,
        metadata=assistant_meta,
    )
    _embed_and_link(
        user_id=user_id,
        message_id=assistant_msg_id,
        vector=embed(assistant_text),
        text=assistant_text,
    )

    observation_text: str | None = None
    if extract_observation:
        try:
            observation_text = observer.maybe_extract_observation(
                user_id=user_id,
                user_message=user_text,
                assistant_message=assistant_text,
                client=client,
                context={
                    "conversation_id": conversation_id,
                    "user_message_id": user_msg_id,
                    "assistant_message_id": assistant_msg_id,
                },
            )
        except Exception as e:
            logger.warning("observer failed: %s", e)

    trait_deltas_dicts: list[dict[str, Any]] = []
    if apply_drift:
        try:
            deltas = trait_drift.maybe_apply_heuristics(
                user_id=user_id,
                user_message=user_text,
                assistant_message=assistant_text,
                prior_user_messages=prior_user_msgs,
            )
            trait_deltas_dicts = [
                {"trait": d.trait, "delta": d.delta, "reason": d.reason}
                for d in deltas
            ]
        except Exception as e:
            logger.warning("trait drift failed: %s", e)

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    return AssistantResponse(
        user_message_id=user_msg_id,
        assistant_message_id=assistant_msg_id,
        text=assistant_text,
        model=client.model,
        backend=client.backend,
        context_assembled=_context_for_debug(context, user_emb_id=user_emb_id),
        elapsed_ms=elapsed_ms,
        observation_extracted=observation_text,
        trait_deltas=trait_deltas_dicts,
    )


def _insert_message(
    *,
    conversation_id: str,
    user_id: str,
    role: str,
    content: str,
    metadata: dict[str, Any],
) -> str:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO chat_messages
              (conversation_id, user_id, role, content, metadata)
            VALUES (%s, %s, %s, %s, %s::jsonb)
            RETURNING id
            """,
            (conversation_id, user_id, role, content, json.dumps(metadata, default=str)),
        )
        new_id = str(cur.fetchone()[0])
        conn.commit()
    return new_id


def _embed_and_link(
    *, user_id: str, message_id: str, vector: list[float], text: str
) -> str:
    """Store embedding and link it back to chat_messages.embedding_id."""
    from embeddings.store import store_embedding

    emb_id = store_embedding(
        user_id=user_id,
        source_type="chat_message",
        source_id=message_id,
        vector=vector,
    )
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE chat_messages SET embedding_id = %s WHERE id = %s",
            (emb_id, message_id),
        )
        conn.commit()
    return emb_id


def _prior_user_messages(
    *, conversation_id: str, exclude_id: str, limit: int
) -> list[str]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT content FROM chat_messages
            WHERE conversation_id = %s AND role = 'user' AND id <> %s
            ORDER BY sent_at DESC
            LIMIT %s
            """,
            (conversation_id, exclude_id, limit),
        )
        rows = cur.fetchall()
    return [r[0] for r in reversed(rows)]


def _load_persona() -> str:
    return _paths.PERSONA_PATH.read_text()


def _build_prompt(*, user_text: str, context: dict[str, Any]) -> str:
    """Assemble the user message Regis sees, with all retrieved context.

    Persona stays in the system prompt; this is the runtime brief.
    """
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    parts: list[str] = [
        "# Now",
        f"timestamp: {now_iso}",
        "moment_kind: chat_message",
        "mode: companion    # user is awake and typing",
        "",
        "# What the user just said",
        user_text.strip(),
    ]

    recent = context.get("current_conversation_recent") or []
    if recent and len(recent) > 1:
        parts.extend(["", "# This conversation so far (oldest first, last 6 turns)"])
        for t in recent[:-1]:
            parts.append(f"  {t['role'].upper()}: {t['content']}")

    health = (context.get("relevant_health_data") or "").strip()
    if health:
        parts.extend(["", "# Relevant health data", health])

    observations = context.get("relevant_observations") or []
    notable_obs = [o for o in observations if "observation" in o]
    if notable_obs:
        parts.extend(["", "# Things you've previously noticed about this person"])
        for o in notable_obs:
            parts.append(
                f"  (sim {o['similarity']}) {o['observation']}"
            )

    similar = context.get("similar_past_exchanges") or []
    notable_similar = [s for s in similar if "content" in s]
    if notable_similar:
        parts.extend(["", "# Echoes — past chat exchanges similar to right now"])
        for s in notable_similar:
            content = s["content"]
            if len(content) > 240:
                content = content[:240].rstrip() + "..."
            parts.append(f"  ({s['role']}, sim {s['similarity']}) {content}")

    state = context.get("current_user_state")
    if state:
        parts.extend(["", "# Sensor read of the user right now", json.dumps(state, default=str)])

    traits = context.get("regis_traits") or {}
    if traits:
        parts.extend(["", "# Your current trait dials (0..1)"])
        parts.append("  " + ", ".join(f"{k}={v:.2f}" for k, v in sorted(traits.items())))

    parts.extend(
        [
            "",
            "# Task",
            "Reply as Regis in Companion Mode. You're a general partner — friend, witness, occasional smart-ass.",
            "Don't reach for sleep / dream / biometric framing unless the user actually brought it up.",
            "If health data is provided above, it's because the user's message invited it; use it sparingly, don't recite numbers.",
            "Let any retrieved observations or echoes texture your voice without naming them.",
            "Keep it to 1-4 sentences unless they asked for more. No preamble, no 'as Regis,' just speak.",
        ]
    )
    return "\n".join(parts)


async def handle_user_message_streaming(
    *,
    user_id: str,
    conversation_id: str,
    user_text: str,
    client: ChatClient | None = None,
    extract_observation: bool = True,
    apply_drift: bool = True,
    reasoning_effort: str = "low",
    verbosity: str = "low",
) -> AsyncIterator[str]:
    """Streaming variant of handle_user_message.

    Yields assistant text deltas as they arrive from the LLM. Same DB writes,
    observer, and trait drift as the sync path — the assistant row is written
    after the stream completes (or on early termination).
    """
    t0 = time.monotonic()
    user_text = user_text.strip()
    if not user_text:
        raise ValueError("user_text is empty")

    user_vec = embed(user_text)

    user_msg_id = _insert_message(
        conversation_id=conversation_id,
        user_id=user_id,
        role="user",
        content=user_text,
        metadata={},
    )
    _embed_and_link(
        user_id=user_id,
        message_id=user_msg_id,
        vector=user_vec,
        text=user_text,
    )

    prior_user_msgs = _prior_user_messages(
        conversation_id=conversation_id, exclude_id=user_msg_id, limit=10
    )

    context = gather_context(
        user_id=user_id,
        conversation_id=conversation_id,
        user_text=user_text,
        user_embedding=user_vec,
    )

    persona = _load_persona()
    user_prompt = _build_prompt(user_text=user_text, context=context)

    if client is None:
        client = ChatClient.auto()

    full_text = ""
    stream_error: Exception | None = None
    first_delta_ms: int | None = None
    llm_t0 = time.monotonic()

    try:
        async for delta in client.chat_stream(
            system=persona,
            user=user_prompt,
            reasoning_effort=reasoning_effort,
            verbosity=verbosity,
        ):
            if first_delta_ms is None:
                first_delta_ms = int((time.monotonic() - llm_t0) * 1000)
                logger.info("first_delta_ms=%s", first_delta_ms)
            full_text += delta
            yield delta
    except CodexStreamError as e:
        stream_error = e
        partial = getattr(e, "partial_text", "") or ""
        if partial and not full_text:
            full_text = partial
        logger.warning("codex stream failed: %s (partial=%d chars)", e, len(full_text))
    except GeneratorExit:
        stream_error = RuntimeError("consumer closed stream early")
        logger.info("stream consumer closed early (likely barge-in)")
        _finalize_assistant_turn(
            user_id=user_id,
            conversation_id=conversation_id,
            user_text=user_text,
            user_msg_id=user_msg_id,
            assistant_text=full_text,
            client=client,
            context=context,
            llm_t0=llm_t0,
            first_delta_ms=first_delta_ms,
            t0=t0,
            stream_error=stream_error,
            extract_observation=extract_observation,
            apply_drift=apply_drift,
            prior_user_msgs=prior_user_msgs,
        )
        raise
    except Exception as e:
        stream_error = e
        logger.exception("unexpected error during streaming chat")

    if not full_text and stream_error is not None:
        full_text = (
            "I'm having trouble reaching the language layer right now. "
            "Try me again in a moment."
        )
        yield full_text

    _finalize_assistant_turn(
        user_id=user_id,
        conversation_id=conversation_id,
        user_text=user_text,
        user_msg_id=user_msg_id,
        assistant_text=full_text.strip(),
        client=client,
        context=context,
        llm_t0=llm_t0,
        first_delta_ms=first_delta_ms,
        t0=t0,
        stream_error=stream_error,
        extract_observation=extract_observation,
        apply_drift=apply_drift,
        prior_user_msgs=prior_user_msgs,
    )


def _finalize_assistant_turn(
    *,
    user_id: str,
    conversation_id: str,
    user_text: str,
    user_msg_id: str,
    assistant_text: str,
    client: ChatClient,
    context: dict[str, Any],
    llm_t0: float,
    first_delta_ms: int | None,
    t0: float,
    stream_error: Exception | None,
    extract_observation: bool,
    apply_drift: bool,
    prior_user_msgs: list[str],
) -> None:
    """Write assistant row + embedding, fire observer + drift. Best-effort."""
    if not assistant_text:
        return

    llm_ms = int((time.monotonic() - llm_t0) * 1000)
    assistant_meta: dict[str, Any] = {
        "model": client.model,
        "backend": client.backend,
        "retrieval_ms": context.get("_retrieval_ms"),
        "llm_ms": llm_ms,
        "streaming": True,
    }
    if first_delta_ms is not None:
        assistant_meta["first_delta_ms"] = first_delta_ms
    if stream_error is not None:
        assistant_meta["streaming_interrupted"] = True
        assistant_meta["stream_error"] = str(stream_error)[:300]

    try:
        assistant_msg_id = _insert_message(
            conversation_id=conversation_id,
            user_id=user_id,
            role="assistant",
            content=assistant_text,
            metadata=assistant_meta,
        )
        _embed_and_link(
            user_id=user_id,
            message_id=assistant_msg_id,
            vector=embed(assistant_text),
            text=assistant_text,
        )
    except Exception:
        logger.exception("failed to persist assistant message; skipping observer/drift")
        return

    if extract_observation:
        try:
            observer.maybe_extract_observation(
                user_id=user_id,
                user_message=user_text,
                assistant_message=assistant_text,
                client=client,
                context={
                    "conversation_id": conversation_id,
                    "user_message_id": user_msg_id,
                    "assistant_message_id": assistant_msg_id,
                },
            )
        except Exception as e:
            logger.warning("observer failed: %s", e)

    if apply_drift:
        try:
            trait_drift.maybe_apply_heuristics(
                user_id=user_id,
                user_message=user_text,
                assistant_message=assistant_text,
                prior_user_messages=prior_user_msgs,
            )
        except Exception as e:
            logger.warning("trait drift failed: %s", e)

    total_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "streaming turn complete: total=%dms first_delta=%s llm=%dms interrupted=%s",
        total_ms,
        first_delta_ms,
        llm_ms,
        stream_error is not None,
    )


def _context_for_debug(
    context: dict[str, Any], *, user_emb_id: str
) -> dict[str, Any]:
    """Pruned version of context suitable for logging / persisting in metadata."""
    out = dict(context)
    out["user_embedding_id"] = user_emb_id
    if recent := out.get("current_conversation_recent"):
        out["current_conversation_recent_count"] = len(recent)
    if similar := out.get("similar_past_exchanges"):
        out["similar_past_exchanges_count"] = len(similar)
    if obs := out.get("relevant_observations"):
        out["relevant_observations_count"] = len(obs)
    return out
