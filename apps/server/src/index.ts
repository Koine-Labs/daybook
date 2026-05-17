import { Hono } from "hono";
import type { Env, JWTPayload } from "./types";
import { corsMiddleware } from "./middleware/cors";
import auth from "./routes/auth";
import sessions from "./routes/sessions";
import users from "./routes/users";

type AppEnv = { Bindings: Env; Variables: { user: JWTPayload } };

const app = new Hono<AppEnv>();

// Global middleware
app.use("/*", corsMiddleware());

// Health check
app.get("/", (c) => c.json({ service: "lullaby", version: "0.1.0" }));
app.get("/health", (c) => c.json({ status: "ok" }));

// Route groups
app.route("/auth", auth);
app.route("/sessions", sessions);
app.route("/users", users);

// 404 fallback
app.notFound((c) => c.json({ error: "Not found" }, 404));

// Error handler
app.onError((err, c) => {
  console.error("Unhandled error:", err);
  return c.json({ error: "Internal server error" }, 500);
});

export default app;
