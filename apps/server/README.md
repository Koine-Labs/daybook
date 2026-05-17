# @daybook/server

Cloudflare Workers data server for Daybook. Migrated from `Lullaby/server/` (renamed from `lullaby-server` to `@daybook/server`).

## Scope

TypeScript on Cloudflare Workers using the Hono framework. Handles:

- **Auth** — email+password (PBKDF2), Google Sign-In, Sign in with Apple. JWT issuance via `jose`.
- **Session storage** — D1 (SQLite) for user/session metadata, R2 for session JSON blobs.
- **Session upload/download** — multi-user data isolation for the iOS/watchOS app and the offline analysis CLI.

This is the data transport layer. Real-time inference lives in `apps/inference/` (Python FastAPI).

## Layout

```
apps/server/
├── src/                    Hono app source
│   ├── routes/             auth, sessions, users
│   ├── middleware/         JWT auth, CORS
│   ├── services/           Business logic
│   └── utils/              Crypto, JWT, OAuth helpers
├── migrations/             D1 SQL schema
├── wrangler.toml           Cloudflare bindings (D1 + R2)
└── package.json            hono, jose, wrangler
```

## Development

```bash
pnpm dev                     # wrangler dev (local)
pnpm deploy                  # wrangler deploy
pnpm migrate:local           # apply D1 migrations locally
pnpm migrate:remote          # apply D1 migrations to remote
```
