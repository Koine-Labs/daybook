import SwiftUI

// TodayView — port of ScreenToday from screens-companion.jsx.
// Placeholder data throughout. When the FastAPI bridge lands (apps/api/),
// replace the hardcoded values with APIClient calls in a .task modifier.
struct TodayView: View {
    @Environment(Theme.self) private var theme

    @State private var intent: String = "walk the long way home"

    var body: some View {
        ZStack {
            theme.bg.ignoresSafeArea()

            VStack(spacing: 0) {
                ScreenHead(
                    sub: "tuesday · 17 may",
                    wispState: .dormant,
                    showWisp: true
                )

                ScrollView {
                    VStack(alignment: .leading, spacing: Spacing.md) {
                        greeting
                            .padding(.top, 18)

                        intentCard
                        heldFromLastNight
                        shapeOfToday
                        recallTrend

                        Text("\"I'll be quiet until you ask, or until tonight.\"")
                            .regisVoice(theme.voice, size: 14)
                            .opacity(0.7)
                            .frame(maxWidth: .infinity, alignment: .center)
                            .padding(.top, 26)
                            .padding(.bottom, 16)
                    }
                    .padding(.horizontal, 24)
                    .padding(.top, 12)
                    .padding(.bottom, 100)
                }
            }
        }
    }

    // MARK: - Sections

    private var greeting: some View {
        Text("Afternoon.")
            .dbHeadlineLarge(theme.ink)
    }

    private var intentCard: some View {
        card {
            VStack(alignment: .leading, spacing: 0) {
                Text("intent for today")
                    .dbEyebrow(theme.ink3)
                    .padding(.bottom, 8)

                TextField("", text: $intent, axis: .vertical)
                    .font(DBFont.serif(26))
                    .tracking(-0.13)
                    .foregroundStyle(theme.ink)
                    .textFieldStyle(.plain)
                    .tint(theme.amber)
                    .lineLimit(1...3)

                Divider()
                    .background(theme.edge)
                    .padding(.top, 12)

                HStack {
                    Text("set 09:14 · 3 quiet hours blocked")
                        .dbMeta(theme.ink3)
                    Spacer()
                    chipView("today")
                }
                .padding(.top, 12)
            }
        }
    }

    private var heldFromLastNight: some View {
        card {
            VStack(alignment: .leading, spacing: 0) {
                HStack {
                    Text("held from last night")
                        .dbEyebrow(theme.ink3)
                    Spacer()
                    Text("3 fragments")
                        .dbMeta(theme.ink3)
                }

                VStack(alignment: .leading, spacing: 10) {
                    dreamFragment("a kitchen made of warm tile. someone's mother was there.", faded: false)
                    dreamFragment("walking up a staircase that kept going one more flight.", faded: false)
                    dreamFragment("something about a green field. faded.", faded: true)
                }
                .padding(.top, 10)

                Divider()
                    .background(theme.edge)
                    .padding(.top, 14)

                HStack {
                    Text("recall · 14 of last 14 nights")
                        .dbMeta(theme.ink3)
                    Spacer()
                    Text("archive →")
                        .dbMeta(theme.amber)
                }
                .padding(.top, 12)
            }
        }
    }

    private func dreamFragment(_ text: String, faded: Bool) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Text("·")
                .font(DBFont.serif(22))
                .foregroundStyle(theme.amberSoft)
                .frame(width: 14, alignment: .leading)

            Text(text)
                .font(DBFont.serif(17, italic: faded))
                .foregroundStyle(faded ? theme.ink2 : theme.ink)
                .lineSpacing(17 * 0.3)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private struct ScheduleRow {
        let time: String
        let label: String
        let meta: String
        let accent: Bool
    }

    private let scheduleRows: [ScheduleRow] = [
        .init(time: "11:30", label: "standup", meta: "short", accent: false),
        .init(time: "14:00", label: "call with kabir", meta: "90 min", accent: false),
        .init(time: "16:30", label: "walk · long way", meta: "intent", accent: true),
        .init(time: "19:00", label: "dinner — dad", meta: "", accent: false),
        .init(time: "22:30", label: "threshold", meta: "regis arms", accent: true)
    ]

    private var shapeOfToday: some View {
        card {
            VStack(alignment: .leading, spacing: 0) {
                HStack {
                    Text("the shape of today")
                        .dbEyebrow(theme.ink3)
                    Spacer()
                    Text("5 things")
                        .dbMeta(theme.ink3)
                }
                .padding(.bottom, 12)

                ForEach(Array(scheduleRows.enumerated()), id: \.offset) { index, row in
                    if index > 0 {
                        Divider().background(theme.edge)
                    }
                    HStack(alignment: .firstTextBaseline, spacing: 10) {
                        Text(row.time)
                            .dbMeta(row.accent ? theme.amber : theme.ink3)
                            .frame(width: 46, alignment: .leading)

                        Text(row.label)
                            .font(DBFont.sans(15, weight: row.accent ? .medium : .regular))
                            .foregroundStyle(theme.ink)
                            .frame(maxWidth: .infinity, alignment: .leading)

                        Text(row.meta)
                            .dbMeta(row.accent ? theme.amber : theme.ink3)
                    }
                    .padding(.vertical, 8)
                }
            }
        }
    }

    private let sparkline: [Double] = [
        0.4, 0.2, 0.5, 0.0, 0.3, 0.7, 0.8, 0.6, 0.9, 0.7, 1.0, 0.8, 1.0, 0.95
    ]

    private var recallTrend: some View {
        card {
            VStack(alignment: .leading, spacing: 0) {
                HStack(alignment: .firstTextBaseline) {
                    Text("recall, last 14 nights")
                        .dbEyebrow(theme.ink3)
                    Spacer()
                    HStack(alignment: .lastTextBaseline, spacing: 4) {
                        Text("+62")
                            .font(DBFont.serif(28))
                            .foregroundStyle(theme.ink)
                        Text("% vs baseline")
                            .font(DBFont.sans(14))
                            .foregroundStyle(theme.ink2)
                    }
                }

                HStack(alignment: .bottom, spacing: 2) {
                    ForEach(Array(sparkline.enumerated()), id: \.offset) { _, value in
                        RoundedRectangle(cornerRadius: 1)
                            .fill(theme.amber.opacity(0.45 + value * 0.45))
                            .frame(width: 6, height: max(8, 36 * value))
                    }
                }
                .frame(height: 36, alignment: .bottom)
                .padding(.top, 14)

                HStack {
                    Text("2 may")
                        .dbMeta(theme.ink3)
                    Spacer()
                    Text("today")
                        .dbMeta(theme.ink3)
                }
                .padding(.top, 8)
            }
        }
    }

    // MARK: - Building blocks

    @ViewBuilder
    private func card<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        content()
            .padding(.horizontal, 18)
            .padding(.vertical, 16)
            .background(
                RoundedRectangle(cornerRadius: Radius.card, style: .continuous)
                    .fill(theme.card)
                    .overlay(
                        RoundedRectangle(cornerRadius: Radius.card, style: .continuous)
                            .stroke(theme.edge, lineWidth: 0.5)
                    )
            )
    }

    private func chipView(_ label: String) -> some View {
        Text(label)
            .font(DBFont.sans(11.5, weight: .medium))
            .tracking(0.12)
            .foregroundStyle(theme.ink2)
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(
                Capsule().fill(Color.black.opacity(0.04))
            )
            .overlay(
                Capsule().stroke(theme.edge, lineWidth: 0.5)
            )
    }
}

#Preview {
    let theme = Theme()
    return TodayView()
        .environment(theme)
}
