import type { Env, SessionRow, SessionMetadataInput } from "../types";

/** Store a session blob in R2. Streams the body directly (no buffering). */
export async function uploadBlob(
  env: Env,
  userId: string,
  sessionId: string,
  body: ReadableStream | ArrayBuffer | null
): Promise<{ blobKey: string; sizeBytes: number }> {
  if (!body) throw new Error("Empty request body");

  const blobKey = `sessions/${userId}/${sessionId}.json`;
  const result = await env.BUCKET.put(blobKey, body, {
    httpMetadata: { contentType: "application/json" },
  });

  return { blobKey, sizeBytes: result?.size ?? 0 };
}

/** Register session metadata in D1. */
export async function createSession(
  env: Env,
  userId: string,
  input: SessionMetadataInput,
  blobKey: string,
  sizeBytes: number
): Promise<SessionRow> {
  const now = new Date().toISOString();

  await env.DB.prepare(
    `INSERT INTO sessions (id, user_id, start_date, end_date, duration_seconds,
     watch_packet_count, sleep_stage_count, blob_key, size_bytes, uploaded_at, notes)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
  )
    .bind(
      input.id,
      userId,
      input.startDate,
      input.endDate || null,
      input.durationSeconds || null,
      input.watchPacketCount || 0,
      input.sleepStageCount || 0,
      blobKey,
      sizeBytes,
      now,
      input.notes || null
    )
    .run();

  return {
    id: input.id,
    user_id: userId,
    start_date: input.startDate,
    end_date: input.endDate || null,
    duration_seconds: input.durationSeconds || null,
    watch_packet_count: input.watchPacketCount || 0,
    sleep_stage_count: input.sleepStageCount || 0,
    blob_key: blobKey,
    size_bytes: sizeBytes,
    uploaded_at: now,
    notes: input.notes || null,
  };
}

/** List all sessions for a user. */
export async function listSessions(
  env: Env,
  userId: string
): Promise<SessionRow[]> {
  const { results } = await env.DB.prepare(
    "SELECT * FROM sessions WHERE user_id = ? ORDER BY start_date DESC"
  )
    .bind(userId)
    .all<SessionRow>();

  return results;
}

/** Get a single session (with ownership check). */
export async function getSession(
  env: Env,
  userId: string,
  sessionId: string
): Promise<SessionRow | null> {
  return env.DB.prepare(
    "SELECT * FROM sessions WHERE id = ? AND user_id = ?"
  )
    .bind(sessionId, userId)
    .first<SessionRow>();
}

/** Download session blob from R2. Returns the R2 object or null. */
export async function downloadBlob(
  env: Env,
  blobKey: string
): Promise<R2ObjectBody | null> {
  return env.BUCKET.get(blobKey);
}

/** Delete a session (metadata + blob). */
export async function deleteSession(
  env: Env,
  userId: string,
  sessionId: string
): Promise<boolean> {
  const session = await getSession(env, userId, sessionId);
  if (!session) return false;

  await env.BUCKET.delete(session.blob_key);
  await env.DB.prepare("DELETE FROM sessions WHERE id = ? AND user_id = ?")
    .bind(sessionId, userId)
    .run();

  return true;
}

/** Upload prediction results to R2, keyed by session (with ownership check). */
export async function uploadPredictions(
  env: Env,
  userId: string,
  sessionId: string,
  body: ReadableStream | ArrayBuffer | string | null,
): Promise<{ key: string; sizeBytes: number }> {
  const session = await env.DB.prepare(
    "SELECT id FROM sessions WHERE id = ? AND user_id = ?"
  ).bind(sessionId, userId).first<{ id: string }>();

  if (!session) {
    throw new Error("Session not found");
  }

  const key = `predictions/${sessionId}.json`;
  const result = await env.BUCKET.put(key, body, {
    httpMetadata: { contentType: "application/json" },
  });

  return { key, sizeBytes: result?.size ?? 0 };
}

/** List all sessions across all users (admin). */
export async function listAllSessions(
  env: Env
): Promise<(SessionRow & { email?: string })[]> {
  const { results } = await env.DB.prepare(
    `SELECT s.*, u.email FROM sessions s
     JOIN users u ON u.id = s.user_id
     ORDER BY s.start_date DESC`
  ).all<SessionRow & { email: string }>();

  return results;
}
