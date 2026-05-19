import SwiftUI

// SelfRoom — your evolving picture. Long-form portrait + body aurora + theme
// constellation + memory threads + honest empty state for dreams.

struct SelfRoom: View {
    var tweaks: Tweaks

    var body: some View {
        ScrollView(showsIndicators: false) {
            VStack(alignment: .leading, spacing: 0) {
                // Header — small Regis PNG + label
                HStack(spacing: 14) {
                    RegisView(size: 56, mood: tweaks.mood, hrv: tweaks.hrv, form: .png)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("self").labelTiny()
                        Text("who you've been")
                            .font(Fonts.body(22, .medium))
                            .tracking(-0.4)
                            .foregroundStyle(Theme.pearl)
                    }
                }
                .padding(.bottom, 28)

                // Portrait — honest empty state
                VStack(alignment: .leading, spacing: 14) {
                    SectionHeader(title: "a portrait, today", meta: "empty")
                    Text("i don't know you yet. give it a few days — i'm listening.")
                        .font(Fonts.quote(18).italic())
                        .lineSpacing(6)
                        .foregroundStyle(Theme.amberPortrait)
                }
                .padding(.bottom, 32)

                // Body aurora — honest empty meta
                VStack(alignment: .leading, spacing: 14) {
                    SectionHeader(title: "body, lately", meta: "not connected")
                    BodyAurora()
                }
                .padding(.bottom, 32)

                // Themes — honest empty state
                VStack(alignment: .leading, spacing: 14) {
                    SectionHeader(title: "what keeps surfacing", meta: "empty")
                    Text("nothing's repeated yet. i'll notice patterns as they form.")
                        .font(Fonts.quote(16).italic())
                        .lineSpacing(4)
                        .foregroundStyle(Theme.pearlDim)
                        .padding(.vertical, 8)
                }
                .padding(.bottom, 32)

                // Memory threads — honest empty state
                VStack(alignment: .leading, spacing: 14) {
                    SectionHeader(title: "moments regis kept", meta: "empty")
                    Text("i haven't held anything yet. soon.")
                        .font(Fonts.quote(16).italic())
                        .lineSpacing(4)
                        .foregroundStyle(Theme.pearlDim)
                        .padding(.vertical, 8)
                }
                .padding(.bottom, 32)

                // Dreams — empty state
                VStack(alignment: .leading, spacing: 14) {
                    SectionHeader(title: "dreams", meta: "empty")
                    VStack(alignment: .leading, spacing: 14) {
                        Text("""
                        you haven't told me any yet. mornings, while you're still soft, \
                        you can speak one and i'll keep it.
                        """)
                            .font(Fonts.quote(16))
                            .lineSpacing(4)
                            .foregroundStyle(Theme.pearlDim)
                        Text("tell regis a dream →")
                            .font(Fonts.body(13))
                            .foregroundStyle(Theme.amber)
                    }
                    .padding(22)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(
                        RoundedRectangle(cornerRadius: 22, style: .continuous)
                            .fill(Theme.pearl.opacity(0.025))
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 22, style: .continuous)
                            .strokeBorder(
                                Theme.pearl.opacity(0.16),
                                style: StrokeStyle(lineWidth: 0.5, dash: [3, 3])
                            )
                    )
                }
                .padding(.bottom, 16)
            }
            .padding(.horizontal, 28)
            .padding(.top, 112)
            .padding(.bottom, 40)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

// MARK: - BodyAurora

struct BodyAurora: View {
    @State private var shift = false
    var body: some View {
        ZStack {
            // base ink
            RoundedRectangle(cornerRadius: 22, style: .continuous)
                .fill(
                    LinearGradient(
                        colors: [Color(red: 10/255.0, green: 14/255.0, blue: 30/255.0).opacity(0.4),
                                 Color(red: 8/255.0,  green: 10/255.0, blue: 22/255.0).opacity(0.6)],
                        startPoint: .top, endPoint: .bottom
                    )
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 22, style: .continuous)
                        .strokeBorder(Color(red: 1.0, green: 230/255.0, blue: 200/255.0).opacity(0.14), lineWidth: 0.5)
                )

            // Aurora bands
            ZStack {
                AuroraBand(
                    color: Theme.amber.opacity(0.5),
                    center: UnitPoint(x: 0.30, y: 0.60),
                    radius: 200, dx: shift ? -12 : 10, dy: shift ? -10 : -16, rotation: shift ? 0.6 : -0.5
                )
                .animation(.easeInOut(duration: 14).repeatForever(autoreverses: true), value: shift)

                AuroraBand(
                    color: Color(red: 0xE0 / 255.0, green: 0x6A / 255.0, blue: 0x39 / 255.0).opacity(0.45),
                    center: UnitPoint(x: 0.70, y: 0.40),
                    radius: 200, dx: shift ? 10 : -12, dy: shift ? -16 : -10, rotation: shift ? -0.5 : 0.6
                )
                .animation(.easeInOut(duration: 17).delay(0.5).repeatForever(autoreverses: true), value: shift)

                AuroraBand(
                    color: Color(red: 0x88 / 255.0, green: 0xC3 / 255.0, blue: 0xE6 / 255.0).opacity(0.4),
                    center: UnitPoint(x: 0.50, y: 0.80),
                    radius: 200, dx: shift ? -8 : 12, dy: shift ? 6 : -10, rotation: shift ? 0.3 : -0.3
                )
                .animation(.easeInOut(duration: 19).delay(0.9).repeatForever(autoreverses: true), value: shift)
            }
            .blur(radius: 14)
            .mask(RoundedRectangle(cornerRadius: 22, style: .continuous))

            // Tiny "now" star
            GeometryReader { geo in
                Circle()
                    .fill(Color(red: 1.0, green: 241/255.0, blue: 214/255.0))
                    .frame(width: 6, height: 6)
                    .shadow(color: Color(red: 1.0, green: 224/255.0, blue: 166/255.0), radius: 6, x: 0, y: 0)
                    .shadow(color: Color(red: 1.0, green: 200/255.0, blue: 130/255.0).opacity(0.5), radius: 12, x: 0, y: 0)
                    .position(x: geo.size.width * 0.78, y: geo.size.height * 0.38)
            }

            // Captions
            HStack {
                Text("seven days · body").labelTiny()
                Spacer()
                Text("no readings yet").labelMono(Theme.pearl.opacity(0.55), size: 10)
            }
            .padding(.top, 12)
            .padding(.horizontal, 16)
            .frame(maxHeight: .infinity, alignment: .top)

            // Timeline track
            HStack {
                let days = ["fri", "sat", "sun", "mon", "tue", "wed", "today"]
                ForEach(0..<days.count, id: \.self) { i in
                    VStack(spacing: 4) {
                        Circle()
                            .fill(i == 6 ? Theme.amber : Theme.pearl.opacity(0.35))
                            .frame(width: 2, height: 2)
                            .shadow(color: i == 6 ? Theme.amberGlow : .clear, radius: 3, x: 0, y: 0)
                        Text(days[i])
                            .font(Fonts.mono(9))
                            .tracking(0.9)
                            .foregroundStyle(i == 6 ? Theme.pearl : Theme.pearl.opacity(0.32))
                    }
                    .frame(maxWidth: .infinity)
                }
            }
            .padding(.horizontal, 18)
            .padding(.bottom, 8)
            .frame(maxHeight: .infinity, alignment: .bottom)

            // Inset top shine
            RoundedRectangle(cornerRadius: 22, style: .continuous)
                .stroke(
                    LinearGradient(colors: [Theme.pearl.opacity(0.18), .clear], startPoint: .top, endPoint: .center),
                    lineWidth: 0.8
                )
                .blendMode(.plusLighter)
                .allowsHitTesting(false)
        }
        .frame(height: 168)
        .onAppear { shift = true }
    }
}

private struct AuroraBand: View {
    var color: Color
    var center: UnitPoint
    var radius: CGFloat
    var dx: CGFloat
    var dy: CGFloat
    var rotation: Double
    var body: some View {
        GeometryReader { geo in
            Circle()
                .fill(
                    RadialGradient(colors: [color, .clear], center: .center, startRadius: 0, endRadius: radius)
                )
                .frame(width: radius * 2, height: radius * 2)
                .position(x: center.x * geo.size.width + dx, y: center.y * geo.size.height + dy)
                .rotationEffect(.degrees(rotation))
        }
    }
}

// MARK: - MemoryThread

struct MemoryThread: View {
    var when: String
    var hue: Double            // 0..360 hue-ish, used to choose color
    var line: String

    private var hueColor: Color {
        // 28 ≈ red-orange, 65 ≈ amber, 145 ≈ green
        if hue < 50 { return Color(red: 0xE6 / 255.0, green: 0x84 / 255.0, blue: 0x45 / 255.0) }
        if hue < 100 { return Theme.amber }
        return Color(red: 0x83 / 255.0, green: 0xC8 / 255.0, blue: 0x9A / 255.0)
    }

    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            Circle()
                .fill(
                    RadialGradient(
                        colors: [
                            Color(red: 1.0, green: 250/255.0, blue: 232/255.0),
                            hueColor,
                            hueColor.opacity(0.5)
                        ],
                        center: UnitPoint(x: 0.38, y: 0.32),
                        startRadius: 0, endRadius: 16
                    )
                )
                .frame(width: 28, height: 28)
                .shadow(color: hueColor.opacity(0.55), radius: 7, x: 0, y: 0)

            VStack(alignment: .leading, spacing: 4) {
                Text(when).labelMono()
                Text(line)
                    .font(Fonts.quote(16))
                    .lineSpacing(4)
                    .foregroundStyle(Theme.amberQuote)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(.top, 2)
        }
        .padding(.vertical, 14)
    }
}

// MARK: - Theme word constellation

struct ThemeWord: Identifiable {
    let id = UUID()
    let word: String
    let size: CGFloat
    let dim: Bool
    init(_ word: String, size: CGFloat, dim: Bool) {
        self.word = word; self.size = size; self.dim = dim
    }
}

struct ThemeFlow: View {
    var themes: [ThemeWord]
    var body: some View {
        FlowLayout(spacingX: 18, spacingY: 14) {
            ForEach(themes) { t in
                Text(t.word)
                    .font(Fonts.body(t.size, .medium))
                    .tracking(-0.3)
                    .foregroundStyle(t.dim ? Theme.pearl.opacity(0.32) : Color(red: 1.0, green: 0xE5 / 255.0, blue: 0xBD / 255.0))
                    .shadow(color: t.dim ? .clear : Theme.amber.opacity(0.5), radius: t.size * 0.4, x: 0, y: 0)
                    .fixedSize()
            }
        }
    }
}

// Simple flow / wrap layout (used for theme word cloud).
struct FlowLayout: Layout {
    var spacingX: CGFloat = 8
    var spacingY: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let maxW = proposal.width ?? .infinity
        var x: CGFloat = 0
        var y: CGFloat = 0
        var rowHeight: CGFloat = 0
        var totalW: CGFloat = 0
        for sv in subviews {
            let s = sv.sizeThatFits(.unspecified)
            if x + s.width > maxW {
                x = 0
                y += rowHeight + spacingY
                rowHeight = 0
            }
            x += s.width + spacingX
            rowHeight = max(rowHeight, s.height)
            totalW = max(totalW, x)
        }
        return CGSize(width: totalW, height: y + rowHeight)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x: CGFloat = bounds.minX
        var y: CGFloat = bounds.minY
        var rowHeight: CGFloat = 0
        for sv in subviews {
            let s = sv.sizeThatFits(.unspecified)
            if x + s.width > bounds.maxX {
                x = bounds.minX
                y += rowHeight + spacingY
                rowHeight = 0
            }
            sv.place(at: CGPoint(x: x, y: y), proposal: .init(s))
            x += s.width + spacingX
            rowHeight = max(rowHeight, s.height)
        }
    }
}
