# apps/ios

Native iOS + watchOS source for Daybook. Two projects coexist here:

1. **`Daybook.xcodeproj` (NEW — scaffolded 2026-05-17)** — the active Daybook iOS/watchOS app being built from scratch against the Claude Design tokens. This is where new UI work lands.
2. **`Lullaby.xcodeproj` (legacy infrastructure)** — the inherited Lullaby project carries audio capture, HealthKit, WatchConnectivity, sensor collectors, networking, and storage code that will be folded into Daybook in follow-up passes. It builds independently. See "What was migrated from Lullaby" below.

---

## Daybook project (the new app)

### Layout

```
Daybook/
├── project.yml                           # xcodegen spec — regenerates Daybook.xcodeproj
├── Daybook.xcodeproj/                    # generated; committed
├── Daybook/
│   ├── DaybookApp.swift                  # @main
│   ├── ContentView.swift                 # Root — TabBar + active screen
│   ├── DesignSystem/
│   │   ├── Tokens.swift                  # Color hex tokens (translation of styles.css :root)
│   │   ├── Theme.swift                   # @Observable Theme — companion / witness palettes
│   │   ├── Typography.swift              # DBFont + .dbHeadline / .dbEyebrow / .dbMeta / .regisVoice
│   │   └── Fonts/                        # (empty for now — system fallbacks in use)
│   ├── Components/
│   │   ├── WispView.swift                # Animated Regis glyph — 5 states
│   │   ├── WispMark.swift                # Static glyph for inline use
│   │   ├── RegisQuote.swift              # Italic serif primitive for Regis's voice
│   │   ├── TabBar.swift                  # Bottom tab bar with .ultraThinMaterial blur
│   │   ├── ScreenHead.swift              # Calm header (date + corner wisp)
│   │   ├── MicButton.swift               # Round record button (port of shell.jsx)
│   │   └── VuBars.swift                  # Animated VU meter
│   ├── Screens/
│   │   └── TodayView.swift               # The Today screen (port of ScreenToday)
│   ├── Networking/
│   │   ├── APIClient.swift               # URLSession client → http://localhost:8000
│   │   └── Models.swift                  # Codable shapes for the FastAPI bridge
│   ├── State/
│   │   └── AppState.swift                # Root @Observable state
│   └── Assets.xcassets/
│       ├── AppIcon.appiconset/Koine-Wisp.png   # 1024×1024 master from /Logo/
│       └── AccentColor.colorset/               # Amber (#C97C3A)
├── DaybookWatch Watch App/               # watchOS — scaffolded only
│   ├── DaybookWatchApp.swift
│   ├── ContentView.swift                 # "hello watch" placeholder
│   └── Assets.xcassets/
└── screenshots/
    └── today-iphone17pro.png             # rendered TodayView on iPhone 17 Pro sim
```

### Building

The project is defined by [xcodegen](https://github.com/yonaskolb/XcodeGen). Regenerate the Xcode project from source any time `project.yml` or the file tree changes:

```bash
cd apps/ios
xcodegen generate
```

Then open `Daybook.xcodeproj` in Xcode, or build from the command line:

```bash
# iOS
xcodebuild -project Daybook.xcodeproj \
  -scheme Daybook \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
  build

# watchOS
xcodebuild -project Daybook.xcodeproj \
  -scheme "DaybookWatch Watch App" \
  -destination 'platform=watchOS Simulator,name=Apple Watch Ultra 3 (49mm)' \
  build
```

Both currently build clean. (Both `.xcodeproj` bundles live in the same directory, so you must pass `-project Daybook.xcodeproj` explicitly to disambiguate from the legacy `Lullaby.xcodeproj`.)

Tested on Xcode 26.3, iOS 17.0 deployment target, watchOS 10.0 deployment target.

### What is implemented

- All design tokens from `styles.css` (companion + witness palettes, both color sets).
- `Theme` flows through `Environment(Theme.self)` and switches palettes by `ThemeMode`.
- The full `WispView` with all 5 states (dormant / listening / composing / witnessing / held), with state-specific breathing animations, ripples (listening), and eye-blink (composing).
- Static `WispMark` for inline use.
- `TabBar` matching the shell.jsx design — 5 tabs, wisp icon on `regis`, ultra-thin material blur, top border, companion mode colors.
- `ScreenHead` with date eyebrow + corner wisp.
- `MicButton` with active/inactive states and pulse glow.
- `VuBars` with per-bar staggered animation.
- `TodayView` — full port of `ScreenToday` from `screens-companion.jsx`. Hardcoded placeholder data throughout. Sections: greeting, intent card (editable), held-from-last-night (3 dream fragments), the-shape-of-today (5-row schedule), recall-trend (sparkline + delta), closing Regis whisper.
- `APIClient` + Codable `Models` (ChatMessage, DreamRecall, SleepSession, RegisMoment, Intent) — defined but not wired to any view yet. Ready for the FastAPI bridge.
- watchOS app — bare-minimum stub that compiles. The witness face / dream cue surface is a follow-up pass.

### What is NOT implemented (intentionally — for this pass)

- Other companion screens: chat (regis), inner, archive, lab. The TabBar navigates to them and renders a "coming soon" placeholder.
- Witness / Threshold / Recall / Night immersive screens.
- watchOS UI body — only the scaffold target exists.
- Real network calls — TodayView shows placeholder strings. APIClient is ready; the bridge at `apps/api/` is being built in parallel.
- Companion-mode paper noise overlay (the dotted texture in styles.css `.paper-noise`).
- Witness-mode starfield.
- Wisp transition animation between states (currently jump-resets).
- Real watchOS health/sensor wiring (those collectors live in legacy Lullaby and will be carried over).

### Font situation — placeholders

Instrument Serif, Instrument Sans, and JetBrains Mono are all Open Font License but I did NOT download them in this pass. The current Swift typography uses system fallbacks:

| Design intent     | What's rendered now                                           |
| ----------------- | ------------------------------------------------------------- |
| Instrument Serif  | `UIFont.systemFont(...).withDesign(.serif)` (Charter on iOS)  |
| Instrument Sans   | System sans (SF Pro)                                          |
| JetBrains Mono    | System monospaced (SF Mono)                                   |

The screenshot at `screenshots/today-iphone17pro.png` shows the result — visually close, but the real Instrument Serif has narrower stems and a more distinctive italic. To swap in the real fonts:

1. Download `.ttf` files from Google Fonts (Instrument Serif, Instrument Sans, JetBrains Mono).
2. Drop them into `Daybook/DesignSystem/Fonts/`.
3. Add `UIAppFonts` entries to `project.yml` under the iOS target's `info.properties` (currently `UIAppFonts: []`).
4. Update `Typography.swift` to construct `Font.custom("InstrumentSerif-Regular", size: ...)` etc.
5. Run `xcodegen generate` + rebuild.

### Screenshot

`screenshots/today-iphone17pro.png` shows TodayView rendered on iPhone 17 Pro simulator (iOS 17 target, Xcode 26.3). The cream paper background, serif "Afternoon." headline, three card stack, and tab bar match the reference design (`/tmp/daybook-design-fetch/daybook/project/screenshots/01-overview.png`) closely. The Wisp glyph appears as the small amber dot in the upper right.

---

## Lullaby legacy project — what was migrated

(Original README content. Preserved verbatim for reference. The Lullaby project still compiles and is the home for the inherited iOS / watchOS infrastructure that will be progressively folded into Daybook.)

iOS + watchOS app for Daybook. Migrated from the Lullaby prototype as the technical foundation; the UI layer is being rebuilt from scratch.

### What was migrated from Lullaby

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

### What was scrapped

The entire Lullaby UI layer is being rebuilt for Daybook. Removed:

- `Lullaby/Views/`, `Lullaby/Components/`, `Lullaby/Theme/`
- `Lullaby Watch App/Views/`, `Lullaby Watch App/Components/`, `Lullaby Watch App/Theme/`
- `DashboardView.swift`, `AccountView.swift` (deprecated screens)
- Xcode `build/` artifacts, the source repo's `.git/`, agent state (`.claude/`), `.DS_Store` files
- Source-tree `docs/` (Lullaby engine docs — superseded by the monorepo root `docs/`)

Empty `Views/`, `Components/`, `Theme/` folders are left in both targets as placeholders for the new Daybook UI.

### Naming

All filenames inside the Lullaby project, its scheme names, target names, and Bundle IDs are still `Lullaby`-named so the project keeps building post-migration. The Lullaby → Daybook rename in Xcode is delicate (project file references, code-signing, entitlements, asset catalog names) and is being handled progressively as new Daybook code is written. The new `Daybook.xcodeproj` is the first piece of that.

### Building Lullaby

Open `Lullaby.xcodeproj` in Xcode. The project should build as-is — no source files were modified in the migration, only relocated.
