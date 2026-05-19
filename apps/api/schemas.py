"""Pydantic request/response models for the Daybook HTTP API."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------


class CreateConversationRequest(BaseModel):
    title: str | None = None


class ConversationOut(BaseModel):
    id: str
    started_at: datetime
    title: str | None = None


class ConversationListItem(BaseModel):
    id: str
    started_at: datetime
    ended_at: datetime | None = None
    title: str | None = None
    message_count: int
    last_message_at: datetime | None = None


class ConversationListResponse(BaseModel):
    conversations: list[ConversationListItem]


class SendMessageRequest(BaseModel):
    text: str = Field(min_length=1)


class TraitDelta(BaseModel):
    trait: str
    delta: float
    reason: str | None = None


class SendMessageResponse(BaseModel):
    user_message_id: str
    assistant_message_id: str
    text: str
    model: str
    backend: str
    elapsed_ms: int
    observation_extracted: str | None = None
    trait_deltas: list[TraitDelta] = []


class ChatMessage(BaseModel):
    id: str
    role: str
    content: str
    sent_at: datetime
    metadata: dict[str, Any] = {}


class MessageListResponse(BaseModel):
    messages: list[ChatMessage]


# ---------------------------------------------------------------------------
# Recall / dreams
# ---------------------------------------------------------------------------


class RecallTextRequest(BaseModel):
    text: str = Field(min_length=1)
    ack: bool = True


class RecallResponse(BaseModel):
    dream_recall_id: str
    embedding_id: str | None
    text: str
    depth: str
    captured_at: datetime
    regis_utterance: str | None = None


class DreamListItem(BaseModel):
    id: str
    captured_at: datetime
    depth: str
    raw_text: str
    themes: list[str] = []
    similarity: float | None = None


class DreamListResponse(BaseModel):
    dreams: list[DreamListItem]


class DreamDetail(BaseModel):
    id: str
    captured_at: datetime
    depth: str
    raw_text: str
    voice_memo_url: str | None = None
    themes: list[str] = []
    session_id: str | None = None


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


class StageSummary(BaseModel):
    REM_pct: float = 0.0
    CORE_pct: float = 0.0
    DEEP_pct: float = 0.0
    AWAKE_pct: float = 0.0


class SessionListItem(BaseModel):
    id: str
    started_at: datetime
    ended_at: datetime
    duration_seconds: int
    stage_summary: StageSummary


class SessionListResponse(BaseModel):
    sessions: list[SessionListItem]


class StageRow(BaseModel):
    epoch_start_at: datetime
    stage: str
    source: str
    confidence: float | None = None


class SessionDetail(BaseModel):
    id: str
    started_at: datetime
    ended_at: datetime
    duration_seconds: int
    sensor_sources: list[str] = []
    notes: str | None = None
    stage_summary: StageSummary
    stages: list[StageRow] = []


class StateRow(BaseModel):
    estimated_at: datetime
    stage_proba: dict[str, Any] | None = None
    arousal: float | None = None
    valence: float | None = None
    presence: float | None = None
    confidence: float | None = None
    source: str


class SessionStateResponse(BaseModel):
    session_id: str
    states: list[StateRow]


# ---------------------------------------------------------------------------
# Observations
# ---------------------------------------------------------------------------


class ObservationItem(BaseModel):
    id: str
    observed_at: datetime
    observation: str
    weight: float
    similarity: float | None = None


class ObservationListResponse(BaseModel):
    observations: list[ObservationItem]


# ---------------------------------------------------------------------------
# Persona
# ---------------------------------------------------------------------------


class PersonaResponse(BaseModel):
    content: str
    modified_at: datetime


class PersonaUpdateRequest(BaseModel):
    content: str = Field(min_length=1)


class PersonaUpdateResponse(BaseModel):
    modified_at: datetime
    byte_count: int


# ---------------------------------------------------------------------------
# Compose
# ---------------------------------------------------------------------------


class ComposeRequest(BaseModel):
    moment_kind: str
    explicit_context: str = ""
    retrieval_query: str | None = None
    retrieval_top_k: int = 5
    persist: bool = False


class ComposeResponse(BaseModel):
    text: str
    mode: str
    retrieved: list[dict[str, Any]] = []
    composition_seconds: float
    model: str
    backend: str
    persisted_moment_id: str | None = None


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    db_connected: bool
    llm_signed_in: bool
    llm_account_email: str | None = None
    embeddings_loaded: bool
    last_dream_at: datetime | None = None
    total_dreams: int
    total_chat_messages: int


# ---------------------------------------------------------------------------
# State (#13) — iOS HealthKit → Mac body picture
# ---------------------------------------------------------------------------


class SensorReadingIn(BaseModel):
    recorded_at: datetime
    source: str                # "IPHONE" or "APPLE_WATCH"
    kind: str                  # "heart_rate" | "hrv" | "sleep_stage" | "temperature"
    payload: dict[str, Any]    # numeric value(s); polymorphic per `kind`


class SensorReadingsBatch(BaseModel):
    readings: list[SensorReadingIn]


class SensorIngestResponse(BaseModel):
    inserted: int
    rejected: int
    last_recorded_at: datetime | None = None


class BodySummary(BaseModel):
    line: str | None = None
    hrv_avg_ms: float | None = None
    hr_resting_bpm: int | None = None
    last_sleep_duration_minutes: int | None = None
    last_sleep_ended_at: datetime | None = None
    readings_last_24h: int
    generated_at: datetime


class BodySeriesPoint(BaseModel):
    day: str                   # "YYYY-MM-DD" (UTC)
    hrv_avg_ms: float | None = None
    hr_avg_bpm: float | None = None
    sleep_minutes: int | None = None


class BodySeriesResponse(BaseModel):
    days: int
    points: list[BodySeriesPoint]
