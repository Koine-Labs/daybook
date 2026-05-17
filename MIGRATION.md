# Daybook Migration Log

**Date:** 2026-05-16 / 2026-05-17

**Approach:** **Approach A** — selective copy from the legacy Lullaby project into the new `Repo/daybook/` monorepo. The Lullaby source is preserved as an archived GitHub repository (not deleted, just retired).

**Lullaby archival location (2026-05-17):**
- Original GitHub: `Aakash-a18/Lullaby` (private personal account)
- Transferred to: **`github.com/Koine-Labs/lullaby`** (under the org, marked **Archived**)
- Local `Repo/Lullaby/` directory: **deleted** (~549 MB freed). Clone from the archived repo if you need a local reference.

---

## What was KEPT and migrated

### iOS / watchOS (`apps/ios/`)
Source: `Repo/Lullaby/Lullaby/`

- The full `Lullaby.xcodeproj/` Xcode project bundle
- iOS target `Lullaby/`:
  - `Audio/` — SonarEngine, PassiveAudioAnalyzer
  - `Auth/` — AuthManager, KeychainHelper, AppleSignInHelper, GoogleSignInHelper
  - `Connectivity/` — PhoneConnectivityManager
  - `Health/` — MorningSyncManager (HealthKit sync)
  - `Networking/` — APIClient, SessionUploader, UploadQueue
  - `Storage/` — SleepSessionStore, JSONExporter
  - `PhoneSessionCoordinator.swift`
  - `LullabyApp.swift`
- watchOS target `Lullaby Watch App/`:
  - `Sensors/` — WorkoutSession, HR, HRV, Accelerometer collectors
  - `Connectivity/` — WatchConnectivityManager, WatchDataBuffer
  - `WatchSessionCoordinator.swift`
  - `LullabyWatchApp.swift`
- `Shared/` (cross-target: `Models/`, `Utilities/`)
- `LullabyTests/` (all test files)
- Source-root `.gitignore`

### Python pipeline (`apps/inference/`)
Sources: `Repo/Lullaby/inference/` (FastAPI server) + `Repo/Lullaby/analysis/` (offline ML)

- FastAPI inference server at the package root (`main.py`, `classifier.py`, `feature_engine.py`, `session_tracker.py`, `auth.py`, `schemas.py`, `config.py`, `Dockerfile`, `railway.toml`, server `tests/`)
- Offline analysis suite under `analysis/` — the `lullaby/` Python package, `notebooks/`, `data/`, and the 233-test suite in `analysis/tests/`
- New `pyproject.toml` written as a placeholder workspace config (`daybook-inference` 0.0.1)

### TypeScript data server (`apps/server/`)
Source: `Repo/Lullaby/server/`

- Cloudflare Workers + Hono codebase: `src/` (routes, middleware, services, utils), `migrations/` (D1 SQL schema), `wrangler.toml`, `tsconfig.json`, `package.json`, `package-lock.json`
- `package.json` `name` field renamed `lullaby-server` → `@daybook/server` (no other changes)

### Documentation (`docs/`, root, app-local)
- `CLAUDE.md` copied to repo root verbatim — to be rewritten in a later task to reflect the new structure
- `POSITIONING.md` copied to `docs/POSITIONING.md`
- `Project_Lullaby_PRD_v1.1.docx` copied to `docs/historical/` as the legacy PRD
- `Lullaby/Lullaby/docs/ENGINE_API.md` copied to `apps/ios/docs/ENGINE_API.md` (iOS-specific — kept under the iOS app rather than at the top-level `docs/`, which is reserved for cross-cutting documents)
- This `MIGRATION.md` documents the migration itself

---

## What was SCRAPPED (intentionally not migrated)

All scrapped paths remain in `Repo/Lullaby/` for historical reference.

- **iOS UI layer:** all `Views/` (Tabs, Sleep, History, Insights, Profile) in the iOS target
- **watchOS UI layer:** all `Views/` (WatchSessionView, etc.) in the watchOS target
- **iOS components:** all `Components/` (GlassCard, SessionOrb, Starfield, CircularProgressRing, MetricTile, Charts/SimpleLineChart, SimpleBarChart, HypnogramView, etc.)
- **watchOS components:** all `Components/` (HeartRateRing, WatchGlassButton)
- **Theme layer:** `LullabyTheme`, `WatchTheme`, `GlowModifier`
- **Top-level JSX mockups:** `components.jsx`, `screens (1).jsx`, `ios-frame.jsx`, `tweaks-panel (1).jsx`
- **HTML/JS mockups:** `Lullaby.html`, `data.js`
- **Already-deprecated views:** `DashboardView.swift`, `AccountView.swift` (deprecated inside Lullaby before migration)
- **Build/cache artifacts:** `build/`, `.DS_Store`, `.coverage`, `.pytest_cache/`, `.wrangler/`, `node_modules/`, `__pycache__/`, `*.pyc`, `*.tsbuildinfo`

---

## Notes

- **Coordinators kept and to be reframed.** `PhoneSessionCoordinator` and `WatchSessionCoordinator` were migrated as-is and will be *reframed* (re-targeted at Daybook's flows) rather than rewritten from scratch.
- **Lullaby names still in place.** All Xcode filenames, schemes, Bundle IDs (`Neovasky.Lullaby`, `Neovasky.Lullaby.watchkitapp`), and Python package names (`lullaby/`) are unchanged so the Xcode project still builds after migration. The Lullaby → Daybook rename is a separate dedicated task.
- **UI placeholders.** Empty `Views/`, `Components/`, and `Theme/` folders were created inside both `apps/ios/Lullaby/` and `apps/ios/Lullaby Watch App/` as scaffolding for the new Daybook UI.
- **Server rename.** Only the workspace `name` in `apps/server/package.json` was renamed. The Cloudflare project name (`lullaby-server.aakashjuly18.workers.dev`), the D1 database name (`lullaby-db`), and the deployed worker name in `wrangler.toml` are unchanged — those will be migrated when Daybook's hosting is provisioned.
- **Lullaby tree untouched.** `Repo/Lullaby/` is the canonical historical reference and must not be modified.
