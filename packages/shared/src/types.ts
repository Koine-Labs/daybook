/**
 * Daybook v0 data model.
 *
 * This file is the **conceptual source of truth** for Daybook entities. Every
 * other layer (Python inference pipeline, web app, iOS app) must agree on
 * these shapes.
 *
 * The **database source of truth** is `apps/inference/migrations/0001_initial.sql`.
 * The two must stay in sync — when you change one, change the other.
 *
 * Conventions
 * -----------
 * - Branded ID types from `./ids` for type-safety across entity boundaries.
 * - ISO 8601 date-time strings (with timezone) for all timestamps. Date objects
 *   live only in language-specific layers, not at this boundary.
 * - `iModelId: IModelID | null` on every event-like entity, per the I-Model
 *   architectural commitment. v1 leaves it null; v2+ ML clustering populates it.
 * - Discriminated unions (with a `kind` field) for polymorphic content like
 *   sensor readings. Maps to a `kind` column + `payload` JSONB in Postgres.
 */

import type {
  CueEventID,
  DreamRecallID,
  EmbeddingID,
  IModelActivationID,
  IModelID,
  IModelNoveltyLogID,
  InterjectDecisionID,
  IntentID,
  MoodReportID,
  RegisMomentID,
  RegisObservationID,
  RegisTraitHistoryID,
  SensorReadingID,
  SleepSessionID,
  SleepStageClassificationID,
  UserActionID,
  UserID,
  UserStateEstimateID,
  WispUtteranceID,
} from "./ids";

// =============================================================================
// SHARED PRIMITIVES
// =============================================================================

/** ISO 8601 date-time string with timezone, e.g. "2026-05-17T03:30:00Z". */
export type ISODateTime = string;

/** UUID string (v4 or v7) used for any non-branded identifier. */
export type UUID = string;

// =============================================================================
// USER
// =============================================================================

export interface User {
  id: UserID;
  email: string;
  displayName: string;
  createdAt: ISODateTime;
}

// =============================================================================
// SLEEP — sessions, stages, classifications
// =============================================================================

/**
 * Standard sleep stages, aligned with AASM categories and Apple HealthKit.
 *  - AWAKE   : user is awake (or briefly aroused mid-night)
 *  - REM     : rapid eye movement, dreaming
 *  - CORE    : N1/N2 (Apple's term for light sleep)
 *  - DEEP    : N3, slow-wave sleep (SWS)
 *  - UNKNOWN : unclassified, sensor failure, or gap
 */
export type SleepStage = "AWAKE" | "REM" | "CORE" | "DEEP" | "UNKNOWN";

/** Where the sleep-stage classification came from. */
export type SleepStageSource =
  | "APPLE_HEALTHKIT" // Apple's own algorithm (post-hoc, from morning sync)
  | "DAYBOOK_CLASSIFIER" // Our Python pipeline (HR/HRV/sonar/audio based)
  | "EEG_GROUND_TRUTH" // Direct EEG-based detection from EXG Pill
  | "CAMERA_REM_DETECTOR" // ESP32-CAM eye-movement detector
  | "MANUAL"; // User-labeled (rare)

/** Where biometric sensor data came from. */
export type SensorSource =
  | "APPLE_WATCH"
  | "IPHONE_SONAR"
  | "IPHONE_AUDIO"
  | "ESP32_EXG_PILL"
  | "ESP32_CAM"
  | "WHOOP"
  | "OURA"
  | "MANUAL";

export interface SleepSession {
  id: SleepSessionID;
  userId: UserID;
  startedAt: ISODateTime;
  endedAt: ISODateTime;
  durationSeconds: number;
  /** Which sensor streams contributed data to this session — for traceability. */
  sensorSources: SensorSource[];
  iModelId: IModelID | null;
  notes: string | null;
  createdAt: ISODateTime;
}

/**
 * Sleep-stage classification for a single 30-second epoch.
 * Multiple sources can produce classifications for the same epoch
 * (e.g., HealthKit + Daybook classifier + EEG) — useful for cross-validation.
 */
export interface SleepStageClassification {
  id: SleepStageClassificationID;
  sessionId: SleepSessionID;
  epochStartAt: ISODateTime;
  stage: SleepStage;
  source: SleepStageSource;
  /** 0–1, where 1 is full confidence. */
  confidence: number;
  createdAt: ISODateTime;
}

// =============================================================================
// SENSOR READINGS — discriminated union (high-volume time series)
// =============================================================================

/**
 * A single sensor reading. Discriminated by `kind`.
 *
 * Stored in a TimescaleDB hypertable for time-based partitioning. Each
 * variant has its own payload shape; the SQL representation uses a
 * `kind TEXT` column + `payload JSONB` to hold the variant-specific data.
 */
export type SensorReading =
  | HeartRateReading
  | HRVReading
  | EEGReading
  | AccelerometerReading
  | TemperatureReading
  | SpO2Reading
  | RespiratoryRateReading
  | SonarBreathingReading
  | AudioClassificationReading;

interface SensorReadingBase {
  id: SensorReadingID;
  /** Null for daytime readings not tied to a sleep session. */
  sessionId: SleepSessionID | null;
  userId: UserID;
  recordedAt: ISODateTime;
  source: SensorSource;
}

export interface HeartRateReading extends SensorReadingBase {
  kind: "heart_rate";
  bpm: number;
}

export interface HRVReading extends SensorReadingBase {
  kind: "hrv";
  /** RMSSD in milliseconds — standard HRV metric. */
  rmssdMs: number;
}

export interface EEGReading extends SensorReadingBase {
  kind: "eeg";
  /** Electrode location label, e.g. "Fp1", "AF7", or "single" for one-channel rigs. */
  channel: string;
  /** Raw voltage samples in the batch. */
  samples: number[];
  sampleRateHz: number;
}

export interface AccelerometerReading extends SensorReadingBase {
  kind: "accelerometer";
  /** Acceleration in g on each axis. */
  x: number;
  y: number;
  z: number;
}

export interface TemperatureReading extends SensorReadingBase {
  kind: "temperature";
  /** Delta from baseline in °C (Apple's overnight format). */
  celsiusDelta: number;
}

export interface SpO2Reading extends SensorReadingBase {
  kind: "spo2";
  /** Oxygen saturation percentage, 0–100. */
  percent: number;
}

export interface RespiratoryRateReading extends SensorReadingBase {
  kind: "respiratory_rate";
  breathsPerMinute: number;
}

export interface SonarBreathingReading extends SensorReadingBase {
  kind: "sonar_breathing";
  breathsPerMinute: number;
  confidence: number;
}

export interface AudioClassificationReading extends SensorReadingBase {
  kind: "audio_classification";
  label: "snore" | "breath" | "movement" | "silence" | "speech";
  confidence: number;
  durationMs: number;
}

// =============================================================================
// DREAM RECALL — v1's success measurement substrate
// =============================================================================

/**
 * Depth of recall on a given morning.
 *  - NONE      : remembered nothing
 *  - FRAGMENT  : an image, feeling, or single sense impression
 *  - SCENE     : a coherent scene or episode
 *  - NARRATIVE : a full story arc with characters / progression
 */
export type RecallDepth = "NONE" | "FRAGMENT" | "SCENE" | "NARRATIVE";

export interface DreamRecall {
  id: DreamRecallID;
  userId: UserID;
  /** Which sleep session this recall is tied to. Null if uncertain. */
  sessionId: SleepSessionID | null;
  capturedAt: ISODateTime;
  depth: RecallDepth;
  /** Typed text or transcribed voice. The canonical content. */
  rawText: string;
  /** R2/S3 reference if the user recorded audio. Null if typed only. */
  voiceMemoUrl: string | null;
  /** Themes, either user-tagged or auto-extracted by the LLM layer. */
  themes: string[];
  iModelId: IModelID | null;
  createdAt: ISODateTime;
}

// =============================================================================
// WISP — utterances + cue events
// =============================================================================

/**
 * Discrete moments when the wisp speaks. v1 has ~10 scripted moments;
 * v2+ adds generative conversational moments.
 */
export type WispMomentKind =
  | "morning_recall_prompt" // "What do you remember?"
  | "morning_summary" // "You slept X hours. Here's what was cued."
  | "evening_intent_prompt" // "What's your intent for tonight?"
  | "pre_sleep_plan" // "Tonight I'll cue X during REM."
  | "daytime_checkin" // "HRV is low — break time?"
  | "cue_during_sleep" // Silent log entry for an in-sleep cue
  | "weekly_reflection" // "Your week in dreams."
  | "custom";

export interface WispUtterance {
  id: WispUtteranceID;
  userId: UserID;
  sessionId: SleepSessionID | null;
  kind: WispMomentKind;
  triggeredAt: ISODateTime;
  textContent: string;
  /** Path to rendered TTS audio file (R2 / local), null if not yet rendered. */
  audioRef: string | null;
  iModelId: IModelID | null;
  createdAt: ISODateTime;
}

/**
 * Record of an audio cue delivered during sleep.
 *
 * Distinct from WispUtterance because cues are not conversational — they're
 * TMR-style targeted audio meant to be heard *during* sleep, not at the
 * waking conversation interface.
 *
 * `contentType` is the polymorphism hook per the content-polymorphism
 * architectural commitment. v1: "recall_prompt". v1.5: "positive_anchor".
 * Future: "tmr_card" (memory consolidation), etc.
 */
export interface CueEvent {
  id: CueEventID;
  userId: UserID;
  sessionId: SleepSessionID;
  deliveredAt: ISODateTime;
  cueContent: string;
  contentType: "recall_prompt" | "positive_anchor" | "tmr_card" | "custom";
  /** What stage we intended to cue in. */
  targetStage: SleepStage;
  /** What stage was actually detected at delivery time. */
  actualStageAtDelivery: SleepStage | null;
  audioDurationMs: number;
  audioRef: string;
  /** Did downstream sensors register arousal/response? Null = not yet analyzed. */
  responseDetected: boolean | null;
  iModelId: IModelID | null;
}

// =============================================================================
// PERSONAL MODEL — embeddings + I-Models
// =============================================================================

/**
 * Vector embedding for any piece of text or content. Stored in pgvector.
 * Used for similarity retrieval across dream recalls, journal entries,
 * wisp utterances, etc.
 */
export interface Embedding {
  id: EmbeddingID;
  userId: UserID;
  /** What kind of entity the embedding is derived from. */
  sourceType:
    | "dream_recall"
    | "journal"
    | "wisp_utterance"
    | "biometric_summary"
    | "intent"
    | "custom";
  /** ID of the source entity (a DreamRecallID, WispUtteranceID, etc.). */
  sourceId: UUID;
  /** The vector itself. 1024 dimensions for BGE-M3 (current production model). */
  embedding: number[];
  /** Model identifier, e.g. "BAAI/bge-m3". */
  model: string;
  createdAt: ISODateTime;
}

/**
 * Who owns the cluster. There are three distinct I-Models in the system:
 *  - user_self       : the system's model of the user (what we know about you)
 *  - regis_of_user   : Regis's model of the user (what Regis has noticed about you)
 *  - regis_self      : Regis's evolving self-model (used sparingly; most
 *                      Regis-self state lives in regis_trait_history)
 */
export type IModelOwner = "user_self" | "regis_of_user" | "regis_self";

/**
 * A discovered I-Model cluster. Populated by ML clustering on accumulated
 * embeddings + biometric signatures. v1 doesn't actively classify; the
 * schema is present from day 1 per the I-Model architectural commitment.
 */
export interface IModelCluster {
  id: IModelID;
  userId: UserID;
  modelOwner: IModelOwner;
  /** User-given name once discovered ("Student-Aakash", "Tired-Aakash"). Null while unnamed. */
  label: string | null;
  /** Centroid of the cluster in embedding space. */
  centroidEmbedding: number[];
  discoveredAt: ISODateTime;
}

// =============================================================================
// WAKING-DAY INPUTS — intent, mood
// =============================================================================

export interface Intent {
  id: IntentID;
  userId: UserID;
  /** Typically set in the evening before sleep. */
  setAt: ISODateTime;
  intentText: string;
  /** Which sleep session this intent targets. Null if general. */
  targetSessionId: SleepSessionID | null;
  iModelId: IModelID | null;
}

/**
 * Mood / state self-report, using a valence-arousal model (Russell's circumplex).
 * Maps cleanly to PANAS and similar scales.
 */
export interface MoodReport {
  id: MoodReportID;
  userId: UserID;
  reportedAt: ISODateTime;
  /** -1 (very negative) to 1 (very positive). */
  valence: number;
  /** -1 (very calm) to 1 (very activated). */
  arousal: number;
  notes: string | null;
  iModelId: IModelID | null;
}

// =============================================================================
// REGIS — observations, drifting traits, empathic state
// =============================================================================

/**
 * What Regis has noticed about the user. Each row is a discrete, embeddable
 * observation. Retrieved by similarity at utterance-composition time so Regis's
 * voice reflects what he remembers about THIS user, not generic context.
 *
 * v1: empty (scripted utterances don't observe).
 * v1.5+: populated by a regis_observer job after each interaction or session.
 */
export interface RegisObservation {
  id: RegisObservationID;
  userId: UserID;
  observedAt: ISODateTime;
  /** Natural language note Regis would "remember" about the user. */
  observation: string;
  /** Snapshot of relevant sensor/state context at observation time. */
  context: Record<string, unknown>;
  /** Embedding for similarity retrieval. Null until embedded. */
  embedding: number[] | null;
  /** 0.0 (forgotten) to 1.0 (fresh). Decays over time to deprioritize old observations. */
  weight: number;
  /** Where the observation came from: 'regis_inference', 'user_feedback', etc. */
  source: string;
}

/**
 * Regis's drifting personality traits over time. Each row is a snapshot of one
 * trait at one moment. Latest row per (userId, traitName) is the current value;
 * older rows form the lineage of how Regis evolved through this relationship.
 *
 * Common traits (not enforced at the type level):
 *   - 'playfulness' — 0.0 reverent, 1.0 teasing
 *   - 'reverence'   — 0.0 casual, 1.0 ceremonious
 *   - 'chattiness'  — 0.0 silent, 1.0 verbose
 *   - 'directness'  — 0.0 hedged, 1.0 blunt
 *   - 'familiarity' — 0.0 formal, 1.0 intimate
 *   - 'humor'       — 0.0 dry, 1.0 absurd
 */
export interface RegisTrait {
  id: RegisTraitHistoryID;
  userId: UserID;
  traitName: string;
  /** 0.0 to 1.0. */
  value: number;
  changedAt: ISODateTime;
  /** Signed delta from the prior value, if known. */
  delta: number | null;
  /** Free-form note: why this trait drifted. */
  reason: string | null;
}

/**
 * Continuous empathic read of the user — one row PER AXIS (reshaped from the
 * old wide-row shape in migration 0009). Each row carries a single axis's
 * estimate at a point in time. L3 fusion and the sleep classifier each write
 * rows for the axes they own; readers take the latest row per axis
 * (DISTINCT ON (axis) ... ORDER BY axis, timestamp DESC).
 *
 * This is the substrate Regis queries to "know" what the user is feeling
 * without being told.
 */
export interface UserStateEstimate {
  id: UserStateEstimateID;
  userId: UserID;
  /** e.g. 'sleep_stage', 'arousal_inferred', 'meta_context', 'state_declared', 'cognitive_load'. */
  axis: string;
  timestamp: ISODateTime;
  /** Polymorphic per-axis value: {"category": "focused"} | {"scalar": 0.55} | {"label": "REM", "prob": 0.71}. */
  value: Record<string, unknown>;
  /** 0.0 to 1.0 — model's confidence in this axis estimate. */
  confidence: number | null;
  /** Which producer wrote this: 'L3.fusion.meta_context', 'classifier.binary_rem', etc. */
  source: string | null;
  /** Denormalized active meta-context: 'waking', 'sleep', or sub-context like 'waking/focused'. */
  metaContext: string | null;
  /** Commitment #1 — soft I-Model reference. */
  iModelId: IModelID | null;
  sessionId: SleepSessionID | null;
  createdAt: ISODateTime;
}

// =============================================================================
// REGIS MOMENTS + I-MODEL SELF-EXPANSION (migration 0003)
// =============================================================================

/**
 * Generalized "any context where Regis ever speaks or acts" log. Subsumes
 * CueEvent for the always-on companion architecture. Sleep cues, morning
 * recall prompts, walking remarks, conversation teases, news-pull comments —
 * all land here.
 *
 * CueEvent stays for backward compat; new code writes RegisMoment.
 */
export type RegisMomentKind =
  | "rem_whisper"
  | "pre_sleep_greeting"
  | "intent_setting"
  | "wake_greeting"
  | "morning_recall_prompt"
  | "capture_ack"
  | "walking_remark"
  | "conversation_tease"
  | "news_pull_comment"
  | "mood_check"
  | (string & {}); // permissive: new kinds can be added at runtime

export type RegisMode = "witness" | "companion" | "neutral";

export type RegisContentSource = "scripted_variant" | "generative_llm" | "system";

export interface RegisMoment {
  id: RegisMomentID;
  userId: UserID;
  sessionId: SleepSessionID | null;
  occurredAt: ISODateTime;
  kind: RegisMomentKind;
  mode: RegisMode;
  content: string;
  contentSource: RegisContentSource;
  audioRef: string | null;
  audioDurationMs: number | null;
  triggeringContext: Record<string, unknown>;
  /** Which I-Models were active when this moment was composed. */
  activeIModelIds: IModelID[];
  /** Primary I-Model link (legacy single-link pattern). */
  iModelId: IModelID | null;
  createdAt: ISODateTime;
}

/**
 * Many-to-many membership: one embedding can belong to multiple I-Model
 * clusters with different similarity scores. Honors the "neurons fire across
 * multiple I-Models" insight.
 */
export interface EmbeddingClusterMembership {
  embeddingId: EmbeddingID;
  clusterId: IModelID;
  /** Cosine similarity to cluster centroid. */
  similarity: number;
  assignedAt: ISODateTime;
  /** What process made this assignment: 'clusterer', 'novelty_detector', 'manual', etc. */
  assignmentSource: string;
}

/**
 * One row per "this I-Model was active at this moment." Written by the
 * activator job at decision time. Lets us query "what context was the system
 * in when Regis composed this utterance?" retrospectively.
 */
export interface IModelActivation {
  id: IModelActivationID;
  clusterId: IModelID;
  activatedAt: ISODateTime;
  /** 0.0 (faint) to 1.0 (strongly active). */
  activationStrength: number;
  source: string;
  context: Record<string, unknown>;
}

/**
 * Pre-clustering buffer. When current state doesn't fit any existing I-Model
 * well, it lands here. Enough accumulated novelty triggers a new clustering
 * run that may crystallize a new I-Model.
 */
export interface IModelNoveltyLog {
  id: IModelNoveltyLogID;
  userId: UserID;
  observedAt: ISODateTime;
  stateSnapshot: Record<string, unknown>;
  embedding: number[] | null;
  nearestClusterId: IModelID | null;
  nearestSimilarity: number | null;
  flaggedForClustering: boolean;
  clusteredIntoId: IModelID | null;
}

// =============================================================================
// USER ACTIONS — gestures + explicit commands (silent back-channel to Regis)
// =============================================================================

/**
 * Polymorphic kind for user_actions rows. Captures non-speech inputs from the
 * user (gestures, taps, grunts) plus explicit commands. Distinct from
 * chat_messages (voice/text speech) and sensor_readings (continuous context).
 */
export type UserActionKind =
  | "gesture_tap"
  | "gesture_nod"
  | "gesture_shake"
  | "gesture_wave"
  | "gesture_thumbs_up"
  | "gesture_thumbs_down"
  | "gesture_blink"
  | "voice_grunt"
  | "explicit_command"
  | (string & {});

/** Input device that produced the action. */
export type UserActionSource =
  | "headphone_button"
  | "apple_watch"
  | "camera"
  | "mic"
  | "cli"
  | "phone"
  | (string & {});

/** Inferred user intent — populated where determinable. */
export type UserActionIntent =
  | "acknowledge"
  | "dismiss"
  | "see"
  | "listen"
  | "expand"
  | "silence"
  | "yes"
  | "no"
  | "not_now"
  | "unknown"
  | (string & {});

export interface UserAction {
  id: UserActionID;
  userId: UserID;
  occurredAt: ISODateTime;
  kind: UserActionKind;
  source: UserActionSource;
  intent: UserActionIntent | null;
  context: Record<string, unknown>;
  /** If this action was a response to a specific Regis output, link to it. */
  triggeredBy: RegisMomentID | null;
  createdAt: ISODateTime;
}

// =============================================================================
// INTERJECT DECISIONS — auto-interject decider log
// =============================================================================

/** Which trigger fired the decider. New trigger kinds can be added at runtime. */
export type InterjectTriggerKind =
  | "post_recall"
  | "mood_shift"
  | "novel_scene"
  | "post_conversation"
  | (string & {});

/** Observed outcome of the decision, inferred from a following user action. */
export type InterjectUserOutcome = "positive" | "neutral" | "negative";

export interface InterjectDecision {
  id: InterjectDecisionID;
  userId: UserID;
  decidedAt: ISODateTime;
  triggerKind: InterjectTriggerKind;
  /** Snapshot of inputs the decider considered. */
  contextSnapshot: Record<string, unknown>;
  /** TRUE = spoke, FALSE = held silence. */
  decision: boolean;
  reason: string | null;
  /** If decision = true, links to the resulting regis_moments row. */
  resultingMomentId: RegisMomentID | null;
  userOutcome: InterjectUserOutcome | null;
  createdAt: ISODateTime;
}
