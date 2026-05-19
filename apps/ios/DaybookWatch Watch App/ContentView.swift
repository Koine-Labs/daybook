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
                    state = pressing ? .talk : .rest
                }
            }
        )
        .onAppear { heartRate.start() }
    }
}

#Preview { ContentView() }
