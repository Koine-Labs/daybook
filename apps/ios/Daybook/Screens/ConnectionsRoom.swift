import SwiftUI

// ConnectionsRoom — devices, integrations, Regis tuning, permissions.

struct ConnectionsRoom: View {
    var tweaks: Tweaks

    @State private var proactivity: Double = 0.5
    @State private var warmth: Double = 0.5
    @State private var reach: Double = 0.5

    var body: some View {
        ScrollView(showsIndicators: false) {
            VStack(alignment: .leading, spacing: 0) {
                // Header
                VStack(alignment: .leading, spacing: 4) {
                    Text("connections").labelTiny()
                    Text("what regis can sense")
                        .font(Fonts.body(22, .medium))
                        .tracking(-0.4)
                        .foregroundStyle(Theme.pearl)
                }
                .padding(.bottom, 22)

                // BCI hero
                BCIHero(tweaks: tweaks)
                    .padding(.bottom, 28)

                // Wearables — all not connected
                VStack(alignment: .leading, spacing: 14) {
                    SectionHeader(title: "also listening")
                    VStack(spacing: 0) {
                        ConnectionRow(icon: "⌚", name: "apple watch",
                                      status: "not connected",
                                      accent: Theme.inkLight, active: false)
                        ConnectionRow(icon: "W", name: "whoop 4.0",
                                      status: "not connected",
                                      accent: Color(red: 0xC8 / 255.0, green: 0x4C / 255.0, blue: 0x2B / 255.0),
                                      active: false)
                        ConnectionRow(icon: "○", name: "oura ring",
                                      status: "not connected",
                                      accent: Color(red: 0x6A / 255.0, green: 0x5E / 255.0, blue: 0x3F / 255.0),
                                      active: false)
                    }
                }
                .padding(.bottom, 28)

                // Apps — all not connected
                VStack(alignment: .leading, spacing: 14) {
                    SectionHeader(title: "your life, plugged in")
                    VStack(spacing: 0) {
                        ConnectionRow(icon: "♪", name: "spotify",
                                      status: "not connected",
                                      accent: Theme.green, active: false)
                        ConnectionRow(icon: "◷", name: "apple calendar",
                                      status: "not connected",
                                      accent: Color(red: 0xCB / 255.0, green: 0x4B / 255.0, blue: 0x35 / 255.0),
                                      active: false)
                        ConnectionRow(icon: "✎", name: "notes",
                                      status: "not connected",
                                      accent: Color(red: 0xCB / 255.0, green: 0xAB / 255.0, blue: 0x4B / 255.0),
                                      active: false)
                    }
                }
                .padding(.bottom, 28)

                // Tuning
                VStack(alignment: .leading, spacing: 14) {
                    SectionHeader(title: "tuning", meta: "how regis shows up")
                    VStack(spacing: 0) {
                        TuneSlider(label: "proactivity",
                                   leftLabel: "quiet", rightLabel: "forward",
                                   value: $proactivity)
                        TuneSlider(label: "warmth",
                                   leftLabel: "cool", rightLabel: "affectionate",
                                   value: $warmth)
                        TuneSlider(label: "reach",
                                   leftLabel: "just here", rightLabel: "everywhere",
                                   value: $reach)
                    }
                    .padding(.horizontal, 18)
                    .padding(.vertical, 4)
                    .glassPanel(cornerRadius: 22)
                }
                .padding(.bottom, 28)

                // Permissions — all off until user grants
                VStack(alignment: .leading, spacing: 14) {
                    SectionHeader(title: "what regis can see", meta: "you decide")
                    VStack(spacing: 0) {
                        PermissionRow(label: "biometrics", scope: "hrv · sleep · skin temp", initial: false)
                        PermissionRow(label: "calendar", scope: "titles only · no attendees", initial: false)
                        PermissionRow(label: "location", scope: "home · studio · in-transit", initial: false)
                        PermissionRow(label: "messages", scope: "closed — opt in to share", initial: false)
                        PermissionRow(label: "microphone", scope: "only when you tap to speak", initial: false)
                    }
                    .padding(.horizontal, 4)
                }
                .padding(.bottom, 28)

                // Closing reverent line
                Text("anything you tell me, you can also unmake.")
                    .font(Fonts.quote(12))
                    .multilineTextAlignment(.center)
                    .foregroundStyle(Theme.pearlFaint)
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.horizontal, 20)
            }
            .padding(.horizontal, 28)
            .padding(.top, 112)
            .padding(.bottom, 40)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

// MARK: - BCIHero

struct BCIHero: View {
    var tweaks: Tweaks
    @State private var shimmer = false

    var body: some View {
        VStack(spacing: 0) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("your wearable").labelTiny()
                    Text("koine band")
                        .font(Fonts.body(21, .medium))
                        .tracking(-0.3)
                        .foregroundStyle(Theme.pearl)
                    Text("not paired yet")
                        .font(Fonts.body(13))
                        .foregroundStyle(Theme.pearlDim)
                        .padding(.top, 2)
                }
                Spacer()
                RegisView(size: 56, mood: .calm, hrv: 1.1, form: .orb)
            }
            .padding(.bottom, 18)

            Divider().background(Theme.pearl.opacity(0.08))

            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("—").labelTiny()
                    Text("searching")
                        .font(Fonts.body(14))
                        .foregroundStyle(Theme.pearlDim)
                }
                Spacer()
                SignalBars(strength: 0.0)
            }
            .padding(.top, 14)
            .padding(.bottom, 4)
        }
        .padding(.horizontal, 24)
        .padding(.top, 22)
        .padding(.bottom, 24)
        .glassPanel(cornerRadius: 28)
    }
}

struct SignalBars: View {
    var strength: Double
    @State private var animate = false
    var body: some View {
        let bars = 12
        HStack(alignment: .bottom, spacing: 3) {
            ForEach(0..<bars, id: \.self) { i in
                let filled = Double(i) / Double(bars) < strength
                let h: CGFloat = 8 + (CGFloat(i) / CGFloat(bars)) * 20
                Capsule()
                    .fill(filled ? Theme.amber : Theme.pearl.opacity(0.12))
                    .frame(width: 3, height: h)
                    .shadow(color: filled ? Theme.amberGlow : .clear, radius: 3, x: 0, y: 0)
                    .opacity(filled ? (animate ? 1.0 : 0.55) : 1.0)
                    .animation(
                        filled
                          ? .easeInOut(duration: 2 + Double(i % 4) * 0.3).repeatForever(autoreverses: true).delay(Double(i) * 0.08)
                          : .default,
                        value: animate
                    )
            }
        }
        .frame(height: 28, alignment: .bottom)
        .onAppear { animate = true }
    }
}

// MARK: - ConnectionRow

struct ConnectionRow: View {
    var icon: String
    var name: String
    var status: String
    var accent: Color
    var active: Bool

    var body: some View {
        HStack(spacing: 14) {
            // Icon tile
            RoundedRectangle(cornerRadius: 11, style: .continuous)
                .fill(
                    active
                    ? AnyShapeStyle(LinearGradient(colors: [accent, accent.opacity(0.7)],
                                                   startPoint: .topLeading, endPoint: .bottomTrailing))
                    : AnyShapeStyle(Theme.pearl.opacity(0.05))
                )
                .overlay(
                    // Use default system design (not rounded) so unicode glyphs
                    // like ⌚ and ◷ render — they're missing from SF Rounded.
                    Text(icon)
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundStyle(active ? Theme.bgBase : Theme.pearlFaint)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 11, style: .continuous)
                        .strokeBorder(
                            Theme.pearl.opacity(0.15),
                            style: StrokeStyle(lineWidth: active ? 0 : 0.5, dash: active ? [] : [3, 3])
                        )
                )
                .frame(width: 38, height: 38)
                .shadow(color: active ? accent.opacity(0.35) : .clear, radius: 8, x: 0, y: 4)

            // Name + status
            VStack(alignment: .leading, spacing: 2) {
                Text(name)
                    .font(Fonts.body(15, .medium))
                    .tracking(-0.1)
                    .foregroundStyle(active ? Theme.pearl : Theme.pearlDim)
                Text(status).labelMono()
            }

            Spacer()

            // Trailing indicator / action
            if active {
                Circle()
                    .fill(Theme.green)
                    .frame(width: 6, height: 6)
                    .shadow(color: Theme.green.opacity(0.6), radius: 4, x: 0, y: 0)
            } else {
                Text("connect")
                    .font(Fonts.body(12))
                    .foregroundStyle(Theme.amber)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .background(
                        Capsule().fill(Theme.amber.opacity(0.06))
                    )
                    .overlay(
                        Capsule().strokeBorder(Theme.amber.opacity(0.3), lineWidth: 0.5)
                    )
            }
        }
        .padding(.vertical, 14)
        .padding(.horizontal, 4)
        .overlay(alignment: .bottom) {
            Rectangle().fill(Theme.pearl.opacity(0.06)).frame(height: 0.5)
        }
    }
}

// MARK: - TuneSlider

struct TuneSlider: View {
    var label: String
    var leftLabel: String
    var rightLabel: String
    @Binding var value: Double

    private var stateLabel: String {
        value < 0.33 ? leftLabel : (value > 0.66 ? rightLabel : "in-between")
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .firstTextBaseline) {
                Text(label.uppercased())
                    .labelTiny()
                Spacer()
                Text(stateLabel).labelMono(Theme.pearlFaint, size: 10)
            }
            .padding(.bottom, 12)

            ZStack(alignment: .leading) {
                // Track
                Capsule().fill(Theme.pearl.opacity(0.10))
                    .frame(height: 2)

                // Filled portion
                GeometryReader { geo in
                    Capsule()
                        .fill(
                            LinearGradient(colors: [Theme.amber.opacity(0.4), Theme.amber],
                                           startPoint: .leading, endPoint: .trailing)
                        )
                        .frame(width: geo.size.width * CGFloat(value), height: 2)
                        .shadow(color: Theme.amberGlow.opacity(0.5), radius: 4, x: 0, y: 0)
                }
                .frame(height: 2)

                // Handle + invisible slider for hit testing
                GeometryReader { geo in
                    Circle()
                        .fill(
                            RadialGradient(
                                colors: [Color(red: 1.0, green: 246/255.0, blue: 226/255.0), Theme.amber],
                                center: UnitPoint(x: 0.38, y: 0.32), startRadius: 0, endRadius: 8
                            )
                        )
                        .frame(width: 16, height: 16)
                        .shadow(color: Theme.amberGlow, radius: 6, x: 0, y: 0)
                        .shadow(color: .black.opacity(0.4), radius: 3, x: 0, y: 2)
                        .position(x: geo.size.width * CGFloat(value), y: geo.size.height / 2)
                        .gesture(
                            DragGesture(minimumDistance: 0).onChanged { dragValue in
                                let frac = max(0, min(1, dragValue.location.x / geo.size.width))
                                value = Double(frac)
                            }
                        )
                }
                .frame(height: 24)
            }
            .frame(height: 24)
            .contentShape(Rectangle())

            HStack {
                Text(leftLabel)
                Spacer()
                Text(rightLabel)
            }
            .font(Fonts.mono(11))
            .foregroundStyle(Theme.pearlFaint)
            .tracking(0.2)
            .padding(.top, 8)
        }
        .padding(.vertical, 14)
        .padding(.horizontal, 4)
    }
}

// MARK: - PermissionRow

struct PermissionRow: View {
    var label: String
    var scope: String
    var initial: Bool

    @State private var on: Bool

    init(label: String, scope: String, initial: Bool) {
        self.label = label; self.scope = scope; self.initial = initial
        _on = State(initialValue: initial)
    }

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(label)
                    .font(Fonts.body(14, .medium))
                    .foregroundStyle(Theme.pearl)
                Text(scope).labelMono()
            }
            Spacer()

            // Custom amber toggle
            Button(action: { withAnimation(.easeInOut(duration: 0.24)) { on.toggle() } }) {
                ZStack(alignment: on ? .trailing : .leading) {
                    Capsule()
                        .fill(
                            on
                            ? AnyShapeStyle(LinearGradient(colors: [Theme.amber, Theme.amberDeep],
                                                          startPoint: .topLeading, endPoint: .bottomTrailing))
                            : AnyShapeStyle(Theme.pearl.opacity(0.12))
                        )
                        .frame(width: 36, height: 22)
                        .shadow(color: on ? Theme.amberGlow.opacity(0.8) : .clear, radius: 5, x: 0, y: 0)
                    Circle()
                        .fill(Color(red: 1.0, green: 246/255.0, blue: 232/255.0))
                        .frame(width: 18, height: 18)
                        .shadow(color: .black.opacity(0.3), radius: 1, x: 0, y: 1)
                        .padding(2)
                }
                .frame(width: 36, height: 22)
            }
            .buttonStyle(.plain)
        }
        .padding(.vertical, 12)
        .overlay(alignment: .bottom) {
            Rectangle().fill(Theme.pearl.opacity(0.06)).frame(height: 0.5)
        }
    }
}
