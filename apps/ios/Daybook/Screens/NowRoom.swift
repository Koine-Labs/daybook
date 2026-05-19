import SwiftUI

// NowRoom — front door. Regis present, body/mind whispers, micro-states, talk pill.

struct NowRoom: View {
    var tweaks: Tweaks
    var onTalk: () -> Void
    var ping: String?
    var onDonePing: () -> Void

    // Real day + time, formatted lowercase (e.g. "tuesday · 7:42")
    private var nowLabel: String {
        let now = Date()
        let dayFmt = DateFormatter()
        dayFmt.dateFormat = "EEEE"
        let day = dayFmt.string(from: now).lowercased()
        let timeFmt = DateFormatter()
        timeFmt.dateFormat = "H:mm"
        let time = timeFmt.string(from: now)
        return "\(day) · \(time)"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Top whisper — real day/time (centered)
            VStack(spacing: 5) {
                Text(nowLabel).labelMono(Theme.pearl.opacity(0.42), size: 10)
            }
            .frame(maxWidth: .infinity)
            .padding(.bottom, 6)

            // Regis center stage
            ZStack {
                RegisView(
                    size: 220,
                    mood: tweaks.mood,
                    hrv: tweaks.hrv,
                    form: tweaks.regisForm,
                    ping: ping,
                    onDonePing: onDonePing,
                    onTap: onTalk
                )
            }
            .frame(maxWidth: .infinity)
            .frame(height: 260)
            .padding(.top, 4)

            // Body / mind whispers — honest empty states
            VStack(alignment: .leading, spacing: 18) {
                BodyWhisper(
                    title: "body",
                    line: "no readings yet. once your watch syncs, i'll know.",
                    meta: nil,
                    hue: .amber
                )
                BodyWhisper(
                    title: "mind",
                    line: "the band isn't paired yet.",
                    meta: nil,
                    hue: .cool
                )
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.top, 22)
            .padding(.bottom, 8)

            Spacer(minLength: 4)

            // Micro-states row — honest empty states
            HStack(alignment: .top, spacing: 18) {
                MicroState(
                    label: "focus",
                    value: "—",
                    viz: AnyView(RingViz(value: 0, hue: .cool)),
                    dimmed: true
                )
                MicroState(
                    label: "next",
                    value: "calendar not connected",
                    viz: AnyView(
                        ZStack {
                            RoundedRectangle(cornerRadius: 6, style: .continuous)
                                .strokeBorder(Theme.pearl.opacity(0.25), lineWidth: 0.5)
                                .frame(width: 22, height: 22)
                        }
                    ),
                    dimmed: true
                )
                MicroState(
                    label: "playing",
                    value: "nothing yet",
                    viz: AnyView(EqViz(playing: false)),
                    dimmed: true
                )
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 18)
            .padding(.horizontal, 4)
            .overlay(alignment: .top) {
                Rectangle().fill(Theme.pearl.opacity(0.08)).frame(height: 0.5)
            }
            .overlay(alignment: .bottom) {
                Rectangle().fill(Theme.pearl.opacity(0.08)).frame(height: 0.5)
            }

            // Talk affordance
            TalkAffordance(onTap: onTalk)
                .padding(.top, 22)
        }
        .padding(.horizontal, 28)
        .padding(.top, 118)
        .padding(.bottom, 30)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
    }
}

// MARK: - Atoms used inside NowRoom

enum WhisperHue { case amber, cool, green }

struct BodyWhisper: View {
    var title: String
    var line: String
    var meta: String?
    var hue: WhisperHue

    private var accent: Color {
        switch hue {
        case .amber: return Theme.amber
        case .cool:  return Color(red: 0x86 / 255.0, green: 0xB3 / 255.0, blue: 0xD6 / 255.0)
        case .green: return Color(red: 0xA0 / 255.0, green: 0xCC / 255.0, blue: 0x95 / 255.0)
        }
    }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Circle()
                .fill(accent)
                .frame(width: 6, height: 6)
                .shadow(color: accent, radius: 5, x: 0, y: 0)
                .padding(.top, 7)
            VStack(alignment: .leading, spacing: 4) {
                Text(title.uppercased()).labelTiny()
                Text(line)
                    .font(Fonts.body(16))
                    .tracking(-0.2)
                    .foregroundStyle(Theme.pearl)
                    .multilineTextAlignment(.leading)
                if let meta = meta {
                    Text(meta).labelMono()
                }
            }
            Spacer(minLength: 0)
        }
    }
}

struct MicroState: View {
    var label: String
    var value: String
    var viz: AnyView
    var dimmed: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            viz
                .frame(height: 28)
                .frame(maxWidth: .infinity, alignment: .leading)
            Text(label).labelTiny()
            Text(value)
                .font(Fonts.body(13))
                .foregroundStyle(Theme.pearlDim)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .opacity(dimmed ? 0.55 : 1.0)
    }
}

enum RingHue { case amber, cool }
struct RingViz: View {
    var value: Double            // 0..1
    var hue: RingHue
    var size: CGFloat = 26

    private var color: Color {
        switch hue {
        case .amber: return Theme.amber
        case .cool:  return Color(red: 0x86 / 255.0, green: 0xB3 / 255.0, blue: 0xD6 / 255.0)
        }
    }

    var body: some View {
        ZStack {
            Circle()
                .strokeBorder(Theme.pearl.opacity(0.12), lineWidth: 2)
            Circle()
                .trim(from: 0, to: value)
                .stroke(color, style: StrokeStyle(lineWidth: 2, lineCap: .round))
                .shadow(color: color.opacity(0.6), radius: 3, x: 0, y: 0)
                .rotationEffect(.degrees(-90))
        }
        .frame(width: size, height: size)
    }
}

struct EqViz: View {
    var playing: Bool
    @State private var animate = false
    var body: some View {
        if playing {
            HStack(alignment: .bottom, spacing: 3) {
                ForEach(0..<3, id: \.self) { i in
                    let h: CGFloat = [11, 22, 15][i]
                    Capsule()
                        .fill(Theme.green)
                        .frame(width: 3, height: animate ? h : h * 0.6)
                        .animation(
                            .easeInOut(duration: 1.2 + Double(i) * 0.3).repeatForever(autoreverses: true).delay(Double(i) * 0.15),
                            value: animate
                        )
                }
            }
            .frame(height: 22, alignment: .bottom)
            .onAppear { animate = true }
        } else {
            // empty-state dashed circle
            Circle()
                .strokeBorder(style: StrokeStyle(lineWidth: 0.5, dash: [3, 3]))
                .foregroundStyle(Theme.pearl.opacity(0.2))
                .frame(width: 22, height: 22)
        }
    }
}

struct TalkAffordance: View {
    var onTap: () -> Void
    @State private var pulse = false
    var body: some View {
        Button(action: onTap) {
            HStack {
                HStack(spacing: 12) {
                    Circle()
                        .fill(Theme.amber)
                        .frame(width: 10, height: 10)
                        .shadow(color: Theme.amberGlow, radius: 5, x: 0, y: 0)
                        .scaleEffect(pulse ? 1.12 : 1.0)
                        .animation(.easeInOut(duration: 2.4).repeatForever(autoreverses: true), value: pulse)
                    Text("say something to regis")
                        .font(Fonts.body(15))
                        .foregroundStyle(Theme.pearlDim)
                }
                Spacer()
                // waveform glyph
                HStack(spacing: 2) {
                    let bars: [CGFloat] = [6, 11, 16, 11, 6, 9, 14]
                    ForEach(0..<bars.count, id: \.self) { i in
                        Capsule().fill(Theme.pearl.opacity(0.42))
                            .frame(width: 2, height: bars[i])
                    }
                }
                .frame(height: 18, alignment: .center)
            }
            .padding(.horizontal, 22)
            .frame(height: 58)
            .background(TalkPillBackground())
        }
        .buttonStyle(.plain)
        .onAppear { pulse = true }
    }
}
