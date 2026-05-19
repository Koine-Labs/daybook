import SwiftUI

// Daybook Watch — single face, four states (Rest / Listen / Speak / Talk).
//
// Real triggers (now):
//   - long-press anywhere      → Talk (records via mic; release returns to Rest)
//   - HealthKit heart rate     → drives the HR readout on Rest
//
// Testing scaffolding (until WatchConnectivity + TTS-active feed are wired):
//   - tap anywhere             → cycles Rest → Listen → Speak → Talk → Rest

struct ContentView: View {
    @State private var state: WatchFaceState = .rest
    @State private var heartRate = HeartRateClient.shared

    var body: some View {
        ZStack {
            switch state {
            case .rest:    WatchRest(heartRate: heartRate)
            case .listen:  WatchListen()
            case .speak:   WatchSpeak()
            case .talk:    WatchTalk(isRecording: state == .talk)
            }
        }
        .ignoresSafeArea()
        .contentShape(Rectangle())
        .onTapGesture { cycleState() }
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

    private func cycleState() {
        let all = WatchFaceState.allCases
        if let i = all.firstIndex(of: state) {
            withAnimation(.easeInOut(duration: 0.35)) {
                state = all[(i + 1) % all.count]
            }
        }
    }
}

#Preview { ContentView() }
