# @daybook/shared

The conceptual source of truth for Daybook's data model.

This package defines the TypeScript types that every other Daybook workspace
agrees on:

- `apps/web` — Next.js web app
- `apps/inference` — Python FastAPI pipeline (consumes a generated Python copy or hand-mirrored equivalents)
- `apps/ios` — Swift iOS + watchOS app (consumes hand-mirrored Swift equivalents)
- `apps/server` — Cloudflare Workers data server

## Source-of-truth split

Daybook is a polyglot system. Type definitions can't be auto-shared across
TypeScript, Python, and Swift, so each language layer mirrors what's here.
Three sources of truth, three things to keep in sync:

| File / location                                  | Layer            | Role                                |
| ------------------------------------------------ | ---------------- | ----------------------------------- |
| `packages/shared/src/types.ts`                   | TypeScript       | **Conceptual source of truth**      |
| `apps/inference/migrations/0001_initial.sql`     | Postgres         | **Database source of truth**        |
| `apps/inference/daybook/models/*.py` (Pydantic)  | Python           | Mirror for the inference pipeline   |
| `apps/ios/Lullaby/Shared/Models/*.swift`         | Swift            | Mirror for iOS / watchOS            |
| `apps/web/src/db/schema.ts` (Drizzle ORM)        | TypeScript-on-DB | Web-side typed reflection of SQL    |

**Discipline:** when you change a type here, you change all four. There is no
codegen yet. If drift becomes painful, we'll add codegen later (`ts-to-zod`,
`pydantic-to-typescript`, etc.). For v0, manual sync is the right tradeoff.

## File layout

```
src/
├── ids.ts          Branded ID types (UserID, SleepSessionID, ...) + helpers
├── types.ts        All entity types
└── index.ts        Re-exports
```

## Conventions used in `types.ts`

- **Branded ID types** for entity boundaries — compile-time safety, zero runtime cost.
- **ISO 8601 date-time strings** for all timestamps. Date objects live inside
  language-specific layers; the contract uses strings.
- **`iModelId: IModelID | null`** on every event-like entity. v1 leaves it null;
  v2+ ML clustering populates it. Schema-from-day-1 per the I-Model architectural
  commitment.
- **Discriminated unions** with a `kind` field for polymorphic content
  (`SensorReading`, `CueEvent.contentType`, `WispUtterance.kind`). Maps to a
  `kind TEXT` column + `payload JSONB` in Postgres.

## Adding a new entity

1. Add the interface in `src/types.ts`. Use existing entities as the style guide.
2. Add the matching ID type + `asXxxID` helper in `src/ids.ts` if it has its own ID.
3. Add the corresponding table to `apps/inference/migrations/000X_xxx.sql`.
4. Add (or update) the Pydantic model in `apps/inference/daybook/models/`.
5. Add the Swift `Codable` struct in `apps/ios/Lullaby/Shared/Models/`.
6. Add the Drizzle schema in `apps/web/src/db/schema.ts`.

Yes, it's a lot. Yes, it's annoying. Yes, drift hurts. The tradeoff: native
language ergonomics in each layer vs. a single codegen toolchain we'd have to
maintain. For v0, manual is cheaper.

## Status

- v0.0.1 — initial data model. Covers: User, SleepSession, SleepStageClassification,
  SensorReading (9 variants), DreamRecall, WispUtterance, CueEvent, Embedding,
  IModelCluster, Intent, MoodReport. Defined 2026-05-17.
