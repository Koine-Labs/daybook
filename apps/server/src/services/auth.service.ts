import type { Env, UserRow, AuthTokens, RefreshTokenRow } from "../types";
import { hashPassword, verifyPassword, sha256 } from "../utils/crypto";
import { signAccessToken, generateRefreshToken } from "../utils/jwt";

/** Register a new user with email + password. */
export async function registerUser(
  env: Env,
  email: string,
  password: string,
  displayName?: string
): Promise<{ user: UserRow; tokens: AuthTokens }> {
  // Check existing
  const existing = await env.DB.prepare(
    "SELECT id FROM users WHERE email = ?"
  )
    .bind(email)
    .first();
  if (existing) {
    throw new Error("Email already registered");
  }

  const id = crypto.randomUUID();
  const passwordHash = await hashPassword(password);
  const now = new Date().toISOString();

  await env.DB.prepare(
    `INSERT INTO users (id, email, display_name, password_hash, auth_provider, role, created_at, updated_at)
     VALUES (?, ?, ?, ?, 'email', 'user', ?, ?)`
  )
    .bind(id, email, displayName || null, passwordHash, now, now)
    .run();

  const user: UserRow = {
    id,
    email,
    display_name: displayName || null,
    password_hash: passwordHash,
    auth_provider: "email",
    auth_provider_id: null,
    role: "user",
    created_at: now,
    updated_at: now,
  };

  const tokens = await createTokens(env, user);
  return { user, tokens };
}

/** Login with email + password. */
export async function loginUser(
  env: Env,
  email: string,
  password: string
): Promise<{ user: UserRow; tokens: AuthTokens }> {
  const user = await env.DB.prepare("SELECT * FROM users WHERE email = ?")
    .bind(email)
    .first<UserRow>();

  if (!user || !user.password_hash) {
    throw new Error("Invalid email or password");
  }

  const valid = await verifyPassword(password, user.password_hash);
  if (!valid) {
    throw new Error("Invalid email or password");
  }

  const tokens = await createTokens(env, user);
  return { user, tokens };
}

/** Refresh an access token using a refresh token. */
export async function refreshTokens(
  env: Env,
  refreshToken: string
): Promise<AuthTokens> {
  const tokenHash = await sha256(refreshToken);

  const row = await env.DB.prepare(
    `SELECT rt.*, u.email, u.role FROM refresh_tokens rt
     JOIN users u ON u.id = rt.user_id
     WHERE rt.token_hash = ? AND rt.revoked = 0`
  )
    .bind(tokenHash)
    .first<RefreshTokenRow & { email: string; role: string }>();

  if (!row) {
    throw new Error("Invalid refresh token");
  }

  if (new Date(row.expires_at) < new Date()) {
    throw new Error("Refresh token expired");
  }

  // Rotate: revoke old, create new
  await env.DB.prepare("UPDATE refresh_tokens SET revoked = 1 WHERE id = ?")
    .bind(row.id)
    .run();

  const ttl = parseInt(env.ACCESS_TOKEN_TTL) || 900;
  const refreshTtl = parseInt(env.REFRESH_TOKEN_TTL) || 2592000;

  const accessToken = await signAccessToken(
    { sub: row.user_id, email: row.email, role: row.role },
    env.JWT_SECRET,
    ttl
  );

  const newRefresh = generateRefreshToken();
  const newRefreshHash = await sha256(newRefresh);
  const expiresAt = new Date(
    Date.now() + refreshTtl * 1000
  ).toISOString();

  await env.DB.prepare(
    `INSERT INTO refresh_tokens (id, user_id, token_hash, expires_at)
     VALUES (?, ?, ?, ?)`
  )
    .bind(crypto.randomUUID(), row.user_id, newRefreshHash, expiresAt)
    .run();

  return { accessToken, refreshToken: newRefresh, expiresIn: ttl };
}

/** Revoke a refresh token (logout). */
export async function revokeRefreshToken(
  env: Env,
  refreshToken: string
): Promise<void> {
  const tokenHash = await sha256(refreshToken);
  await env.DB.prepare(
    "UPDATE refresh_tokens SET revoked = 1 WHERE token_hash = ?"
  )
    .bind(tokenHash)
    .run();
}

/** Create access + refresh tokens for a user. */
export async function createTokens(
  env: Env,
  user: UserRow
): Promise<AuthTokens> {
  const ttl = parseInt(env.ACCESS_TOKEN_TTL) || 900;
  const refreshTtl = parseInt(env.REFRESH_TOKEN_TTL) || 2592000;

  const accessToken = await signAccessToken(
    { sub: user.id, email: user.email, role: user.role },
    env.JWT_SECRET,
    ttl
  );

  const refreshToken = generateRefreshToken();
  const tokenHash = await sha256(refreshToken);
  const expiresAt = new Date(
    Date.now() + refreshTtl * 1000
  ).toISOString();

  await env.DB.prepare(
    `INSERT INTO refresh_tokens (id, user_id, token_hash, expires_at)
     VALUES (?, ?, ?, ?)`
  )
    .bind(crypto.randomUUID(), user.id, tokenHash, expiresAt)
    .run();

  return { accessToken, refreshToken, expiresIn: ttl };
}
