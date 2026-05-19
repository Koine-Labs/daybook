import SwiftUI

// ContentView — three-room shell (Self ← Now → Connections) with constellation indicator,
// chat overlay, ambient particles, HRV simulator, and proactive Regis pings.
// Implementation of the Claude Design output (apps/ios/_design_package).

private enum Room: Int, CaseIterable, Identifiable {
    case self_ = 0, now = 1, connections = 2
    var id: Int { rawValue }
    var label: String {
        switch self {
        case .self_:        return "self · who you've been"
        case .now:          return "now · with regis"
        case .connections:  return "connections · the wider net"
        }
    }
}

struct ContentView: View {
    @Environment(AppState.self) private var appState
    @State private var tweaks = Tweaks()
    @State private var index: Int = Room.now.rawValue
    @State private var chatOpen: Bool = false

    // Timers
    @State private var hrvTimer: Timer?
    @State private var pingTimer: Timer?

    var body: some View {
        ZStack {
            // Outer black backdrop so safe-area glow doesn't bleed
            Theme.bgDeep.ignoresSafeArea()

            // Room background — recomputes per visible room (spill falls off away from Now)
            RoomBackground(tweaks: tweaks, roomIndex: index)
                .animation(.easeInOut(duration: 0.6), value: index)

            // Ambient drifting particles
            AmbientParticles(count: 16, show: tweaks.particles)
                .ignoresSafeArea()

            // Sliding rooms via TabView paging (iOS-native and respects child ScrollViews)
            TabView(selection: $index) {
                SelfRoom(tweaks: tweaks, bodySeries: appState.bodySeries)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .tag(Room.self_.rawValue)
                NowRoom(
                    tweaks: tweaks,
                    onTalk: { openChat() },
                    ping: tweaks.proactivePing,
                    onDonePing: { tweaks.proactivePing = nil },
                    // MARK: - HealthKit (#13)
                    bodyLine: appState.bodySummary?.line,
                    bodyMeta: appState.bodySummary?.last_sleep_ended_at.flatMap { relativeTimeAgo($0) }
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .tag(Room.now.rawValue)
                ConnectionsRoom(tweaks: tweaks)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .tag(Room.connections.rawValue)
            }
            .tabViewStyle(.page(indexDisplayMode: .never))

            // Overlay chrome — constellation indicator + room label
            VStack(spacing: 4) {
                ConstellationDots(index: index) { i in
                    withAnimation(.easeInOut(duration: 0.48)) { index = i }
                }
                .padding(.top, 8)

                Text(roomLabel)
                    .font(Fonts.body(9, .semibold))
                    .tracking(1.8)
                    .textCase(.uppercase)
                    .foregroundStyle(Theme.pearl.opacity(0.32))
                    .id(index) // re-animate on change
                    .transition(.opacity)
                    .animation(.easeInOut(duration: 0.42), value: index)
            }
            .padding(.top, 56)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
            .allowsHitTesting(true)

            // Chat overlay
            if chatOpen {
                ChatOverlay(tweaks: tweaks, onClose: { closeChat() })
                    .transition(.opacity)
            }
        }
        .preferredColorScheme(.dark)
        .onAppear {
            startTimers()
        }
        .onDisappear { stopTimers() }
        // Re-derive halo intensity when real HRV updates land (#13 → halo).
        .onChange(of: appState.bodySummary?.hrv_avg_ms) { _, _ in
            syncHrv()
        }
    }

    private var roomLabel: String {
        Room(rawValue: index)?.label ?? ""
    }

    private func openChat() {
        withAnimation(.easeInOut(duration: 0.4)) { chatOpen = true }
    }
    private func closeChat() {
        withAnimation(.easeInOut(duration: 0.3)) { chatOpen = false }
    }

    // MARK: - Live simulators

    private func startTimers() {
        // HRV halo intensity comes from real data now (post-#13). When
        // appState.bodySummary updates, syncHrv() re-derives tweaks.hrv from
        // the real average. No more random walk — if no data exists Regis's
        // halo sits at neutral until HealthKit catches up.
        syncHrv()

        // Proactive ping cadence — only if there are real pings to surface.
        guard !NOW_PINGS.isEmpty else { return }
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.8) {
            surfacePing()
            pingTimer = Timer.scheduledTimer(withTimeInterval: 14, repeats: true) { _ in
                surfacePing()
            }
        }
    }

    /// Map real HRV ms → halo intensity multiplier (the same 0.7-1.3 range
    /// the visualization was tuned for). When HRV is unknown, halo sits at
    /// neutral 1.0 (no fake animation).
    private func syncHrv() {
        guard let ms = appState.bodySummary?.hrv_avg_ms else {
            tweaks.hrv = 1.0
            return
        }
        // Linear map: 15ms → 0.80 (soft halo), 35ms → 1.0 (neutral),
        // 60ms → 1.20 (lively). Clamped to keep visual sane.
        let mapped = 0.80 + ((ms - 15.0) / 45.0) * 0.40
        tweaks.hrv = max(0.7, min(1.3, mapped))
    }

    private func surfacePing() {
        guard !chatOpen else { return }
        guard !NOW_PINGS.isEmpty else { return }
        tweaks.proactivePing = NOW_PINGS.randomElement()
    }

    private func stopTimers() {
        hrvTimer?.invalidate(); hrvTimer = nil
        pingTimer?.invalidate(); pingTimer = nil
    }

    // MARK: - HealthKit (#13)
    /// Lowercase relative-time string for the body whisper meta line.
    /// e.g. "updated 3h ago" / "updated just now". Returns nil if `date`
    /// is in the future (shouldn't happen for HealthKit data).
    private func relativeTimeAgo(_ date: Date) -> String? {
        let secs = Date().timeIntervalSince(date)
        guard secs >= 0 else { return nil }
        let prefix = "updated"
        if secs < 60 { return "\(prefix) just now" }
        if secs < 3600 { return "\(prefix) \(Int(secs / 60))m ago" }
        if secs < 86400 { return "\(prefix) \(Int(secs / 3600))h ago" }
        return "\(prefix) \(Int(secs / 86400))d ago"
    }
}

#Preview {
    ContentView()
        .environment(AppState())
}
