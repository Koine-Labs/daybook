// packages/shared/src/protocol.ts
/**
 * Daybook nervous-system message protocol — TS mirror of
 * apps/inference/core/protocol/*. Field names are camelCase here; the Python
 * side is snake_case. JSON on the wire uses the Python (snake_case) names.
 */
import type { ISODateTime, UUID } from "./types";

export type NodeRole = "wisp_edge" | "phone_relay" | "desktop_compute" | "cloud";
export type MetaContext = "waking" | "sleep" | "unknown";
export type Modality =
  | "voice" | "text" | "gesture" | "biometric" | "audio" | "vision" | "bci";
export type Intent = "explicit" | "continuous";
export type PayloadType =
  | "signal" | "feature" | "belief" | "prediction" | "action" | "output";

export interface SignalPacket {
  userId: UUID;
  timestamp: ISODateTime;
  modality: Modality;
  intent: Intent;
  kind: string;
  payload: Record<string, unknown>;
  source: string;
  confidence?: number | null;
  iModelId?: UUID | null;
}

/** L2 payload — mirror of FeatureSnapshot. */
export interface FeaturePacket {
  userId: UUID;
  timestamp: ISODateTime;
  modality: string;
  source: string;
  payload: Record<string, unknown>;
  intent: Intent;
  confidence?: number | null;
  durationMs?: number | null;
  metaContextHint?: string | null;
  iModelId?: UUID | null;
}

export interface AxisEstimate {
  axis: string;
  value: Record<string, unknown>;
  timestamp: ISODateTime;
  confidence: number | null;
  source: string;
  metaContext?: string | null;
  iModelId?: UUID | null;
  freshForSeconds: number;
}

export interface BeliefState {
  userId: UUID;
  estimates: Record<string, AxisEstimate>;
}

export interface Prediction {
  userId: UUID;
  axis: string;
  madeAt: ISODateTime;
  horizonSeconds: number;
  distribution: Record<string, unknown>;
  modelId: string;
  confidence?: number | null;
  action?: Record<string, unknown> | null;
  provenance: "placeholder" | "calibrated";
  coldStart: boolean;
  iModelId?: UUID | null;
}

export interface ActionDecision {
  userId: UUID;
  decidedAt: ISODateTime;
  action: "interject" | "hold";
  rationale: string;
  mode?: "witness" | "companion" | null;
  contentKind?: string | null;
  gateTrace: Record<string, unknown>;
  iModelId?: UUID | null;
}

export interface OutputDirective {
  userId: UUID;
  createdAt: ISODateTime;
  channel: "voice" | "haptic" | "visual";
  mode?: "witness" | "companion" | null;
  text?: string | null;
  delivery: Record<string, unknown>;
  iModelId?: UUID | null;
}

export type Payload =
  | SignalPacket | FeaturePacket | BeliefState | Prediction
  | ActionDecision | OutputDirective;

export interface MessageEnvelope {
  id: UUID;
  type: PayloadType;
  schemaVersion: number;
  sourceRole: NodeRole;
  targetRole?: NodeRole | null;
  occurredAt: ISODateTime;
  metaContext: MetaContext;
  consentScope: string;
  traceId: UUID;
  iModelId?: UUID | null;
  payload: Payload;
}
