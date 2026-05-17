/** Cloudflare Workers environment bindings */
export interface Env {
  DB: D1Database;
  BUCKET: R2Bucket;
  JWT_SECRET: string;
  CORS_ORIGIN: string;
  ACCESS_TOKEN_TTL: string;
  REFRESH_TOKEN_TTL: string;
  GOOGLE_CLIENT_ID?: string;
  APPLE_BUNDLE_ID?: string;
}

/** JWT access token payload */
export interface JWTPayload {
  sub: string; // user ID
  email: string;
  role: string;
  iat: number;
  exp: number;
}

/** D1 user row */
export interface UserRow {
  id: string;
  email: string;
  display_name: string | null;
  password_hash: string | null;
  auth_provider: string;
  auth_provider_id: string | null;
  role: string;
  created_at: string;
  updated_at: string;
}

/** D1 session row */
export interface SessionRow {
  id: string;
  user_id: string;
  start_date: string;
  end_date: string | null;
  duration_seconds: number | null;
  watch_packet_count: number;
  sleep_stage_count: number;
  blob_key: string;
  size_bytes: number;
  uploaded_at: string;
  notes: string | null;
}

/** D1 refresh token row */
export interface RefreshTokenRow {
  id: string;
  user_id: string;
  token_hash: string;
  expires_at: string;
  revoked: number;
  created_at: string;
}

/** Session metadata sent by the iOS app during POST /sessions */
export interface SessionMetadataInput {
  id: string;
  startDate: string;
  endDate?: string;
  durationSeconds?: number;
  watchPacketCount?: number;
  sleepStageCount?: number;
  notes?: string;
}

/** Public user profile (no password hash) */
export interface UserProfile {
  id: string;
  email: string;
  displayName: string | null;
  authProvider: string;
  role: string;
  createdAt: string;
}

/** Auth tokens returned after login/register */
export interface AuthTokens {
  accessToken: string;
  refreshToken: string;
  expiresIn: number;
}
