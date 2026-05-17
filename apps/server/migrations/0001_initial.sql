-- Lullaby Phase 2.5: Initial schema
-- Users, sessions, and refresh tokens

CREATE TABLE users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    display_name TEXT,
    password_hash TEXT,
    auth_provider TEXT NOT NULL DEFAULT 'email',
    auth_provider_id TEXT,
    role TEXT NOT NULL DEFAULT 'user',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    start_date TEXT NOT NULL,
    end_date TEXT,
    duration_seconds REAL,
    watch_packet_count INTEGER NOT NULL DEFAULT 0,
    sleep_stage_count INTEGER NOT NULL DEFAULT 0,
    blob_key TEXT NOT NULL,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    uploaded_at TEXT NOT NULL DEFAULT (datetime('now')),
    notes TEXT
);

CREATE INDEX idx_sessions_user_id ON sessions(user_id);
CREATE INDEX idx_sessions_start_date ON sessions(start_date);

CREATE TABLE refresh_tokens (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    token_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE INDEX idx_refresh_tokens_token_hash ON refresh_tokens(token_hash);
