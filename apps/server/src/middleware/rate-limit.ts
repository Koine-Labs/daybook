import type { Context, Next } from "hono";
import type { Env, JWTPayload } from "../types";

/**
 * Simple in-memory rate limiter for auth endpoints.
 *
 * Uses a Map that resets per isolate lifecycle (acceptable for Workers
 * where each request may hit a different isolate). This provides
 * per-isolate protection against brute force without external state.
 *
 * For production, consider Cloudflare Rate Limiting rules instead.
 */

interface RateLimitEntry {
  count: number;
  resetAt: number;
}

const store = new Map<string, RateLimitEntry>();

/** Create a rate limiter middleware. */
export function rateLimit(opts: {
  windowMs: number;
  maxRequests: number;
}) {
  return async (
    c: Context<{ Bindings: Env; Variables: { user: JWTPayload } }>,
    next: Next
  ) => {
    const key = c.req.header("CF-Connecting-IP") || "unknown";
    const now = Date.now();

    let entry = store.get(key);
    if (!entry || now > entry.resetAt) {
      entry = { count: 0, resetAt: now + opts.windowMs };
      store.set(key, entry);
    }

    entry.count++;

    if (entry.count > opts.maxRequests) {
      const retryAfter = Math.ceil((entry.resetAt - now) / 1000);
      c.header("Retry-After", String(retryAfter));
      return c.json({ error: "Too many requests" }, 429);
    }

    await next();
  };
}
