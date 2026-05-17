import { cors } from "hono/cors";
import type { Env } from "../types";

export function corsMiddleware() {
  return cors({
    origin: (origin, c) => {
      const allowed = (c.env as Env).CORS_ORIGIN;
      if (allowed === "*") return origin || "*";
      return allowed;
    },
    allowMethods: ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allowHeaders: ["Content-Type", "Authorization"],
    exposeHeaders: ["Content-Length"],
    maxAge: 86400,
  });
}
