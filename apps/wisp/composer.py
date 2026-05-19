"""Generative Regis composer.

Assembles a runtime context (current user state + retrieved I-Model memories +
moment kind + any explicit context) and calls the LLM with PERSONA.md as the
system prompt. Returns an utterance suitable for TTS playback.

Mode tag (Witness vs Companion) is derived from the moment kind, matching the
dual-mode framing in PERSONA.md.

Optionally persists the composed utterance to regis_moments for later review +
trait drift + observation accumulation.
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

# Path setup so we can import from apps/inference/
INFERENCE_DIR = Path(__file__).resolve().parent.parent / "inference"
sys.path.insert(0, str(INFERENCE_DIR))

from db import get_conn  # noqa: E402
from llm import ChatClient  # noqa: E402
from embeddings import embed, retrieve_similar  # noqa: E402
from imodels.substrate import SubstrateContext, gather_substrate  # noqa: E402

from .embedding_hook import embed_regis_moment  # noqa: E402

# PERSONA.md sits next to this file in apps/wisp/
PERSONA_PATH = Path(__file__).resolve().parent / "PERSONA.md"

# Map moment kind -> mode. Default = companion (safe-ish for awake user).
# Witness mode is the reserved-for-sleep mode where Regis is reverent.
WITNESS_KINDS = {
    "rem_whisper",
    "wake_greeting",
    "capture_ack",
    "sleep_onset_silence",
}
COMPANION_KINDS = {
    "pre_sleep_greeting",
    "intent_setting",
    "morning_recall_prompt",
    "walking_remark",
    "conversation_tease",
    "news_pull_comment",
    "mood_check",
    "inner_thought",
    "dream_thought",
}


@dataclass
class ComposedUtterance:
    text: str
    mode: str  # 'witness' | 'companion'
    moment_kind: str
    model: str
    backend: str
    retrieved: list[dict[str, Any]] = field(default_factory=list)
    current_state: dict[str, Any] | None = None
    persisted_moment_id: str | None = None
    composition_seconds: float = 0.0
    # Shared substrate snapshot (traits / active i-models / prosody) used to
    # texture this utterance. Empty SubstrateContext if no embedding-yielding
    # query text was available at compose time.
    substrate: SubstrateContext = field(default_factory=SubstrateContext)


# Forbidden vocabulary — sanity validator, NOT strict enforcement (see Test 3 in
# llm/smoke_test.py: Regis using forbidden words in scare quotes to refuse them
# is character-correct). This list is for cheap logging.
FORBIDDEN_WORDS_SOFT = {
    "optimize", "improve", "track", "log",
    "sync", "data", "session", "feature",
    "stages", "stage", "HRV", "REM",  # let scare-quote use slide; warn anyway
}


def compose_utterance(
    *,
    user_id: str,
    moment_kind: str,
    explicit_context: str = "",
    retrieval_query: str | None = None,
    retrieval_top_k: int = 5,
    retrieval_source_types: Sequence[str] | None = ("dream_recall", "intent"),
    persist: bool = False,
    session_id: str | None = None,
    client: ChatClient | None = None,
    reasoning_effort: str = "low",
    verbosity: str = "low",
) -> ComposedUtterance:
    """Compose a Regis utterance for the given moment.

    Args:
        user_id: which user this is for (drives retrieval scoping + state read)
        moment_kind: e.g. 'rem_whisper', 'morning_recall_prompt' (see WITNESS_KINDS / COMPANION_KINDS)
        explicit_context: free-form runtime context the caller wants in the prompt
            (e.g. "REM probability 0.78, sustained 90s, first cue of night")
        retrieval_query: text to embed for I-Model retrieval; if None and explicit_context
            is non-empty, uses explicit_context as the query
        retrieval_top_k: how many memories to retrieve
        retrieval_source_types: limit retrieval to these source_type values in embeddings
        persist: if True, write the utterance to regis_moments after composition
        session_id: optional sleep_session this moment belongs to
        client: pre-built ChatClient (else ChatClient.auto())
        reasoning_effort: LLM param
        verbosity: LLM param

    Returns ComposedUtterance with utterance text + metadata.
    """
    t0 = time.monotonic()
    mode = _mode_for_kind(moment_kind)
    persona = PERSONA_PATH.read_text()

    # 1. Compute one query embedding (if we have query text) so retrieval AND
    #    substrate share the same vector — cheaper than embedding twice, and
    #    keeps "what's similar to right now" consistent across both reads.
    query_text = retrieval_query or explicit_context
    qvec: list[float] | None = None
    if query_text and query_text.strip():
        try:
            qvec = embed(query_text)
        except Exception:
            qvec = None

    # 2. Shared substrate: traits / current_user_state (fresh) / prosody /
    #    active_i_models / relevant_observations. Same well chat drinks from.
    substrate = gather_substrate(user_id=user_id, query_embedding=qvec)

    # current_state preserves the legacy 'no freshness gate' read path so
    # nightly autonomous moments (e.g., rem_whisper) still surface the
    # session's latest estimate even if it's > 1h old. The substrate's
    # fresh-only current_user_state is also rendered when present.
    current_state = _read_latest_state(user_id)

    # 3. Retrieved I-Model context — reuses qvec so we don't re-embed.
    retrieved: list[dict[str, Any]] = []
    if qvec is not None:
        try:
            hits = retrieve_similar(
                qvec,
                user_id=user_id,
                top_k=retrieval_top_k,
                source_types=list(retrieval_source_types) if retrieval_source_types else None,
            )
            retrieved = [
                {
                    "source_type": h.source_type,
                    "source_id": h.source_id,
                    "similarity": round(h.similarity, 3),
                }
                for h in hits
            ]
        except Exception as e:
            retrieved = [{"_retrieval_error": str(e)}]

    # 4. Compose the runtime context (the LLM user message)
    user_prompt = _build_user_prompt(
        moment_kind=moment_kind,
        mode=mode,
        explicit_context=explicit_context,
        current_state=current_state,
        retrieved=retrieved,
        substrate=substrate,
    )

    # 4. LLM call
    if client is None:
        client = ChatClient.auto()
    text = client.chat(
        system=persona,
        user=user_prompt,
        reasoning_effort=reasoning_effort,
        verbosity=verbosity,
    ).strip()

    # 5. Sanity warn on forbidden-word presence (don't reject — see docstring)
    leaks = sorted({w for w in FORBIDDEN_WORDS_SOFT if w.lower() in text.lower()})
    if leaks:
        print(f"[composer] note: utterance contains soft-forbidden words {leaks}: {text!r}")

    composed = ComposedUtterance(
        text=text,
        mode=mode,
        moment_kind=moment_kind,
        model=client.model,
        backend=client.backend,
        retrieved=retrieved,
        current_state=current_state,
        composition_seconds=time.monotonic() - t0,
        substrate=substrate,
    )

    # 6. Optional persistence
    if persist:
        composed.persisted_moment_id = _persist_moment(
            user_id=user_id,
            session_id=session_id,
            composed=composed,
            explicit_context=explicit_context,
        )

    return composed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mode_for_kind(kind: str) -> str:
    if kind in WITNESS_KINDS:
        return "witness"
    if kind in COMPANION_KINDS:
        return "companion"
    # Unknown kind → safer default is companion (Regis speaks at full voice;
    # caller can override by explicit context).
    return "companion"


def _read_latest_state(user_id: str) -> dict[str, Any] | None:
    """Get the most recent user_state_estimate row."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT estimated_at, stage_proba, arousal, valence, presence, confidence, source
            FROM user_state_estimate
            WHERE user_id = %s
            ORDER BY estimated_at DESC
            LIMIT 1
            """,
            (user_id,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return {
        "estimated_at": row[0].isoformat() if row[0] else None,
        "stage_proba": row[1],
        "arousal": row[2],
        "valence": row[3],
        "presence": row[4],
        "confidence": row[5],
        "source": row[6],
    }


def _build_user_prompt(
    *,
    moment_kind: str,
    mode: str,
    explicit_context: str,
    current_state: dict[str, Any] | None,
    retrieved: list[dict[str, Any]],
    substrate: SubstrateContext,
) -> str:
    """Assemble the LLM user-message context. Structured but compact.

    The persona (system prompt) governs voice; this user message provides
    *what is happening right now* and *what to remember*.

    Substrate sections (trait dials, active facets, prosody) match the
    rendering in chat.handler._build_prompt so trait drift learned via chat
    transfers to autonomous moments.
    """
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    parts: list[str] = [
        f"# Now",
        f"timestamp: {now_iso}",
        f"moment_kind: {moment_kind}",
        f"mode: {mode}    # speak in this mode per PERSONA.md",
    ]

    if explicit_context:
        parts.extend(["", "# Context", explicit_context.strip()])

    if current_state:
        parts.extend(["", "# Sensor state", json.dumps(current_state, default=str)])
    else:
        parts.extend(["", "# Sensor state", "(no user_state_estimate available)"])

    prosody = substrate.current_prosody
    if prosody:
        parts.extend(["", "# How they sound right now"])
        for p in prosody:
            bits = [f"tone={p['tone']}", f"energy={p['energy']}"]
            if p.get("pitch_mean_hz"):
                bits.append(f"pitch_mean={p['pitch_mean_hz']}Hz")
            if p.get("pitch_std_hz"):
                bits.append(f"pitch_std={p['pitch_std_hz']}Hz")
            parts.append(f"  ({p['recorded_at']}) " + ", ".join(bits))

    traits = substrate.regis_traits
    if traits:
        parts.extend(["", "# Your current trait dials (0..1)"])
        parts.append(
            "  " + ", ".join(f"{k}={v:.2f}" for k, v in sorted(traits.items()))
        )

    active_imodels = substrate.active_i_models
    if active_imodels:
        parts.extend(["", "# Active facets right now (I-Models)"])
        for im in active_imodels:
            parts.append(
                f"  - {im['label']} (sim {im['similarity']}, {im['model_owner']})"
            )

    observations = substrate.relevant_observations
    notable_obs = [o for o in observations if "observation" in o]
    if notable_obs:
        parts.extend(["", "# Things you've previously noticed about this person"])
        for o in notable_obs:
            parts.append(f"  (sim {o['similarity']}) {o['observation']}")

    if retrieved:
        retrieved_block = json.dumps(retrieved, indent=2)
        parts.extend(
            [
                "",
                "# Retrieved I-Model memories",
                "(top similarity matches — use these to texture your utterance if relevant; do NOT list them back)",
                retrieved_block,
            ]
        )

    parts.extend(
        [
            "",
            "# Task",
            f"Speak as Regis. Mode = {mode}. Moment = {moment_kind}.",
            "Respond with only the utterance itself — no preamble, no explanation, no quotes.",
        ]
    )
    return "\n".join(parts)


def _persist_moment(
    *,
    user_id: str,
    session_id: str | None,
    composed: ComposedUtterance,
    explicit_context: str,
) -> str:
    """Write to regis_moments. Returns new moment id.

    active_i_model_ids + i_model_id are populated from the substrate
    snapshot (audit #3 / leftover #2) — no more hardcoded []. Top-1 cluster
    becomes the primary i_model_id; all firing cluster ids land in the
    array column.
    """
    active_ids = composed.substrate.active_i_model_cluster_ids
    primary_id = composed.substrate.primary_i_model_cluster_id
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO regis_moments
                (user_id, session_id, occurred_at, kind, mode, content,
                 content_source, triggering_context, active_i_model_ids,
                 i_model_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
            RETURNING id
            """,
            (
                user_id,
                session_id,
                datetime.now(timezone.utc),
                composed.moment_kind,
                composed.mode,
                composed.text,
                "generative_llm",
                json.dumps(
                    {
                        "explicit_context": explicit_context,
                        "current_state": composed.current_state,
                        "retrieved": composed.retrieved,
                        "model": composed.model,
                        "backend": composed.backend,
                        "substrate": composed.substrate.as_dict(),
                    },
                    default=str,
                ),
                active_ids,
                primary_id,
            ),
        )
        new_id = str(cur.fetchone()[0])
        conn.commit()
    # Fire-and-forget: embed this moment so Regis can later recall his own
    # utterances (audit item #12). Errors are logged inside the hook and do
    # not propagate — moment persistence must succeed even if embedding fails.
    embed_regis_moment(user_id, new_id, composed.text)
    return new_id
