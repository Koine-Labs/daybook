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
  IModelID,
  IntentID,
  MoodReportID,
  SensorReadingID,
  SleepSessionID,
  SleepStageClassificationID,
  UserID,
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
  /** The vector itself. Typically 1536 dimensions for OpenAI text-embedding-3-small. */
  embedding: number[];
  /** Model identifier, e.g. "text-embedding-3-small". */
  model: string;
  createdAt: ISODateTime;
}

/**
 * A discovered I-Model cluster. Populated by ML clustering on accumulated
 * embeddings + biometric signatures. v1 doesn't actively classify; the
 * schema is present from day 1 per the I-Model architectural commitment.
 */
export interface IModelCluster {
  id: IModelID;
  userId: UserID;
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
