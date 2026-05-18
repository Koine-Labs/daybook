import SwiftUI

// RecallView — morning recall ceremony. Warming mode (transition from witness
// back toward companion). Port of ScreenRecall from screens-witness.jsx.
// Three phases: prompt → recording → held. The mic button toggles between
// them; nothing is actually recorded yet.
// TODO: wire mic to apps/recall/recorder.py + whisper_client.py via APIClient.
// TODO: real transcript should stream in from the recall pipeline.
struct RecallView: View {
    @Environment(Theme.self) private var theme

    enum Phase: String, Hashable {
        case prompt
        case recording
        case held
    }

    @State private var phase: Phase = .prompt
    @State private var transcript: String = ""
    @State private var streamTimer: Timer?

    private let mockTranscriptLines: [String] = [
        "there was a kitchen.",
        " warm tile under my feet.",
        " someone's mother — not mine —",
        " was there, near the window.",
        " then a staircase that kept going.",
        " one more flight, one more."
    ]

    var body: some View {
        ZStack {
            background
                .ignoresSafeArea()

            StarfieldView()
                .opacity(phase == .held ? 0.0 : 0.6)
                .animation(.easeInOut(duration: 1.2), value: phase)
                .allowsHitTesting(false)

            VStack(spacing: 0) {
                header
                    .padding(.horizontal, 24)
                    .padding(.top, 54)

                Spacer(minLength: 0)

                phaseBody
                    .padding(.horizontal, 32)
                    .padding(.bottom, 110)

                Spacer(minLength: 0)
            }
        }
        .onDisappear {
            streamTimer?.invalidate()
            streamTimer = nil
        }
    }

    // MARK: - Background

    private var background: some View {
        Group {
            if phase == .held {
                LinearGradient(
                    gradient: Gradient(stops: [
                        .init(color: Color(hex: "2a1f12"), location: 0.0),
                        .init(color: Color(hex: "3a2a18"), location: 0.4),
                        .init(color: Color(hex: "4a361f"), location: 1.0)
                    ]),
                    startPoint: .top,
                    endPoint: .bottom
                )
            } else {
                LinearGradient(
                    gradient: Gradient(stops: [
                        .init(color: Color(hex: "0f131e"), location: 0.0),
                        .init(color: Color(hex: "1a1108"), location: 0.5),
                        .init(color: Color(hex: "2a1a0c"), location: 1.0)
                    ]),
                    startPoint: .top,
                    endPoint: .bottom
                )
            }
        }
        .animation(.easeInOut(duration: 1.4), value: phase)
    }

    // MARK: - Header

    private var header: some View {
        HStack {
            Text("06:47 · before it slips")
                .dbMeta(Color(red: 255/255, green: 233/255, blue: 204/255, opacity: 0.5))
            Spacer()
            WispView(size: 20, state: headerWispState, mode: .witness)
        }
    }

    private var headerWispState: WispState {
        switch phase {
        case .prompt: return .composing
        case .recording: return .listening
        case .held: return .held
        }
    }

    // MARK: - Phase bodies

    @ViewBuilder
    private var phaseBody: some View {
        switch phase {
        case .prompt: promptPhase
        case .recording: recordingPhase
        case .held: heldPhase
        }
    }

    private var promptPhase: some View {
        VStack(spacing: 0) {
            WispView(size: 88, state: .composing, mode: .witness)
                .padding(.bottom, 14)

            VStack(spacing: 4) {
                RegisQuote("\"So. What did you bring back,\"", size: 32)
                    .multilineTextAlignment(.center)
                RegisQuote("\"or did you sleepwalk through that one?\"", size: 32)
                    .multilineTextAlignment(.center)
            }

            Spacer().frame(height: 56)

            VStack(spacing: 14) {
                MicButton(size: 88) {
                    startRecording()
                }
                Text("hold to speak · or type below")
                    .dbMeta(Color(red: 255/255, green: 233/255, blue: 204/255, opacity: 0.55))
            }

            Spacer().frame(height: 22)

            Button {
                phase = .held
                if transcript.isEmpty {
                    transcript = ""
                }
            } label: {
                Text("nothing tonight")
                    .font(DBFont.serif(14, italic: true))
                    .foregroundStyle(Color(red: 255/255, green: 233/255, blue: 204/255, opacity: 0.7))
                    .padding(.horizontal, 16)
                    .padding(.vertical, 8)
                    .overlay(
                        Capsule()
                            .stroke(Color(red: 255/255, green: 233/255, blue: 204/255, opacity: 0.25), lineWidth: 0.5)
                    )
            }
            .buttonStyle(.plain)
        }
    }

    private var recordingPhase: some View {
        VStack(spacing: 0) {
            WispView(size: 72, state: .listening, mode: .witness)
                .padding(.bottom, 24)

            VuBars(count: 20, color: Color(hex: "FFCB95"), height: 48)
                .frame(height: 60)

            HStack(alignment: .firstTextBaseline, spacing: 2) {
                Text(transcript)
                    .font(DBFont.serif(22))
                    .lineSpacing(22 * 0.4)
                    .foregroundStyle(Color(hex: "FFE9CC"))
                    .multilineTextAlignment(.center)
                BlinkingCursor()
            }
            .frame(minHeight: 88)
            .padding(.top, 14)

            Spacer().frame(height: 32)

            VStack(spacing: 12) {
                MicButton(size: 72, active: true) {
                    stopRecording()
                }
                Text("tap when done")
                    .dbMeta(Color(red: 255/255, green: 203/255, blue: 149/255, opacity: 0.7))
            }
        }
    }

    private var heldPhase: some View {
        VStack(spacing: 0) {
            WispView(size: 64, state: .held, mode: .witness)
                .padding(.bottom, 6)

            RegisQuote("\"Held.\"", size: 48)
                .multilineTextAlignment(.center)

            Spacer().frame(height: 26)

            recallReceipt

            Spacer().frame(height: 22)

            Button {
                phase = .prompt
                transcript = ""
            } label: {
                Text("add another fragment")
                    .font(DBFont.serif(14, italic: true))
                    .foregroundStyle(Color(hex: "FFE9CC"))
                    .padding(.horizontal, 22)
                    .padding(.vertical, 10)
                    .background(
                        Capsule().fill(Color.white.opacity(0.08))
                    )
                    .overlay(
                        Capsule().stroke(Color(red: 255/255, green: 233/255, blue: 204/255, opacity: 0.2), lineWidth: 0.5)
                    )
            }
            .buttonStyle(.plain)
        }
    }

    private var recallReceipt: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("06:47 · tue · 17 may")
                .dbMeta(Color(red: 255/255, green: 233/255, blue: 204/255, opacity: 0.5))

            Text(transcript.isEmpty
                 ? "a kitchen made of warm tile. someone's mother was there. then a staircase that kept going. one more flight, one more."
                 : transcript)
                .font(DBFont.serif(18))
                .lineSpacing(18 * 0.4)
                .foregroundStyle(Color(hex: "FFE9CC"))

            HStack(spacing: 5) {
                ForEach(["kitchen", "mother", "warm", "staircase"], id: \.self) { tag in
                    Text(tag)
                        .font(DBFont.mono(10))
                        .foregroundStyle(Color(hex: "FFCB95"))
                        .padding(.horizontal, 6)
                        .padding(.vertical, 1)
                        .background(
                            RoundedRectangle(cornerRadius: 4, style: .continuous)
                                .fill(Color(red: 255/255, green: 203/255, blue: 149/255, opacity: 0.1))
                        )
                }
            }
            .padding(.top, 2)
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 16)
        .frame(maxWidth: 320, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(Color.white.opacity(0.05))
                .overlay(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .stroke(Color(red: 255/255, green: 233/255, blue: 204/255, opacity: 0.12), lineWidth: 0.5)
                )
        )
    }

    // MARK: - Recording state machine

    private func startRecording() {
        phase = .recording
        transcript = ""
        streamTimer?.invalidate()
        var idx = 0
        streamTimer = Timer.scheduledTimer(withTimeInterval: 1.1, repeats: true) { timer in
            guard idx < mockTranscriptLines.count else {
                timer.invalidate()
                return
            }
            transcript += mockTranscriptLines[idx]
            idx += 1
        }
    }

    private func stopRecording() {
        streamTimer?.invalidate()
        streamTimer = nil
        phase = .held
    }
}

private struct BlinkingCursor: View {
    @State private var on: Bool = false

    var body: some View {
        Rectangle()
            .fill(Color(hex: "FFCB95"))
            .frame(width: 2, height: 22)
            .opacity(on ? 1.0 : 0.0)
            .onAppear {
                withAnimation(.linear(duration: 0.5).repeatForever(autoreverses: true)) {
                    on = true
                }
            }
    }
}

#Preview {
    let theme = Theme()
    theme.mode = .warming
    return RecallView()
        .environment(theme)
}
