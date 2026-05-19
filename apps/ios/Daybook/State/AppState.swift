import SwiftUI

// AppState — minimal root state container for the v2 clean-slate iOS app.
//
// The v1 UI iteration (tabs + cards + wisp wandering across screens) lives
// archived under apps/ios/_archive_v1_ui/. This is the foundation for the
// next direction: single-surface-that-morphs around a persistent fireball
// (Regis as visible presence).

@Observable
final class AppState {
    // HTTP client pointed at the FastAPI bridge. Uses `APIClient.shared`
    // which reads the base URL from Info.plist (`DaybookAPIBaseURL`).
    let api: APIClient = .shared

    // First /chat reply from the server seeds this. Subsequent messages reuse
    // it so the whole session shares one conversation row in Postgres.
    var conversationId: String? = nil

    // MARK: - HealthKit (#13)

    // HealthKitClient.shared is @MainActor-isolated — we don't store a
    // reference at AppState init time (nonisolated context). Every method
    // below hops to @MainActor before touching the singleton.

    /// Latest body picture from the server (composed whisper line + stats).
    /// Nil = "no data yet" — UI falls back to its empty-state copy.
    var bodySummary: APIClient.BodySummary? = nil

    /// Seven-day series for the BodyAurora on Self. Nil until first refresh.
    var bodySeries: APIClient.BodySeriesResponse? = nil

    /// Last successful upload→refresh pair. Used to throttle aggressive
    /// scenePhase toggles (don't re-poll every foreground bounce).
    private var lastBodyRefreshAt: Date? = nil
    private let bodyRefreshMinInterval: TimeInterval = 60

    /// Last upload attempt time. Throttles `uploadHealthSnapshot` so
    /// scenePhase chatter (active ↔ background) can't hammer HealthKit
    /// or the API. Independent of `lastBodyRefreshAt` because the upload
    /// + refresh share a cost ceiling.
    private var lastUploadAt: Date? = nil
    private let uploadMinInterval: TimeInterval = 60

    /// Background refresh timer kicked off on first start.
    private var bodyRefreshTimer: Timer? = nil

    /// Request HealthKit auth (idempotent) then kick off an initial fetch.
    /// Wired from DaybookApp's .task on launch.
    func startHealthKit() {
        Task { @MainActor in
            await HealthKitClient.shared.requestAuthorizationIfNeeded()
            await uploadHealthSnapshot()
            startBodyRefreshTimer()
        }
    }

    /// Pull any new HealthKit samples, ship them to FastAPI, then refresh
    /// the body summary + series so the UI updates. Throttled so rapid
    /// scenePhase transitions (foreground ↔ background) coalesce into one
    /// sweep per minute. `force=true` bypasses the throttle (used by the
    /// internal 5-min timer that wants a real periodic snapshot).
    func uploadHealthSnapshot(force: Bool = false) async {
        if !force, let last = lastUploadAt,
           Date().timeIntervalSince(last) < uploadMinInterval {
            return
        }
        lastUploadAt = Date()
        await HealthKitClient.shared.fetchAndUpload(api: api)
        await refreshBody(force: true)
    }

    /// Refresh just the body summary + series (no new sample upload).
    /// `force=false` skips if we polled recently — cheap protection from
    /// scenePhase chatter.
    func refreshBody(force: Bool = false) async {
        if !force, let last = lastBodyRefreshAt,
           Date().timeIntervalSince(last) < bodyRefreshMinInterval {
            return
        }
        async let summary: APIClient.BodySummary? = try? api.bodySummary()
        async let series: APIClient.BodySeriesResponse? = try? api.bodySeries(days: 7)
        let (s, ser) = await (summary, series)
        if let s { bodySummary = s }
        if let ser { bodySeries = ser }
        lastBodyRefreshAt = Date()
    }

    /// Periodic refresh (every 5 min) while the app is in foreground.
    /// Bypasses the throttle since a 5-min cadence is the throttle.
    private func startBodyRefreshTimer() {
        bodyRefreshTimer?.invalidate()
        bodyRefreshTimer = Timer.scheduledTimer(withTimeInterval: 300, repeats: true) { [weak self] _ in
            Task { @MainActor in await self?.uploadHealthSnapshot(force: true) }
        }
    }

    // Likely future fields (deferred until the next direction settles):
    //   - var surfaceMode: SurfaceMode  // .resting / .capturing / .browsing / .settings
    //   - var fireballState: FireballState  // .idle / .listening / .composing / .alert
    //   - var settingsOpen: Bool
}
