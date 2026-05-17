import type { Context, Next } from "hono";
import { verifyAccessToken } from "../utils/jwt";
import type { Env, JWTPayload } from "../types";

/** Require a valid Bearer token. Sets c.set("user", payload). */
export async function authMiddleware(
  c: Context<{ Bindings: Env; Variables: { user: JWTPayload } }>,
  next: Next
) {
  const header = c.req.header("Authorization");
  if (!header?.startsWith("Bearer ")) {
    return c.json({ error: "Missing or invalid Authorization header" }, 401);
  }

  const token = header.slice(7);
  const payload = await verifyAccessToken(token, c.env.JWT_SECRET);
  if (!payload) {
    return c.json({ error: "Invalid or expired token" }, 401);
  }

  c.set("user", payload);
  await next();
}

/** Require admin role (must be used after authMiddleware). */
export async function adminMiddleware(
  c: Context<{ Bindings: Env; Variables: { user: JWTPayload } }>,
  next: Next
) {
  const user = c.get("user");
  if (user.role !== "admin") {
    return c.json({ error: "Admin access required" }, 403);
  }
  await next();
}
