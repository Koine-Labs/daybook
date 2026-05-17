# Lullaby Engine API — UI Handoff Spec

> **Purpose.** This document describes everything the new UI needs to bind to. The old `Views/`, `Components/`, and `Theme/` directories have been deleted on both iOS and watchOS targets. The engine layer below is **stable** and unchanged.
>
> Any new UI implementation must:
> 1. Bind to the `@Observable` managers listed below via SwiftUI's `.environment(_:)` injection (already wired in `LullabyApp.swift`).
> 2. Render the data models defined in `Shared/Models/`.
> 3. Cover the user journeys in §6.
> 4. Compile against the iOS 18+ / watchOS 10+ / Swift 6.2 strict concurrency settings already in the project.

Everything below is **observed state and methods exposed to the UI** — no internal implementation details.

---

## 1. App entry & dependency injection (iOS)

`Lullaby/LullabyApp.swift` constructs four observable managers and injects them into the SwiftUI environment. The new root view must accept them via `@Environment(...)`.

```swift
@main
struct LullabyApp: App {
    @State private var authManager = AuthManager()
    @State private var coordinator: PhoneSessionCoordinator      // session orchestrator
    @State private var progressionManager: ProgressionManager     // XP / ranks / streaks
    @State private var dreamStoreManager = DreamStoreManager()    // dream journal

    var body: some Scene {
        WindowGroup {
            // Auth gate — show sign-in UI when !isAuthenticated, app shell otherwise
            RootView()
                .environment(authManager)
                .environment(coordinator)
                .environment(progressionManager)
                .environment(dreamStoreManager)
                .onOpenURL { url in GIDSignIn.sharedInstance.handle(url) }
        }
    }
}
```

All four managers are `@Observable` and intended to be read with `@Environment(<Type>.self) private var foo`.

---

## 2. Engine managers (iOS)

### 2.1 `AuthManager` — sign-in state

`Lullaby/Auth/AuthManager.swift` · `@Observable @MainActor`

| Published property | Type | Meaning |
|---|---|---|
| `isAuthenticated` | `Bool` | Gate the app shell on this |
| `currentUser` | `UserProfile?` | Display name / email / role |
| `isLoading` | `Bool` | Show spinner during auth calls |
| `error` | `String?` | Render under sign-in form |
| `apiClient` | `APIClient` | Pass to upload code if needed |

**Methods (all `async`):**
- `register(email:password:displayName:)` — new account
- `login(email:password:)` — email/password sign-in
- `signInWithApple()` — Sign in with Apple flow
- `signInWithGoogle()` — Google Sign-In flow
- `logout()` — clear tokens and reset state

```swift
struct UserProfile: Codable, Sendable {
    let id: String
    let email: String
    let displayName: String?
    let role: String
}
```

### 2.2 `PhoneSessionCoordinator` — the night

`Lullaby/PhoneSessionCoordinator.swift` · `@Observable`

This is the **primary** engine for the sleep tracking experience. The UI starts/stops sessions and observes live sensor state from here.

| Published property | Type | Meaning |
|---|---|---|
| `isSessionActive` | `Bool` | Is a session currently recording? |
| `isWatchConnected` | `Bool` | Is the Watch reachable right now? |
| `isSonarRunning` | `Bool` | Is the 19kHz sonar engine emitting? |
| `packetsReceived` | `UInt32` | Total sensor packets received from Watch this session |
| `lastHeartRate` | `Double` | Most recent BPM (live display) |
| `lastBreathingRate` | `Float` | Most recent breaths/min from sonar |
| `sleepStagesSynced` | `Bool` | Has HealthKit ground truth been pulled? |
| `sessionDuration` | `TimeInterval` | Live elapsed seconds since start |
| `isUploading` | `Bool` | Cloud upload in progress |
| `uploadError` | `String?` | Last upload error message |
| `currentPrediction` | `StagePrediction?` | Live ML prediction from inference server (may be nil — server is Phase 3) |
| `hasCompletedSession` | `Bool` (computed) | True if there's a finished session to view |
| `formattedDuration` | `String` (computed) | `"7h 23m 14s"` style |

**Methods:**
- `startSession() async throws` — kicks off sonar + audio + websocket + duration timer
- `stopSession() async` — clean shutdown, drains buffers, updates streak
- `syncSleepStages(for:)` — pulls Apple HealthKit sleep stages; pass `nil` for current session
- `exportSession(_:)` — returns a `URL` to the JSON file
- `uploadSession(apiClient:session:)` — upload one session to the server
- `sessionSummary() async -> String?` — debug string for the active session
- `allSessionSummaries() async -> [SessionSummary]` — lightweight list for History UI
- `loadSession(from:) async -> SleepSession?` — full load for detail view
- `pastSessionURLs() async -> [URL]` — file URLs for past sessions

```swift
struct StagePrediction: Codable, Sendable {
    let epochIndex: Int
    let stage: String                     // "awake" | "rem" | "core" | "deep"
    let confidence: Double                // 0–1
    let probabilities: [String: Double]
}
```

### 2.3 `ProgressionManager` — XP, ranks, streaks, sleep grade

`Lullaby/Services/ProgressionManager.swift` · `@Observable @MainActor`

| Published property | Type | Meaning |
|---|---|---|
| `profile` | `DreamerProfile` | All XP / rank / streak state — see §3.4 |

**Methods:**
- `awardSleepXP(grade:duration:bedtimeDeviation:)` — call after a session
- `awardDreamXP(for: DreamEntry)` — call when a dream is logged
- `updateStreak(sessionDate:)` — called automatically by coordinator on session end
- `computeGrade(duration:targetDuration:awakeTime:totalSleepTime:deepSleepPct:remSleepPct:bedtimeDeviation:) -> SleepGrade`
- `saveGrade(_:forSessionId:)` / `loadGrade(forSessionId:) -> SleepGrade?` — per-session sidecar
- `setTargetSleepDuration(_:)` — preference setter

### 2.4 `DreamStoreManager` — dream journal

`Lullaby/Storage/DreamStore.swift` · `@Observable @MainActor`

| Published property | Type | Meaning |
|---|---|---|
| `entries` | `[DreamEntry]` | All dreams, sorted newest first |
| `isLoaded` | `Bool` | False until `load()` has been called once |

**Methods:**
- `load() async` — call once on app launch / first appearance
- `save(_:) async throws` — create or update an entry
- `delete(_:) async throws` — by UUID
- `entry(forSessionId:) async -> DreamEntry?` — link a dream to a session
- `sessionIdsWithDreams() async -> Set<UUID>` — for "has dream" badges in History

---

## 3. Data models (Shared/Models/)

All models are `Codable`, `Sendable`, and marked `nonisolated` so they cross actor boundaries freely.

### 3.1 `SleepSession`

```swift
struct SleepSession: Codable, Sendable {
    let id: UUID
    let startDate: Date
    var endDate: Date?
    var watchPackets: [SensorPacket]
    var sonarFeatures: [SonarFeatureSample]
    var audioFeatures: [AudioFeatureSample]
    var sleepStages: [SleepStageLabel]
    var respiratoryRateSamples: [TimestampedSample]
    var spo2Samples: [TimestampedSample]
    var wristTemperatureSamples: [TimestampedSample]
    var metadata: SessionMetadata
}

struct SessionMetadata: Codable, Sendable, Equatable {
    let appVersion: String
    var watchModel: String?
    let iphoneModel: String
    var osVersionWatch: String?
    let osVersioniOS: String
    var watchBatteryAtStart: Float?
    var watchBatteryAtEnd: Float?
    var phoneBatteryAtStart: Float?
    var phoneBatteryAtEnd: Float?
    var totalPacketsReceived: UInt32
    var totalPacketsExpected: UInt32?
    var connectivityDropCount: UInt32
}
```

### 3.2 `SessionSummary` — lightweight History list row

```swift
struct SessionSummary: Identifiable, Sendable, Hashable {
    let id: UUID
    let startDate: Date
    let endDate: Date?
    let duration: TimeInterval
    let watchPacketCount: Int
    let sleepStageCount: Int
    let hasSleepStages: Bool
    let fileURL: URL
    let fileSizeBytes: Int
}
```

### 3.3 `SleepStage` + `SleepStageLabel` — Apple HealthKit ground truth

```swift
enum SleepStage: String, Codable, Sendable {
    case awake, remSleep, coreLight, deepSleep, inBed, unknown
}

struct SleepStageLabel: Codable, Sendable, Equatable {
    let startTimestamp: TimeInterval   // seconds since session start
    let endTimestamp: TimeInterval
    let stage: SleepStage
}
```

### 3.4 `DreamerProfile` — XP / rank state

```swift
struct DreamerProfile: Codable, Sendable {
    var sleepXP: Int
    var dreamXP: Int
    var sleepRank: Int                 // 1–6
    var dreamRank: Int                 // 1–6
    var currentStreak: Int
    var longestStreak: Int
    var lastTrackedDate: Date?
    var streakStartDate: Date?
    var totalNightsTracked: Int
    var totalDreamsLogged: Int
    var totalLucidNights: Int
    var targetSleepDuration: TimeInterval     // seconds, default 8h
    var targetBedtime: DateComponents?

    // Computed
    var sleepTitle: String              // "Novice Snoozer" … "Master of Rest"
    var dreamTitle: String              // "Dreamer Initiate" … "Dream Sovereign"
    var fusionTitle: String             // "Master Dreamer", "Oneironaut", …
    var environmentRankLevel: Int       // max(sleepRank, dreamRank) — drives bg theme

    // Static helpers for progress bars
    static let rankThresholds = [0, 100, 300, 700, 1500, 3000]
    static func rankFor(xp: Int) -> Int
    static func xpForNextRank(currentRank: Int) -> Int?
    static func xpProgressInCurrentRank(xp: Int, rank: Int) -> Double  // 0–1
}
```

### 3.5 `SleepGrade` — per-session grade

```swift
struct SleepGrade: Codable, Sendable {
    let letter: String                  // "A+" … "D-"
    let qualitativeLabel: String        // "Deep Recovery", "REM Rich", "Restless", …
    let score: Double                   // 0–100
    let isPartial: Bool                 // true if no HealthKit stage data
    let components: GradeComponents
    var gradeXPBonus: Int               // 0–20

    struct GradeComponents: Codable, Sendable {
        let durationScore: Double       // 0–100
        let stageQualityScore: Double?  // nil = HealthKit missing
        let awakeTimeScore: Double
        let consistencyScore: Double
    }
}
```

### 3.6 `DreamEntry` — single dream

```swift
struct DreamEntry: Codable, Identifiable, Hashable, Sendable {
    let id: UUID
    let date: Date
    var sessionId: UUID?                // optional link to SleepSession
    var isLucid: Bool
    var vividness: Int                  // 1–5
    var emotions: [EmotionTag]
    var summary: String?
    var narrative: String?              // full text
    var themes: [String]
    var realityCheckNotes: String?
    var cueAwareness: Bool?
    var xpAwarded: Bool
    let createdAt: Date
    var updatedAt: Date

    var isRichEntry: Bool               // narrative.count >= 500
    var hasNarrative: Bool              // narrative.count >= 100
}

enum EmotionTag: String, Codable, CaseIterable, Sendable {
    case peaceful, exciting, frightening, surreal, nostalgic, confusing, joyful, bizarre
    var displayName: String
    var sfSymbol: String                // e.g. "leaf.fill", "bolt.fill"
}
```

### 3.7 `SensorPacket` and sub-samples (full reference)

```swift
struct SensorPacket: Codable, Sendable, Equatable {
    let sessionID: UUID
    let batchIndex: UInt32
    let capturedAt: Date
    var heartRateSamples: [HeartRateSample]
    var hrvSamples: [HRVSample]
    var accelerometerSamples: [AccelerometerSample]
    var gyroscopeSamples: [GyroscopeSample]
}

struct HeartRateSample: { let timestamp: TimeInterval; let bpm: Double }
struct HRVSample:       { let timestamp: TimeInterval; let sdnn: Double }
struct AccelerometerSample: { let timestamp: TimeInterval; let x, y, z: Float }
struct GyroscopeSample:     { let timestamp: TimeInterval; let x, y, z: Float }

struct SonarFeatureSample: Codable, Sendable {
    let timestamp: TimeInterval
    let breathingRate: Float?           // breaths/min
    let breathingRegularity: Float?     // 0–1
    let signalStrength: Float           // dB
    // optional autocorrelation diagnostics: secondPeakLag, secondPeakValue, correlationDecay
}

struct AudioFeatureSample: Codable, Sendable {
    let timestamp: TimeInterval
    let dominantFrequency: Float
    let spectralCentroid: Float
    let rmsEnergy: Float                // dB
    let zeroCrossingRate: Float         // 0–1
    let classification: AudioEventClass
    // plus spectralBandwidth, spectralFlatness, spectralRolloff, spectralFlux, subbandEnergy
}

enum AudioEventClass: String, Codable, Sendable {
    case silence, breathing, snoring, movement, ambientNoise
}
```

---

## 4. Watch entry & coordinator

`Lullaby Watch App/LullabyWatchApp.swift` is much simpler — a single coordinator, no auth, no progression on the watch.

```swift
@main
struct LullabyWatchApp: App {
    @State private var coordinator = WatchSessionCoordinator()

    var body: some Scene {
        WindowGroup { RootWatchView(coordinator: coordinator) }
    }
}
```

### `WatchSessionCoordinator`

`Lullaby Watch App/WatchSessionCoordinator.swift` · `@Observable`

| Published property | Type | Meaning |
|---|---|---|
| `isSessionActive` | `Bool` | Recording in progress |
| `lastHeartRate` | `Double` | Live BPM display |
| `packetsSent` | `UInt32` | Batches sent to phone this session |
| `isPhoneReachable` | `Bool` | iPhone reachability |
| `bufferedPacketCount` | `Int` | Pending packets (offline buffer depth) |

**Methods:**
- `startSession() async throws` — starts `HKWorkoutSession`, all collectors, batch timer
- `stopSession() async throws` — graceful shutdown, final batch flush

That's the entire watch UI surface. The watch screen should be **single-purpose**: a big start/stop control with a few live readouts (HR, connectivity, packet count, elapsed time).

---

## 5. Theme — fully open

The old `LullabyTheme.swift` (the "Dreamworld" palette: twilight + gold + lavender + teal, SF Rounded headlines, SF Mono data readouts, animated `EnvironmentView` background tied to rank) has been **deleted**. The new design owns all visual decisions:

- Color palette (light + dark, or dark only)
- Typography
- Iconography conventions
- Card / surface treatment
- Animation language
- Layout tokens (corner radii, spacing scale, etc.)

The only inherited requirement is **iOS dark-mode parity** since people use it in bed.

---

## 6. Required user journeys

The new UI must cover these flows. Each flow lists the engine APIs it touches — but the screen count, layout, tab structure, navigation pattern, and even the metaphors (gamification or not, sleep-grade letter or not) are open.

### 6.1 Auth gate
- Show until `authManager.isAuthenticated == true`
- Support email/password sign-in + register, plus Apple, plus Google
- Bind to `authManager.error`, `authManager.isLoading`
- After sign-in, transition to the main app shell

### 6.2 Tonight — start a session
- Big "Start" affordance → `coordinator.startSession()`
- While active, show: live HR (`lastHeartRate`), breathing rate (`lastBreathingRate`), elapsed time (`formattedDuration`), Watch connection (`isWatchConnected`), packets received (`packetsReceived`)
- A "Stop" affordance → `coordinator.stopSession()`
- Optional live prediction display (`currentPrediction` — may be nil)

### 6.3 Morning sync + last night recap
- Surface `coordinator.syncSleepStages()` (manual button OK; could be automatic on first foreground after wake)
- Show last session: duration, HR average, breathing average, hypnogram (from `sleepStages`), and the `SleepGrade` if computed
- Allow uploading via `coordinator.uploadSession(apiClient:)`

### 6.4 History
- List of `SessionSummary` rows (`coordinator.allSessionSummaries()`)
- Tapping a row → detail view loading full `SleepSession` via `coordinator.loadSession(from:)`
- Detail view should at minimum render: timeline (hypnogram), HR series, breathing series, audio classification distribution, metadata (battery, packet counts, drops)

### 6.5 Dream journal
- List `dreamStoreManager.entries`
- Compose entry → `dreamStoreManager.save(DreamEntry(...))`
- Edit + delete entries
- Allow linking a dream to a `SleepSession` via `sessionId`
- Lucid badge, vividness 1–5, emotion picker (8 tags, each has an SF Symbol), narrative text

### 6.6 Progression
- Show `progressionManager.profile`: sleep XP + rank, dream XP + rank, fusion title
- XP-to-next-rank progress bars via `DreamerProfile.xpProgressInCurrentRank(xp:rank:)`
- Streak display (`currentStreak`, `longestStreak`)
- Milestones / totals (`totalNightsTracked`, `totalDreamsLogged`, `totalLucidNights`)

> **Design note.** Gamification is currently load-bearing in the engine (XP, ranks, grades, streaks all persist). You can hide or de-emphasize it in the new UI, but the data is there if you want it.

### 6.7 Profile / settings
- Show `authManager.currentUser`
- Sign out → `authManager.logout()`
- Target sleep duration → `progressionManager.setTargetSleepDuration(_:)`
- (Future) target bedtime, notification settings, server config

### 6.8 Active session presentation (optional)
- The old UI offered two "modes" for the active session screen: a minimal **Clock** view and a more atmospheric **Dreamscape** view. Whether to keep this split is a design call.

---

## 7. What stays / what's gone

### Stays (do not modify)
- `Lullaby/PhoneSessionCoordinator.swift`
- `Lullaby/Auth/*` (AuthManager, KeychainHelper, AppleSignInHelper, GoogleSignInHelper)
- `Lullaby/Networking/*` (APIClient, APIEndpoints, APIError, InferenceConfig, WebSocketManager)
- `Lullaby/Health/MorningSyncManager.swift`
- `Lullaby/Audio/*` (SonarEngine, PassiveAudioAnalyzer)
- `Lullaby/Connectivity/PhoneConnectivityManager.swift`
- `Lullaby/Storage/*` (SleepSessionStore, DreamStore, JSONExporter)
- `Lullaby/Services/ProgressionManager.swift`
- `Lullaby/Upload/*` (SessionUploader, UploadQueue)
- `Lullaby Watch App/WatchSessionCoordinator.swift`
- `Lullaby Watch App/Sensors/*` (HeartRateCollector, HRVCollector, AccelerometerCollector / MotionCollector, WorkoutSession)
- `Lullaby Watch App/Connectivity/*` (WatchConnectivityManager, WatchDataBuffer)
- `Lullaby Watch App/Storage/*`
- All of `Shared/Models/*` and `Shared/Utilities/*`
- `LullabyTests/` and `analysis/` (the Python pipeline)
- `server/` (Cloudflare Workers)

### Gone (deleted from the project)
- `Lullaby/Views/` — every screen
- `Lullaby/Components/` — every reusable UI piece (cards, charts, rings, gamification widgets, glass effects, starfield, etc.)
- `Lullaby/Theme/` — palette, typography, layout constants, gradient presets
- `Lullaby Watch App/Views/` — `WatchSessionView`
- `Lullaby Watch App/Components/` — `HeartRateRing`, `WatchGlassButton`
- `Lullaby Watch App/Theme/`

After the strip, the app entry points reference a minimal `RootView` / `RootWatchView` placeholder that just compiles; replace these with the new design system.

---

## 8. Build & target info

- Swift 6.2, strict MainActor isolation enabled
- iOS deployment target: **18.0+**
- watchOS deployment target: **10.0+**
- iOS bundle ID: `Neovasky.Lullaby`
- watchOS bundle ID: `Neovasky.Lullaby.watchkitapp`
- Xcode project: `Lullaby/Lullaby/Lullaby.xcodeproj`
- App Group (Watch ↔ iPhone shared state): `group.Neovasky.Lullaby`
- HealthKit, Microphone, Motion entitlements already configured

To rebuild from CLI:
```bash
xcodebuild -project Lullaby/Lullaby/Lullaby.xcodeproj -scheme Lullaby -sdk iphonesimulator build
xcodebuild -project Lullaby/Lullaby/Lullaby.xcodeproj -scheme "Lullaby Watch App" -sdk watchsimulator build
```

---

## 9. Open design questions worth deciding before building

1. **Keep gamification?** XP / ranks / streaks / grades are in the engine. Surface them, downplay them, or hide entirely?
2. **Tab vs. stack-based navigation?** Old UI was 4 tabs (Home / Dreams / Progress / Profile). Worth challenging.
3. **One active-session screen or two?** Old UI had Clock vs. Dreamscape modes.
4. **Watch face complication?** Not currently implemented; would be a fast path to the start button.
5. **Live REM cue UI?** The cue-delivery loop isn't built (Phase 3), but the inference prediction is already piped to `coordinator.currentPrediction`. Decide whether to surface "REM detected" indicators now or wait until cues are real.
6. **Light mode at all?** Or dark-only given the use case?
