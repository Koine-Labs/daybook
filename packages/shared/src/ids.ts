/**
 * Branded ID types.
 *
 * Compile-time-only trick that prevents passing a UserID where a SleepSessionID
 * is expected, even though both are strings at runtime. Zero runtime cost —
 * pure type-system safety.
 *
 * Pattern:  `type UserID = string & { readonly __brand: 'UserID' }`
 *
 * To construct a branded ID from a raw string (e.g., from a DB row), use the
 * `asXxxID` helpers below. They are unchecked casts — only call them at the
 * trust boundary (when reading from the database or parsing API input).
 */

declare const __brand: unique symbol;
type Brand<T, B extends string> = T & { readonly [__brand]: B };

// All canonical IDs are UUID strings at runtime; the brand is the type-level tag.
export type UserID = Brand<string, "UserID">;
export type SleepSessionID = Brand<string, "SleepSessionID">;
export type DreamRecallID = Brand<string, "DreamRecallID">;
export type IModelID = Brand<string, "IModelID">;
export type WispUtteranceID = Brand<string, "WispUtteranceID">;
export type CueEventID = Brand<string, "CueEventID">;
export type SensorReadingID = Brand<string, "SensorReadingID">;
export type SleepStageClassificationID = Brand<string, "SleepStageClassificationID">;
export type EmbeddingID = Brand<string, "EmbeddingID">;
export type IntentID = Brand<string, "IntentID">;
export type MoodReportID = Brand<string, "MoodReportID">;
export type RegisObservationID = Brand<string, "RegisObservationID">;
export type RegisTraitHistoryID = Brand<string, "RegisTraitHistoryID">;
export type UserStateEstimateID = Brand<string, "UserStateEstimateID">;
export type RegisMomentID = Brand<string, "RegisMomentID">;
export type IModelActivationID = Brand<string, "IModelActivationID">;
export type IModelNoveltyLogID = Brand<string, "IModelNoveltyLogID">;
export type UserActionID = Brand<string, "UserActionID">;
export type InterjectDecisionID = Brand<string, "InterjectDecisionID">;

// Unchecked-cast helpers. Use only at trust boundaries (DB reads, API inputs).
export const asUserID = (s: string): UserID => s as UserID;
export const asSleepSessionID = (s: string): SleepSessionID => s as SleepSessionID;
export const asDreamRecallID = (s: string): DreamRecallID => s as DreamRecallID;
export const asIModelID = (s: string): IModelID => s as IModelID;
export const asWispUtteranceID = (s: string): WispUtteranceID => s as WispUtteranceID;
export const asCueEventID = (s: string): CueEventID => s as CueEventID;
export const asSensorReadingID = (s: string): SensorReadingID => s as SensorReadingID;
export const asSleepStageClassificationID = (s: string): SleepStageClassificationID =>
  s as SleepStageClassificationID;
export const asEmbeddingID = (s: string): EmbeddingID => s as EmbeddingID;
export const asIntentID = (s: string): IntentID => s as IntentID;
export const asMoodReportID = (s: string): MoodReportID => s as MoodReportID;
export const asRegisObservationID = (s: string): RegisObservationID => s as RegisObservationID;
export const asRegisTraitHistoryID = (s: string): RegisTraitHistoryID => s as RegisTraitHistoryID;
export const asUserStateEstimateID = (s: string): UserStateEstimateID => s as UserStateEstimateID;
export const asRegisMomentID = (s: string): RegisMomentID => s as RegisMomentID;
export const asIModelActivationID = (s: string): IModelActivationID => s as IModelActivationID;
export const asIModelNoveltyLogID = (s: string): IModelNoveltyLogID => s as IModelNoveltyLogID;
export const asUserActionID = (s: string): UserActionID => s as UserActionID;
export const asInterjectDecisionID = (s: string): InterjectDecisionID =>
  s as InterjectDecisionID;
