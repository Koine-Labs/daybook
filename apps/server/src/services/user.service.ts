import type { Env, UserRow, UserProfile } from "../types";

/** Convert a DB row to a public profile. */
export function toProfile(row: UserRow): UserProfile {
  return {
    id: row.id,
    email: row.email,
    displayName: row.display_name,
    authProvider: row.auth_provider,
    role: row.role,
    createdAt: row.created_at,
  };
}

/** Get user by ID. */
export async function getUserById(
  env: Env,
  userId: string
): Promise<UserRow | null> {
  return env.DB.prepare("SELECT * FROM users WHERE id = ?")
    .bind(userId)
    .first<UserRow>();
}

/** Update user profile fields. */
export async function updateUser(
  env: Env,
  userId: string,
  updates: { displayName?: string }
): Promise<UserRow | null> {
  const fields: string[] = [];
  const values: (string | null)[] = [];

  if (updates.displayName !== undefined) {
    fields.push("display_name = ?");
    values.push(updates.displayName);
  }

  if (fields.length === 0) return getUserById(env, userId);

  fields.push("updated_at = ?");
  values.push(new Date().toISOString());
  values.push(userId);

  await env.DB.prepare(
    `UPDATE users SET ${fields.join(", ")} WHERE id = ?`
  )
    .bind(...values)
    .run();

  return getUserById(env, userId);
}

/** List all users (admin). */
export async function listUsers(
  env: Env
): Promise<UserProfile[]> {
  const { results } = await env.DB.prepare(
    "SELECT * FROM users ORDER BY created_at DESC"
  ).all<UserRow>();

  return results.map(toProfile);
}

/** Find or create a user from an OAuth provider. */
export async function findOrCreateOAuthUser(
  env: Env,
  provider: string,
  providerId: string,
  email: string,
  displayName?: string
): Promise<UserRow> {
  // Check by provider ID first
  let user = await env.DB.prepare(
    "SELECT * FROM users WHERE auth_provider = ? AND auth_provider_id = ?"
  )
    .bind(provider, providerId)
    .first<UserRow>();

  if (user) return user;

  // Check by email (link accounts)
  user = await env.DB.prepare("SELECT * FROM users WHERE email = ?")
    .bind(email)
    .first<UserRow>();

  if (user) {
    // Link the OAuth provider to existing account
    await env.DB.prepare(
      `UPDATE users SET auth_provider = ?, auth_provider_id = ?, updated_at = ? WHERE id = ?`
    )
      .bind(provider, providerId, new Date().toISOString(), user.id)
      .run();
    return { ...user, auth_provider: provider, auth_provider_id: providerId };
  }

  // Create new user
  const id = crypto.randomUUID();
  const now = new Date().toISOString();

  await env.DB.prepare(
    `INSERT INTO users (id, email, display_name, auth_provider, auth_provider_id, role, created_at, updated_at)
     VALUES (?, ?, ?, ?, ?, 'user', ?, ?)`
  )
    .bind(id, email, displayName || null, provider, providerId, now, now)
    .run();

  return {
    id,
    email,
    display_name: displayName || null,
    password_hash: null,
    auth_provider: provider,
    auth_provider_id: providerId,
    role: "user",
    created_at: now,
    updated_at: now,
  };
}
