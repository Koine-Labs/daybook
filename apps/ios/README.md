# apps/ios

iOS + watchOS app for Daybook. Migrated from the Lullaby prototype as the technical foundation; the UI layer is being rebuilt from scratch.

## What was migrated from Lullaby

Selective copy of `Repo/Lullaby/Lullaby/` — the inner Xcode-project root. The technical foundation was kept intact:

- `Lullaby.xcodeproj/` — Xcode project bundle (targets, build settings, schemes)
- `Lullaby/` — iOS app target
  - `Audio/` — audio capture and classification
  - `Auth/` — authentication
  - `Connectivity/` — phone-side WatchConnectivity plumbing
  - `Health/` — HealthKit integration
  - `Networking/` — API client
  - `Storage/` — local persistence
  - `Services/`, `Upload/` — supporting infrastructure
  - `Assets.xcassets`, `Info.plist`, `Lullaby.entitlements` — bundle config
  - `LullabyApp.swift`, `PhoneSessionCoordinator.swift` — app entry + session coordination
- `Lullaby Watch App/` — watchOS app target
  - `Sensors/` — accelerometer, heart rate, motion capture
  - `Connectivity/` — watch-side WatchConnectivity
  - `Storage/` — on-watch buffering
  - `Assets.xcassets`, `Lullaby Watch App.entitlements` — bundle config
  - `LullabyWatchApp.swift`, `WatchSessionCoordinator.swift` — app entry + session coordination
- `Shared/` — cross-target code (`Models/`, `Utilities/`)
- `LullabyTests/` — unit tests covering audio, connectivity, serialization, sensors, timestamps, sleep staging
- `.gitignore` — Xcode-tuned ignores

## What was scrapped

The entire Lullaby UI layer is being rebuilt for Daybook. Removed:

- `Lullaby/Views/`, `Lullaby/Components/`, `Lullaby/Theme/`
- `Lullaby Watch App/Views/`, `Lullaby Watch App/Components/`, `Lullaby Watch App/Theme/`
- `DashboardView.swift`, `AccountView.swift` (deprecated screens)
- Xcode `build/` artifacts, the source repo's `.git/`, agent state (`.claude/`), `.DS_Store` files
- Source-tree `docs/` (Lullaby engine docs — superseded by the monorepo root `docs/`)

Empty `Views/`, `Components/`, `Theme/` folders are left in both targets as placeholders for the new Daybook UI.

## Naming

All filenames, the Xcode project, scheme names, target names, and Bundle IDs are still `Lullaby`-named so the project keeps building post-migration. The Lullaby → Daybook rename in Xcode is delicate (project file references, code-signing, entitlements, asset catalog names) and is being handled as a dedicated follow-up task.

## Building

Open `Lullaby.xcodeproj` in Xcode. The project should build as-is — no source files were modified in the migration, only relocated.
