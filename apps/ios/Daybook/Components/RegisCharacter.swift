import SwiftUI

// Regis — wisp character. Two render modes:
//   .png — the actual logo image with breathing motion + warm drop-shadow glow
//   .orb — abstract amber orb (used in Self/Connections where he's a smaller presence)
// Plus a nested layered halo that pulses, and a drifting ping bubble.

struct RegisView: View {
    var size: CGFloat
    var mood: RegisMood
    var hrv: Double             // 0.7..1.3
    var form: RegisForm
    var ping: String? = nil
    var onDonePing: (() -> Void)? = nil
    var onTap: (() -> Void)? = nil

    private var moodSpec: MoodSpec {
        switch mood {
        case .calm:      return MoodSpec(hue: 65, breathSec: 5.2, pulseSec: 3.2, satBoost: 0)
        case .curious:   return MoodSpec(hue: 55, breathSec: 4.2, pulseSec: 2.4, satBoost: 0.04)
        case .concerned: return MoodSpec(hue: 35, breathSec: 6.2, pulseSec: 4.2, satBoost: -0.02)
        }
    }

    private var intensity: Double {
        // mirror chat: 0.85 + (hrv - 1) * 0.5
        max(0.45, min(1.25, 0.85 + (hrv - 1.0) * 0.5))
    }

    private var moodAmber: Color {
        switch mood {
        case .calm:      return Theme.amber
        case .curious:   return Color(red: 1.0, green: 0xC9 / 255.0, blue: 0x7A / 255.0)
        case .concerned: return Color(red: 0xE0 / 255.0, green: 0x8C / 255.0, blue: 0x55 / 255.0)
        }
    }

    var body: some View {
        ZStack {
            // Halo layers
            RegisHalo(size: size, color: moodAmber, intensity: intensity, pulseSec: moodSpec.pulseSec)

            // Body
            switch form {
            case .png:
                RegisPNGBody(size: size, breathSec: moodSpec.breathSec, glowColor: moodAmber)
            case .orb:
                RegisOrbBody(size: size, breathSec: moodSpec.breathSec, color: moodAmber)
            }

            // Drifting ping bubble (if Regis surfaced something)
            if let ping = ping {
                RegisPingBubble(text: ping, onDone: { onDonePing?() })
                    .offset(y: size / 2 + 22)
            }
        }
        .frame(width: size, height: size)
        .contentShape(Rectangle())
        .onTapGesture { onTap?() }
    }
}

// Multi-layer halo — pulses gently in sync with mood/HRV.
struct RegisHalo: View {
    var size: CGFloat
    var color: Color
    var intensity: Double
    var pulseSec: Double

    @State private var pulse = false

    var body: some View {
        ZStack {
            // Outer diffuse
            Circle()
                .fill(
                    RadialGradient(
                        colors: [color.opacity(0.22 * intensity), color.opacity(0.10 * intensity), .clear],
                        center: .center, startRadius: 0, endRadius: size * 1.3
                    )
                )
                .frame(width: size * 2.6, height: size * 2.6)
                .blur(radius: 8)
                .scaleEffect(pulse ? 1.08 : 1.0)
                .opacity(pulse ? 1.0 : 0.78)
                .animation(.easeInOut(duration: pulseSec).repeatForever(autoreverses: true), value: pulse)

            // Inner tighter
            Circle()
                .fill(
                    RadialGradient(
                        colors: [color.opacity(0.55 * intensity), color.opacity(0.18 * intensity), .clear],
                        center: .center, startRadius: 0, endRadius: size * 0.85
                    )
                )
                .frame(width: size * 1.7, height: size * 1.7)
                .blur(radius: 4)
                .scaleEffect(pulse ? 1.12 : 1.0)
                .opacity(pulse ? 1.0 : 0.85)
                .animation(.easeInOut(duration: pulseSec * 0.7).repeatForever(autoreverses: true), value: pulse)
        }
        .allowsHitTesting(false)
        .onAppear { pulse = true }
    }
}

// PNG body with continuous breathing + warm drop-shadow glow.
struct RegisPNGBody: View {
    var size: CGFloat
    var breathSec: Double
    var glowColor: Color

    @State private var breath = false

    var body: some View {
        Image("regis")
            .resizable()
            .interpolation(.high)
            .aspectRatio(contentMode: .fit)
            .frame(width: size, height: size)
            .scaleEffect(breath ? 1.025 : 1.0)
            .offset(y: breath ? -6 : 0)
            .brightness(breath ? 0.05 : 0.0)
            .shadow(color: glowColor.opacity(0.55), radius: 22, x: 0, y: 18)
            .shadow(color: glowColor.opacity(0.45), radius: 18, x: 0, y: 0)
            .animation(.easeInOut(duration: breathSec).repeatForever(autoreverses: true), value: breath)
            .onAppear { breath = true }
    }
}

// Abstract amber orb body — used in Self / Connections.
struct RegisOrbBody: View {
    var size: CGFloat
    var breathSec: Double
    var color: Color

    @State private var breath = false

    private var bodyDiameter: CGFloat { size * 0.6 }

    var body: some View {
        ZStack {
            Circle()
                .fill(
                    RadialGradient(
                        colors: [
                            Color(red: 1.0, green: 246/255.0, blue: 226/255.0),
                            Color(red: 1.0, green: 220/255.0, blue: 160/255.0),
                            color,
                            color.opacity(0.7),
                        ],
                        center: UnitPoint(x: 0.38, y: 0.32),
                        startRadius: 0, endRadius: bodyDiameter * 0.6
                    )
                )
                .overlay(
                    // specular highlight
                    Circle()
                        .fill(
                            RadialGradient(
                                colors: [Color(red: 1.0, green: 250/255.0, blue: 235/255.0).opacity(0.9), .clear],
                                center: .center, startRadius: 0, endRadius: bodyDiameter * 0.16
                            )
                        )
                        .frame(width: bodyDiameter * 0.28, height: bodyDiameter * 0.22)
                        .offset(x: -bodyDiameter * 0.18, y: -bodyDiameter * 0.20)
                        .blur(radius: 2)
                )
                .shadow(color: color.opacity(0.6), radius: 22, x: 0, y: 0)
                .shadow(color: color.opacity(0.35), radius: 48, x: 0, y: 0)
                .frame(width: bodyDiameter, height: bodyDiameter)
                .scaleEffect(breath ? 1.025 : 1.0)
                .offset(y: breath ? -3 : 0)
                .animation(.easeInOut(duration: breathSec).repeatForever(autoreverses: true), value: breath)
                .onAppear { breath = true }
        }
    }
}

// Drifting ping bubble — Regis surfaces a quiet line, drifts up, fades.
struct RegisPingBubble: View {
    var text: String
    var onDone: () -> Void

    @State private var visible = false
    @State private var lifted = false

    var body: some View {
        Text(text)
            .font(Fonts.quote(15))
            .lineSpacing(2)
            .foregroundStyle(Theme.amberSpeech)
            .multilineTextAlignment(.center)
            .frame(maxWidth: 280)
            .padding(.horizontal, 18)
            .padding(.vertical, 11)
            .background(
                ZStack {
                    Capsule(style: .continuous)
                        .fill(.ultraThinMaterial)
                    Capsule(style: .continuous)
                        .fill(Theme.pearl.opacity(0.07))
                    Capsule(style: .continuous)
                        .strokeBorder(Color(red: 1.0, green: 230/255.0, blue: 200/255.0).opacity(0.22), lineWidth: 0.5)
                    Capsule(style: .continuous)
                        .stroke(
                            LinearGradient(
                                colors: [Color(red: 1.0, green: 245/255.0, blue: 230/255.0).opacity(0.40), .clear],
                                startPoint: .top, endPoint: .center
                            ),
                            lineWidth: 0.8
                        )
                        .blendMode(.plusLighter)
                }
            )
            .shadow(color: .black.opacity(0.4), radius: 14, x: 0, y: 8)
            .opacity(visible ? 1 : 0)
            .offset(y: lifted ? -6 : 8)
            .allowsHitTesting(false)
            .onAppear {
                withAnimation(.easeOut(duration: 0.6)) { visible = true }
                withAnimation(.linear(duration: 7.2)) { lifted = true }
                DispatchQueue.main.asyncAfter(deadline: .now() + 6.6) {
                    withAnimation(.easeIn(duration: 0.6)) { visible = false }
                }
                DispatchQueue.main.asyncAfter(deadline: .now() + 7.2) { onDone() }
            }
    }
}
