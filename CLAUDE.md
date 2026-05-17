# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Project Lullaby is a lucid dream induction system for the Apple ecosystem. It uses Apple Watch + iPhone as a sensor fusion platform to detect REM sleep in near-real-time and deliver haptic cues through the watch to promote lucid dreaming. The system streams feature vectors to a cloud inference server for sleep stage classification and calibrates nightly against Apple's HealthKit sleep stage data.

**PRD:** `Project_Lullaby_PRD_v1.1.docx` at the project root contains the full product requirements document. Refer to it for detailed specifications on sensor data, model architecture, cue delivery protocol, and development phases.

## Repository Structure

```
Lullaby/                              # Project root (not a git repo)
├── Project_Lullaby_PRD_v1.1.docx     # Product Requirements Document
├── .claude/                          # Claude Code settings
├── analysis/                         # Python analysis suite (Phase 2)
│   ├── lullaby/                      # Python package
│   │   ├── loader.py                 # JSON session loading + mock generation
│   │   ├── features.py              # 30-second epoch alignment
│   │   ├── temporal_features.py     # Rolling stats, deltas, time-of-night
│   │   ├── pipeline.py              # Multi-session ML pipeline
│   │   ├── model.py                 # XGBoost training + CV
│   │   ├── evaluation.py            # Metrics, SHAP, success criteria
│   │   ├── export.py                # Model serialization (joblib + CoreML)
│   │   ├── remote.py                # Server API client + CLI for downloading sessions
│   │   ├── statistics.py            # REM vs non-REM comparisons
│   │   ├── quality.py               # Data quality assessment
│   │   └── visualization.py         # Plotting (hypnogram, heatmaps, etc.)
│   ├── tests/                        # 233 tests (pytest)
│   └── notebooks/                    # Jupyter notebooks
│       ├── explore_night.ipynb       # Single-night analysis
│       ├── compare_nights.ipynb      # Multi-night comparison
│       └── train_classifier.ipynb    # XGBoost training workflow
├── server/                           # Cloudflare Workers data collection server (Phase 2.5)
│   ├── src/                          # TypeScript source (Hono framework)
│   │   ├── routes/                   # auth, sessions, users endpoints
│   │   ├── middleware/               # JWT auth, CORS
│   │   ├── services/                 # Business logic
│   │   └── utils/                    # Crypto, JWT, OAuth helpers
│   ├── migrations/                   # D1 SQL schema
│   ├── wrangler.toml                 # Cloudflare bindings (D1 + R2)
│   └── package.json                  # hono, jose, wrangler
└── Lullaby/                          # Git repository root (Xcode project)
    ├── Lullaby.xcodeproj/            # Xcode project (3 targets)
    ├── Lullaby/                      # iOS app source (~25 Swift files)
    │   ├── LullabyApp.swift          # @main entry point → MainTabView (auth gate)
    │   ├── PhoneSessionCoordinator.swift  # Orchestrates sonar + audio + connectivity
    │   ├── Audio/                    # SonarEngine, PassiveAudioAnalyzer
    │   ├── Auth/                     # AuthManager, KeychainHelper, AppleSignInHelper, GoogleSignInHelper
    │   ├── Connectivity/             # PhoneConnectivityManager
    │   ├── Health/                   # MorningSyncManager (HealthKit sync)
    │   ├── Networking/               # APIClient, SessionUploader, UploadQueue
    │   ├── Storage/                  # SleepSessionStore, JSONExporter
    │   ├── Views/                    # 4-tab architecture
    │   │   ├── Tabs/                 # MainTabView (root)
    │   │   ├── Sleep/                # SleepTabView, PreSessionView, ActiveSessionView
    │   │   ├── History/              # HistoryTabView, SessionDetailView
    │   │   ├── Insights/             # InsightsTabView
    │   │   ├── Profile/              # ProfileTabView
    │   │   ├── DashboardView.swift   # (deprecated, replaced by tab views)
    │   │   └── AccountView.swift     # (deprecated, absorbed into ProfileTabView)
    │   ├── Components/               # GlassCard, SessionOrb, Starfield, CircularProgressRing, MetricTile, etc.
    │   │   └── Charts/              # SimpleLineChart, SimpleBarChart, HypnogramView
    │   └── Theme/                    # LullabyTheme, GlowModifier
    ├── Lullaby Watch App/            # watchOS app source (12 Swift files)
    │   ├── LullabyWatchApp.swift     # @main entry point → WatchSessionView
    │   ├── WatchSessionCoordinator.swift  # Orchestrates sensors + batching
    │   ├── Sensors/                  # WorkoutSession, HR, HRV, Accelerometer collectors
    │   ├── Connectivity/             # WatchConnectivityManager + WatchDataBuffer
    │   ├── Views/                    # WatchSessionView
    │   ├── Components/               # HeartRateRing, WatchGlassButton
    │   └── Theme/                    # WatchTheme
    ├── Shared/                       # Shared between iOS + watchOS
    │   ├── Models/                   # SleepSession, SensorPacket, SleepStage, ConnectivityMessage
    │   └── Utilities/                # SensorConstants, TimestampUtilities
    └── LullabyTests/                 # Swift unit tests (7 files)
```

Note the nested directory structure: the git repo is at `Lullaby/Lullaby/`, and source files are one level deeper in `Lullaby/Lullaby/Lullaby/`.

### Targets

The Xcode project has **three** targets:

1. **Lullaby (iOS)** — Main iPhone app. 4-tab architecture (Sleep, History, Insights, Profile) with auth gate. SonarEngine (19kHz), PassiveAudioAnalyzer, WatchConnectivity relay, HealthKit morning sync, JSON export, server upload.
2. **Lullaby Watch App (watchOS)** — Apple Watch companion. Runs HKWorkoutSession, collects HR/HRV/accelerometer via dedicated collectors, streams 30-second batched SensorPackets to iPhone via WatchConnectivity. Includes persistent WatchDataBuffer for offline resilience.
3. **LullabyTests** — Swift unit tests (7 test files).

**Lullaby Server** (Cloudflare Workers, TypeScript) handles data collection, user auth, and session storage. See `server/` directory. A separate Python inference server for real-time classification is planned for Phase 3.

## Build & Development

- **Xcode version:** 26.3+
- **Swift version:** 6.2 (Approachable Concurrency, strict MainActor isolation enabled)
- **Bundle ID:** `Neovasky.Lullaby` (iOS), `Neovasky.Lullaby.watchkitapp` (watchOS)
- **iOS deployment target:** iOS 18.0+ (minimum for reliable HealthKit sleep stage access)
- **watchOS deployment target:** watchOS 10.0+ (minimum for current CoreMotion + HKWorkoutSession APIs)
- **Minimum hardware:** Apple Watch Series 4+ (required for HealthKit sleep stage data)

### Build Commands
```bash
# Build iOS target
xcodebuild -project Lullaby/Lullaby/Lullaby.xcodeproj -scheme Lullaby -sdk iphonesimulator build

# Build watchOS target
xcodebuild -project Lullaby/Lullaby/Lullaby.xcodeproj -scheme "Lullaby Watch App" -sdk watchsimulator build

# Clean build
xcodebuild -project Lullaby/Lullaby/Lullaby.xcodeproj -scheme Lullaby clean

# Run Python analysis tests
cd analysis && python3 -m pytest -v

# Run data collection server (local dev)
cd server && npm run dev

# Deploy data collection server
cd server && npm run deploy
```

Prefer building and running via Xcode when possible, as the project uses automatic code signing and simulator destinations.

## Entitlements & Permissions Required

Both iOS and watchOS targets need specific entitlements configured before sensor work begins:

### iOS Target
- **HealthKit** — Read: sleep analysis, heart rate, HRV, respiratory rate, wrist temperature, SpO2. Write: sleep analysis.
- **Microphone** — Required for sonar emission analysis and passive audio capture.
- **Background Modes** — Audio (for continuous sonar/mic during sleep), Background processing, Remote notifications.
- **App Groups** — For shared data between iOS and watchOS targets.
- **Info.plist keys:** `NSHealthShareUsageDescription`, `NSHealthUpdateUsageDescription`, `NSMicrophoneUsageDescription`, `NSMotionUsageDescription`.

### watchOS Target
- **HealthKit** — Read: heart rate, HRV. Write: workout sessions.
- **Motion & Fitness** — Required for CoreMotion accelerometer/gyroscope access.
- **Background Modes** — Workout processing (keeps sensors alive during sleep).
- **App Groups** — Shared with iOS target.

## Architecture

**Current state:** Phase 1 (data collection) and Phase 2 (offline ML classification) are implemented. Both iOS and watchOS targets build successfully. The Python analysis suite has 233 passing tests.

**Three-tier system** (per PRD):
- **Apple Watch (watchOS):** Primary biometric sensor (HR, HRV, accelerometer via HKWorkoutSession + CoreMotion). Streams 30-second batched SensorPackets to iPhone via WatchConnectivity. Persistent WatchDataBuffer handles connectivity drops.
- **iPhone (iOS):** Secondary sensor platform (19kHz ultrasonic sonar for breathing detection via vDSP FFT, passive audio classification for snore/breathing/movement/silence). Aggregates all data in SleepSessionStore, exports JSON for offline analysis. Morning sync pulls Apple sleep stages from HealthKit.
- **Data Collection Server (Phase 2.5):** Cloudflare Workers + D1 (SQLite) + R2 (blob storage). Handles user auth (email/password, Google, Apple Sign-In), session upload/download, multi-user data isolation. TypeScript with Hono framework. This is the data transport layer — not the inference server.
- **Inference Server (Phase 3, future):** Real-time sleep stage inference (XGBoost → LSTM/Transformer), per-user calibration loop, cue delivery decision logic via WebSocket. Will be Python (FastAPI). Reads session data from the same R2 storage.

### Key Apple Frameworks
| Framework | Target | Purpose |
|-----------|--------|---------|
| HealthKit | iOS + watchOS | Sleep stages, HR, HRV, respiratory rate, wrist temp, SpO2 |
| WatchConnectivity | iOS + watchOS | Watch ↔ iPhone bidirectional data relay |
| CoreMotion | watchOS | Accelerometer, gyroscope, CMSensorRecorder (36hr buffer) |
| AVFoundation | iOS | Ultrasonic sonar tone generation + microphone capture |
| Accelerate (vDSP) | iOS | FFT and signal processing for sonar analysis |
| CoreML | iOS + watchOS | On-device fallback classifier when server unreachable |
| CoreHaptics / WKInterfaceDevice | watchOS | Haptic cue pattern delivery |

### Data Flow (Nighttime Loop)
```
Watch sensors → WatchConnectivity → iPhone combines with sonar/audio features
→ WebSocket → Cloud classifier → If REM detected with high confidence
→ Cue command back → iPhone → WatchConnectivity → Watch delivers haptic
→ Post-cue sensor data streams back for wake monitoring
```

### Calibration Flow (Morning)
```
iPhone pulls Apple sleep stages from HealthKit (ground truth)
→ Uploads labeled timeline to server
→ Server aligns predictions vs Apple labels
→ Computes accuracy metrics (REM precision, recall, onset latency)
→ Updates per-user model weights
→ User logs dream journal → server correlates cues with lucidity reports
```

## Current Development Phase

### Phase 1: Data Collection Prototype — COMPLETE

All five Phase 1 deliverables are implemented and building:
1. **watchOS app** — HKWorkoutSession + HeartRateCollector + HRVCollector + AccelerometerCollector (100Hz→10Hz decimation), 30-second batch timer, persistent WatchDataBuffer.
2. **iOS app** — SonarEngine (19kHz tone, vDSP FFT, autocorrelation breathing detection), PassiveAudioAnalyzer (RMS, ZCR, spectral centroid, 5-class classification).
3. **WatchConnectivity** — WatchConnectivityManager (watch→phone via transferUserInfo with sequence tracking) + PhoneConnectivityManager (phone-side packet routing).
4. **Morning sync** — MorningSyncManager queries HKCategoryValueSleepAnalysis, filters Apple Watch sources, converts to session-relative SleepStageLabels.
5. **Data export** — SleepSessionStore persists to Documents/sessions/, JSONExporter encodes with .iso8601 + .sortedKeys matching the Python loader format.

### Phase 2: Offline Classification — COMPLETE

Python analysis suite in `analysis/` with 233 passing tests:
- Temporal feature engineering (32 new features: rolling stats, deltas, time-of-night, audio one-hot)
- Multi-session ML pipeline with session-level splitting (prevents temporal leakage)
- XGBoost training (5-class + binary REM), leave-one-session-out CV, hyperparameter tuning
- Evaluation: confusion matrix, SHAP importance, REM onset latency, success criteria gate (REM F1 ≥ 0.65)
- Model export: joblib for Python server, CoreML for iOS/watchOS fallback

### Phase 2.5: Data Collection Server — IMPLEMENTED

Cloudflare Workers server deployed at `https://lullaby-server.aakashjuly18.workers.dev`:
- **Server:** Hono (TypeScript) on Cloudflare Workers, D1 for user/session metadata, R2 for session JSON blobs
- **Auth:** Email+password (PBKDF2), Google Sign-In, Sign in with Apple — supports friends/family contributing data
- **iOS integration:** APIClient + AuthManager + SessionUploader added to the app, auth gate on launch
- **Python CLI:** `lullaby.remote` module for downloading sessions to local analysis pipeline
- **Deviation from PRD:** PRD planned a Python FastAPI server in Phase 3 for real-time inference. This Phase 2.5 server is a simpler data transport layer built earlier to unblock multi-user data collection. The Phase 3 inference server will be built separately and can read from the same R2 storage.

### Next: Real-World Validation

Deploy to real devices, collect several nights of data, and validate that the ML pipeline achieves success criteria on real sensor data. Then:
- **Phase 3:** Real-time inference server (FastAPI, WebSocket), live classification, haptic cue delivery
- **Phase 4:** Per-user calibration loop, dream journal correlation

## Key Constraints

- **Privacy:** Raw audio NEVER leaves the device. Only numeric feature vectors are transmitted to the server. All audio processing (breathing analysis, snore detection, sonar) is on-device only.
- **Battery:** Watch runs HKWorkoutSession all night — battery impact is a key open question. Recommend user charge to 40%+ before sleep.
- **Background execution:** iOS app must maintain sonar + audio processing for ~8 hours without OS termination. Use Background Audio mode and keep AVAudioEngine running.
- **WatchConnectivity reliability:** Messages between watch and phone can be delayed or dropped. Design for eventual consistency, not guaranteed real-time delivery. Buffer data on watch if phone connection drops.
- **Sensor sampling rates:** Watch HR is every few seconds during active workout session. CoreMotion accelerometer up to 100Hz via CMMotionManager. CMSensorRecorder provides 36-hour historical buffer with ~3 second delay.
- **App Sandbox:** Enabled. App Groups registered for Watch ↔ iPhone shared state.
- **Concurrency:** MainActor isolation enforced by default (Swift 6.2). All background sensor work must use explicit actor/task isolation. HealthKit queries and CoreMotion updates run on background threads — never block the main actor.

## Future Considerations

- **AirPods Pro 3** heart rate sensing is currently workout-only with no HRV access. Architecture should support pluggable sensor sources so AirPods can be added later without rearchitecting.
- **Core body temperature** via AirPods ear canal sensors may become available in future — would provide superior circadian phase indicator compared to wrist temperature.
- **Audio cue delivery** via AirPods during sleep is a potential complement/alternative to haptic wrist cues in future phases.

## Git

- Repository is at `Lullaby/Lullaby/` (not the project root)
- Single initial commit (d932855)
- No remote configured yet
- Commit frequently with descriptive messages referencing PRD sections where applicable
