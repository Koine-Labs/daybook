import { Hono } from "hono";
import type { Env, JWTPayload } from "../types";
import {
  registerUser,
  loginUser,
  refreshTokens,
  revokeRefreshToken,
  createTokens,
} from "../services/auth.service";
import { findOrCreateOAuthUser } from "../services/user.service";
import { verifyGoogleToken } from "../utils/google-auth";
import { verifyAppleToken } from "../utils/apple-auth";
import { rateLimit } from "../middleware/rate-limit";

type AuthEnv = { Bindings: Env; Variables: { user: JWTPayload } };

const auth = new Hono<AuthEnv>();

// Rate limit all auth endpoints: 20 requests per minute per IP
auth.use("/*", rateLimit({ windowMs: 60_000, maxRequests: 20 }));

/** POST /auth/register — create account with email + password */
auth.post("/register", async (c) => {
  const body = await c.req.json<{
    email: string;
    password: string;
    displayName?: string;
  }>();

  if (!body.email || !body.password) {
    return c.json({ error: "Email and password are required" }, 400);
  }

  if (body.password.length < 8) {
    return c.json({ error: "Password must be at least 8 characters" }, 400);
  }

  try {
    const { user, tokens } = await registerUser(
      c.env,
      body.email.toLowerCase().trim(),
      body.password,
      body.displayName
    );

    return c.json(
      {
        user: {
          id: user.id,
          email: user.email,
          displayName: user.display_name,
          role: user.role,
        },
        ...tokens,
      },
      201
    );
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "Registration failed";
    if (msg.includes("already registered")) {
      return c.json({ error: msg }, 409);
    }
    return c.json({ error: msg }, 500);
  }
});

/** POST /auth/login — sign in with email + password */
auth.post("/login", async (c) => {
  const body = await c.req.json<{ email: string; password: string }>();

  if (!body.email || !body.password) {
    return c.json({ error: "Email and password are required" }, 400);
  }

  try {
    const { user, tokens } = await loginUser(
      c.env,
      body.email.toLowerCase().trim(),
      body.password
    );

    return c.json({
      user: {
        id: user.id,
        email: user.email,
        displayName: user.display_name,
        role: user.role,
      },
      ...tokens,
    });
  } catch {
    return c.json({ error: "Invalid email or password" }, 401);
  }
});

/** POST /auth/refresh — exchange refresh token for new access token */
auth.post("/refresh", async (c) => {
  const body = await c.req.json<{ refreshToken: string }>();

  if (!body.refreshToken) {
    return c.json({ error: "Refresh token is required" }, 400);
  }

  try {
    const tokens = await refreshTokens(c.env, body.refreshToken);
    return c.json(tokens);
  } catch {
    return c.json({ error: "Invalid or expired refresh token" }, 401);
  }
});

/** POST /auth/logout — revoke refresh token */
auth.post("/logout", async (c) => {
  const body = await c.req.json<{ refreshToken: string }>();

  if (body.refreshToken) {
    await revokeRefreshToken(c.env, body.refreshToken);
  }

  return c.json({ success: true });
});

/** POST /auth/google — sign in with Google ID token */
auth.post("/google", async (c) => {
  const body = await c.req.json<{ idToken: string }>();

  if (!body.idToken) {
    return c.json({ error: "Google ID token is required" }, 400);
  }

  const clientId = c.env.GOOGLE_CLIENT_ID;
  if (!clientId) {
    return c.json({ error: "Google Sign-In not configured" }, 501);
  }

  try {
    const googleUser = await verifyGoogleToken(body.idToken, clientId);
    const user = await findOrCreateOAuthUser(
      c.env,
      "google",
      googleUser.sub,
      googleUser.email,
      googleUser.name
    );
    const tokens = await createTokens(c.env, user);

    return c.json({
      user: {
        id: user.id,
        email: user.email,
        displayName: user.display_name,
        role: user.role,
      },
      ...tokens,
    });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "Google auth failed";
    return c.json({ error: msg }, 401);
  }
});

/** POST /auth/apple — sign in with Apple identity token */
auth.post("/apple", async (c) => {
  const body = await c.req.json<{
    identityToken: string;
    email?: string;
    fullName?: string;
  }>();

  if (!body.identityToken) {
    return c.json({ error: "Apple identity token is required" }, 400);
  }

  const bundleId = c.env.APPLE_BUNDLE_ID;
  if (!bundleId) {
    return c.json({ error: "Apple Sign-In not configured" }, 501);
  }

  try {
    const appleUser = await verifyAppleToken(body.identityToken, bundleId);

    // Apple only provides email on first sign-in; use client-provided fallback
    const email = appleUser.email || body.email;
    if (!email) {
      return c.json({ error: "Email is required for account creation" }, 400);
    }

    const user = await findOrCreateOAuthUser(
      c.env,
      "apple",
      appleUser.sub,
      email,
      body.fullName
    );
    const tokens = await createTokens(c.env, user);

    return c.json({
      user: {
        id: user.id,
        email: user.email,
        displayName: user.display_name,
        role: user.role,
      },
      ...tokens,
    });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "Apple auth failed";
    return c.json({ error: msg }, 401);
  }
});

export default auth;
