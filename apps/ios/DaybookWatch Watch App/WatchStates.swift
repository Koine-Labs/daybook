import SwiftUI

// Four states of the watch face. VStack-based layouts so content respects
// watchOS safe areas (status bar at top, rounded corners) instead of being
// absolutely positioned and clipped.

enum WatchFaceState: String, CaseIterable, Identifiable {
    case rest, listen, speak, talk
    var id: String { rawValue }
}

// MARK: - Reusable atoms

struct WatchBiometric: View {
    enum Kind: String { case hr, hrv }
    var kind: Kind
    var value: String

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            Text(kind.rawValue.uppercased())
                .font(WatchFonts.mono(10))
                .tracking(0.9)
                .foregroundStyle(WatchTheme.pearlFaint)
            Text(value)
                .font(WatchFonts.mono(18, .medium))
                .foregroundStyle(WatchTheme.pearlDim)
                .monospacedDigit()
        }
    }
}

struct WatchVoiceLine: View {
    var text: String
    var body: some View {
        Text(text)
            .font(WatchFonts.quote(13))
            .multilineTextAlignment(.center)
            .foregroundStyle(WatchTheme.amberSpeech)
            .shadow(color: .black.opacity(0.5), radius: 4, x: 0, y: 1)
            .lineSpacing(2)
            .lineLimit(3)
            .frame(maxWidth: 160, alignment: .center)
    }
}

struct MiniWaveform: View {
    var active: Bool
    private let heights: [CGFloat] = [4, 9, 14, 11, 7, 12, 5]
    @State private var animate = false

    var body: some View {
        HStack(alignment: .center, spacing: 2.5) {
            ForEach(0..<heights.count, id: \.self) { i in
                let h = heights[i]
                Capsule()
                    .fill(active ? WatchTheme.amber : WatchTheme.pearlGhost)
                    .frame(width: 2.2, height: animate ? h : h * 0.5)
                    .shadow(color: active ? WatchTheme.amberGlow.opacity(0.7) : .clear, radius: 2)
                    .animation(
                        .easeInOut(duration: 0.9 + Double(i % 3) * 0.25)
                            .delay(Double(i) * 0.08)
                            .repeatForever(autoreverses: true),
                        value: animate
                    )
            }
        }
        .frame(height: 16)
        .onAppear { animate = true }
    }
}

// MARK: - The four state views

struct WatchRest: View {
    var heartRate: HeartRateClient = .shared

    var body: some View {
        ZStack {
            WatchBackground(mood: .calm, intensity: 1.0)
            VStack(spacing: 4) {
                Spacer(minLength: 18)  // headroom for system clock + breath bob
                // Size matches the other states (Listen/Speak=84, Talk=80) so
                // Regis sits comfortably inside the rounded-display mask. 100
                // pushed body extensions into the rounded-corner clip zone.
                WatchRegis(size: 84, mood: .calm, hrv: 1.0)
                Spacer(minLength: 6)
                WatchBiometric(
                    kind: .hr,
                    value: heartRate.bpm.map { "\($0)" } ?? "—"
                )
                .padding(.bottom, 10)
            }
            .padding(.horizontal, 12)
        }
    }
}

struct WatchListen: View {
    // No default — Listen only renders when there's a real line from a
    // real ping (phone → WatchConnectivity). No mock copy.
    var line: String

    var body: some View {
        ZStack {
            WatchBackground(mood: .curious, intensity: 1.15)
            VStack(spacing: 4) {
                Spacer(minLength: 26)  // more headroom — voice line at bottom
                                       // pushes Regis up; halo extending past
                                       // the system clock zone was the bug.
                WatchRegis(size: 72, mood: .curious, hrv: 1.1)
                Spacer(minLength: 4)
                WatchVoiceLine(text: line)
                    .padding(.bottom, 12)
            }
            .padding(.horizontal, 14)
            .frame(maxWidth: .infinity)
        }
    }
}

struct WatchSpeak: View {
    @State private var pulse = false

    var body: some View {
        ZStack {
            WatchBackground(mood: .calm, intensity: 1.5)

            // Concentric rings centered on Regis. Largest ring stays inside
            // the ~205pt watch screen even at peak pulse scale (1.06×).
            // (96 + 3*22) * 1.06 = 171pt — safely inside.
            ZStack {
                ForEach(1..<4, id: \.self) { i in
                    let s = CGFloat(96 + i * 22)
                    Circle()
                        .strokeBorder(WatchTheme.amber.opacity(0.45 - Double(i) * 0.11), lineWidth: 0.5)
                        .frame(width: s, height: s)
                        .scaleEffect(pulse ? 1.06 : 1.0)
                        .opacity(pulse ? 1.0 : 0.78)
                        .animation(
                            .easeInOut(duration: 1.8 + Double(i) * 0.25)
                                .delay(Double(i) * 0.18)
                                .repeatForever(autoreverses: true),
                            value: pulse
                        )
                }
                WatchRegis(size: 84, mood: .calm, hrv: 1.2)
            }

            VStack {
                Spacer()
                Text("SPEAKING")
                    .font(WatchFonts.mono(9))
                    .tracking(1.8)
                    .foregroundStyle(WatchTheme.amber.opacity(0.55))
                    .padding(.bottom, 10)
            }
        }
        .onAppear { pulse = true }
    }
}

struct WatchTalk: View {
    var isRecording: Bool = true

    var body: some View {
        ZStack {
            WatchBackground(mood: .curious, intensity: 1.4)

            VStack(spacing: 4) {
                Spacer(minLength: 18)
                ZStack {
                    Circle()
                        .strokeBorder(WatchTheme.amber.opacity(0.65), lineWidth: 1.5)
                        .frame(width: 138, height: 138)
                        .shadow(color: WatchTheme.amber.opacity(0.35), radius: 12)
                    WatchRegis(size: 80, mood: .curious, hrv: 1.15, ringExpand: 0.3)
                }
                Spacer(minLength: 4)
                MiniWaveform(active: isRecording)
                Text(isRecording ? "LISTENING" : "HOLD TO SPEAK")
                    .font(WatchFonts.mono(9))
                    .tracking(1.8)
                    .foregroundStyle(Color(red: 1.0, green: 200/255.0, blue: 140/255.0).opacity(0.55))
                    .padding(.bottom, 10)
            }
            .padding(.horizontal, 10)
        }
    }
}
