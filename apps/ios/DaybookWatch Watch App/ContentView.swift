import SwiftUI

// Daybook Watch — single face, four states.
//
// State model:
//   - Rest   → default. What the user sees on wrist-raise.
//   - Listen → Regis surfaced something. Server-pushed (phone →
//              WatchConnectivity). Not user-triggerable. NOT WIRED YET.
//   - Speak  → phone is playing Regis's TTS. Server-pushed. NOT WIRED YET.
//   - Talk   → user is recording. Triggered by long-press, released on lift.
//
// Real gestures (now):
//   - long-press   → Talk (records mic; release returns to Rest)
//   - HealthKit HR → drives the HR readout on Rest
//
// (No tap-to-cycle. The earlier testing scaffold was confusing — random
// tap pulling up Listen made the model unreadable. To see Listen / Speak
// states during dev, set the @State initial value below.)

struct ContentView: View {
    @State private var state: WatchFaceState = .rest
    @State private var heartRate = HeartRateClient.shared
    @State private var pushedLine: String? = nil   // populated when a ping arrives

    // MARK: - WatchConnectivity (#14)
    @State private var session = WatchSession.shared
    @State private var pressStartedAt: Date? = nil
    @State private var autoRestWorkItem: DispatchWorkItem? = nil

    var body: some View {
        ZStack {
            switch state {
            case .rest:
                WatchRest(heartRate: heartRate)
            case .listen:
                // Only renders if we actually have a line. If not, fall back
                // to Rest — never show Listen with empty content.
                if let line = pushedLine {
                    WatchListen(line: line)
                } else {
                    WatchRest(heartRate: heartRate)
                }
            case .speak:
                WatchSpeak()
            case .talk:
                WatchTalk(isRecording: state == .talk)
            }
        }
        .ignoresSafeArea()
        .contentShape(Rectangle())
        .onLongPressGesture(
            minimumDuration: 0.4,
            perform: {},
            onPressingChanged: { pressing in
                withAnimation(.easeInOut(duration: 0.25)) {
                    if pressing {
                        pressStartedAt = Date()
                        state = .talk
                    } else {
                        // MARK: - WatchConnectivity (#14)
                        // Report press duration to phone on release; routes
                        // to AppState.lastTalkPressDuration on the phone side.
                        if let start = pressStartedAt {
                            let dur = Date().timeIntervalSince(start)
                            session.reportTalkPressed(durationSec: dur)
                        }
                        pressStartedAt = nil
                        state = .rest
                    }
                }
            }
        )
        .onAppear {
            heartRate.start()

            // MARK: - WatchConnectivity (#14)
            // Register inbound-message handlers BEFORE activating so we don't
            // miss anything that comes back during activation.
            session.onShowListen = { line, ttl in
                pushedLine = line
                withAnimation(.easeInOut(duration: 0.25)) { state = .listen }
                scheduleAutoRest(after: ttl)
            }
            session.onShowSpeak = {
                withAnimation(.easeInOut(duration: 0.25)) { state = .speak }
                scheduleAutoRest(after: 8)  // conservative default
            }
            session.onDismiss = {
                autoRestWorkItem?.cancel()
                pushedLine = nil
                withAnimation(.easeInOut(duration: 0.25)) { state = .rest }
            }
            session.activate()
        }
    }

    // MARK: - WatchConnectivity (#14)
    /// Auto-return to Rest after `seconds`. Cancels any prior scheduled return.
    private func scheduleAutoRest(after seconds: Double) {
        autoRestWorkItem?.cancel()
        let item = DispatchWorkItem {
            withAnimation(.easeInOut(duration: 0.25)) {
                pushedLine = nil
                state = .rest
            }
        }
        autoRestWorkItem = item
        DispatchQueue.main.asyncAfter(deadline: .now() + seconds, execute: item)
    }
}

#Preview { ContentView() }
