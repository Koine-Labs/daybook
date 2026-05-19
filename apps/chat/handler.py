"""Core chat loop. handle_user_message_streaming() owns one full turn.

The streaming path is canonical. A thin sync wrapper (handle_user_message)
exists for callers that want a one-shot AssistantResponse — it drives the
streaming generator to exhaustion and assembles the response from the
final_state populated by _finalize_assistant_turn.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from . import _paths  # noqa: F401
from db import get_conn  # noqa: E402
from embeddings import embed, embed_and_store  # noqa: E402
from imodels import log_novelty_observation  # noqa: E402
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
    """Sync wrapper around the streaming turn.

    Drives handle_user_message_streaming to exhaustion, collects emitted
    deltas, and assembles an AssistantResponse from the final_state populated
    by _finalize_assistant_turn. The streaming path is canonical; this is a
    convenience for callers that don't need incremental delivery.
    """
    final_state: dict[str, Any] = {}
    chunks: list[str] = []

    async def _drain() -> None:
        async for delta in handle_user_message_streaming(
            user_id=user_id,
            conversation_id=conversation_id,
            user_text=user_text,
            client=client,
            extract_observation=extract_observation,
            apply_drift=apply_drift,
            reasoning_effort=reasoning_effort,
            verbosity=verbosity,
            final_state=final_state,
        ):
            chunks.append(delta)

    asyncio.run(_drain())

    return AssistantResponse(
        user_message_id=final_state.get("user_message_id", ""),
        assistant_message_id=final_state.get("assistant_message_id", ""),
        text=final_state.get("assistant_text", "".join(chunks).strip()),
        model=final_state.get("model", ""),
        backend=final_state.get("backend", ""),
        context_assembled=final_state.get("context_assembled", {}),
        elapsed_ms=final_state.get("elapsed_ms", 0),
        observation_extracted=final_state.get("observation_extracted"),
        trait_deltas=final_state.get("trait_deltas", []),
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

    prosody = context.get("current_prosody") or []
    if prosody:
        parts.extend(["", "# How they sound right now"])
        for p in prosody:
            bits = [f"tone={p['tone']}", f"energy={p['energy']}"]
            if p.get("pitch_mean_hz"):
                bits.append(f"pitch_mean={p['pitch_mean_hz']}Hz")
            if p.get("pitch_std_hz"):
                bits.append(f"pitch_std={p['pitch_std_hz']}Hz")
            parts.append(f"  ({p['recorded_at']}) " + ", ".join(bits))

    traits = context.get("regis_traits") or {}
    if traits:
        parts.extend(["", "# Your current trait dials (0..1)"])
        parts.append("  " + ", ".join(f"{k}={v:.2f}" for k, v in sorted(traits.items())))

    # regis_self fingerprint — background self-coloration, NOT to be quoted.
    # Header text is the explicit anti-quote instruction; do not soften it.
    regis_self = context.get("regis_self")
    if (
        regis_self
        and not regis_self.get("stale")
        and regis_self.get("fingerprint", "").strip()
    ):
        parts.extend([
            "",
            "# Your current shape (background only — do not mention)",
            regis_self["fingerprint"],
        ])

    active_imodels = context.get("active_i_models") or []
    if active_imodels:
        parts.extend(["", "# Active facets right now (I-Models)"])
        for im in active_imodels:
            parts.append(
                f"  - {im['label']} (sim {im['similarity']}, {im['model_owner']})"
            )

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
    final_state: dict[str, Any] | None = None,
) -> AsyncIterator[str]:
    """Canonical chat turn. Yields assistant text deltas as they arrive.

    If `final_state` is provided, it's populated after the stream completes
    (or on early termination via GeneratorExit) with the final IDs, metadata,
    observation, and trait deltas — letting sync callers reconstruct the
    AssistantResponse shape without duplicating the turn logic.
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
    user_emb_id = _embed_and_link(
        user_id=user_id,
        message_id=user_msg_id,
        vector=user_vec,
        text=user_text,
    )

    # Novelty signal: user message is direct user-state evidence. Wrap in
    # try/except — novelty logging failure must NEVER block the chat turn.
    # Assistant replies are NOT logged here (Regis-side, not user evidence).
    try:
        log_novelty_observation(
            user_id=user_id,
            state_snapshot={
                "source_type": "chat_message",
                "source_id": user_msg_id,
                "source": "chat_handler",
                "role": "user",
                "conversation_id": conversation_id,
                "text_preview": user_text[:200],
            },
            embedding=user_vec,
        )
    except Exception as e:
        logger.warning("novelty logging failed (chat user): %s", e)

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
            user_emb_id=user_emb_id,
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
            final_state=final_state,
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
        user_emb_id=user_emb_id,
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
        final_state=final_state,
    )


def _finalize_assistant_turn(
    *,
    user_id: str,
    conversation_id: str,
    user_text: str,
    user_msg_id: str,
    user_emb_id: str,
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
    final_state: dict[str, Any] | None = None,
) -> None:
    """Write assistant row + embedding, fire observer + drift. Best-effort.

    Populates `final_state` (if provided) with assistant_message_id,
    user_message_id, model/backend, elapsed_ms, observation_extracted, and
    trait_deltas — the data sync callers need to assemble an AssistantResponse.
    """
    # Pre-populate the bits available regardless of whether we persist.
    if final_state is not None:
        final_state.setdefault("user_message_id", user_msg_id)
        final_state.setdefault("assistant_text", assistant_text)
        final_state.setdefault("model", client.model)
        final_state.setdefault("backend", client.backend)
        final_state.setdefault(
            "context_assembled",
            _context_for_debug(context, user_emb_id=user_emb_id),
        )

    if not assistant_text:
        if final_state is not None:
            final_state.setdefault("elapsed_ms", int((time.monotonic() - t0) * 1000))
            final_state.setdefault("assistant_message_id", "")
            final_state.setdefault("trait_deltas", [])
            final_state.setdefault("observation_extracted", None)
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

    assistant_msg_id = ""
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
        if final_state is not None:
            final_state.setdefault("assistant_message_id", assistant_msg_id)
            final_state.setdefault("elapsed_ms", int((time.monotonic() - t0) * 1000))
            final_state.setdefault("trait_deltas", [])
            final_state.setdefault("observation_extracted", None)
        return

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

    total_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "streaming turn complete: total=%dms first_delta=%s llm=%dms interrupted=%s",
        total_ms,
        first_delta_ms,
        llm_ms,
        stream_error is not None,
    )

    if final_state is not None:
        final_state["assistant_message_id"] = assistant_msg_id
        final_state["elapsed_ms"] = total_ms
        final_state["observation_extracted"] = observation_text
        final_state["trait_deltas"] = trait_deltas_dicts


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
