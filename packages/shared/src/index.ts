// Public surface of @daybook/shared.
// Other workspaces (apps/web, apps/inference, apps/ios) import from here.

export * from "./ids";
export * from "./types";
// `./protocol` also exports an `Intent` (communication-intent enum) that
// collides with the `Intent` entity in `./types`. Re-export the protocol type
// under `CommunicationIntent` to resolve the ambiguity; everything else is
// re-exported as-is.
export type { Intent as CommunicationIntent } from "./protocol";
export type {
  NodeRole,
  MetaContext,
  Modality,
  PayloadType,
  SignalPacket,
  FeaturePacket,
  AxisEstimate,
  BeliefState,
  Prediction,
  ActionDecision,
  OutputDirective,
  Payload,
  MessageEnvelope,
} from "./protocol";
