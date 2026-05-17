import { Hono } from "hono";
import type { Env, JWTPayload, SessionMetadataInput } from "../types";
import { authMiddleware, adminMiddleware } from "../middleware/auth";
import {
  uploadBlob,
  createSession,
  listSessions,
  getSession,
  downloadBlob,
  deleteSession,
  listAllSessions,
  uploadPredictions,
} from "../services/session.service";

type SessionEnv = { Bindings: Env; Variables: { user: JWTPayload } };

const sessions = new Hono<SessionEnv>();

// All routes require auth
sessions.use("/*", authMiddleware);

/** PUT /sessions/:id/blob — stream session JSON to R2 (step 1 of upload) */
sessions.put("/:id/blob", async (c) => {
  const sessionId = c.req.param("id");
  const userId = c.get("user").sub;

  try {
    const { blobKey, sizeBytes } = await uploadBlob(
      c.env,
      userId,
      sessionId,
      c.req.raw.body
    );

    return c.json({ blobKey, sizeBytes });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "Upload failed";
    return c.json({ error: msg }, 500);
  }
});

/** POST /sessions — register session metadata in D1 (step 2 of upload) */
sessions.post("/", async (c) => {
  const userId = c.get("user").sub;
  const input = await c.req.json<SessionMetadataInput>();

  if (!input.id || !input.startDate) {
    return c.json({ error: "id and startDate are required" }, 400);
  }

  const blobKey = `sessions/${userId}/${input.id}.json`;

  // Verify blob exists in R2
  const headResult = await c.env.BUCKET.head(blobKey);
  if (!headResult) {
    return c.json(
      { error: "Blob not found — upload via PUT /sessions/:id/blob first" },
      400
    );
  }

  try {
    const session = await createSession(
      c.env,
      userId,
      input,
      blobKey,
      headResult.size
    );
    return c.json(session, 201);
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "Failed to create session";
    return c.json({ error: msg }, 500);
  }
});

/** GET /sessions — list user's sessions */
sessions.get("/", async (c) => {
  const userId = c.get("user").sub;
  const rows = await listSessions(c.env, userId);
  return c.json({ sessions: rows });
});

/** GET /sessions/:id/download — download session JSON from R2 */
sessions.get("/:id/download", async (c) => {
  const userId = c.get("user").sub;
  const sessionId = c.req.param("id");

  const session = await getSession(c.env, userId, sessionId);
  if (!session) {
    return c.json({ error: "Session not found" }, 404);
  }

  const object = await downloadBlob(c.env, session.blob_key);
  if (!object) {
    return c.json({ error: "Session blob not found in storage" }, 404);
  }

  return new Response(object.body, {
    headers: {
      "Content-Type": "application/json",
      "Content-Length": String(object.size),
      "Content-Disposition": `attachment; filename="${sessionId}.json"`,
    },
  });
});

/** PUT /sessions/:id/predictions — upload prediction results to R2 */
sessions.put("/:id/predictions", async (c) => {
  const userId = c.get("user").sub;
  const sessionId = c.req.param("id");

  try {
    const result = await uploadPredictions(c.env, userId, sessionId, c.req.raw.body);
    return c.json(result, 201);
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "Upload failed";
    if (msg === "Session not found") {
      return c.json({ error: msg }, 404);
    }
    return c.json({ error: msg }, 500);
  }
});

/** DELETE /sessions/:id — remove session + blob */
sessions.delete("/:id", async (c) => {
  const userId = c.get("user").sub;
  const sessionId = c.req.param("id");

  const deleted = await deleteSession(c.env, userId, sessionId);
  if (!deleted) {
    return c.json({ error: "Session not found" }, 404);
  }

  return c.json({ success: true });
});

/** GET /sessions/admin/all — list all sessions across users (admin only) */
sessions.get("/admin/all", adminMiddleware, async (c) => {
  const rows = await listAllSessions(c.env);
  return c.json({ sessions: rows });
});

export default sessions;
