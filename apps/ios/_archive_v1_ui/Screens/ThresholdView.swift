import SwiftUI

// ThresholdView — pre-sleep wind-down + intent-setting moment.
// Port of ScreenThreshold from screens-witness.jsx. Transit mode:
// between companion (paper, awake) and witness (navy, sleeping).
// TODO: wire intent persistence to apps/api/ via APIClient.
// TODO: tonight's cue plan should come from the real scheduler.
struct ThresholdView: View {
    @Environment(Theme.self) private var theme

    @State private var intent: String = "ocean"
    @State private var armed: Bool = false
    @State private var appeared: Bool = false

    var body: some View {
        ZStack {
            background
                .ignoresSafeArea()

            StarfieldView()
                .opacity(armed ? 1.0 : 0.4)
                .animation(.easeInOut(duration: 1.2), value: armed)
                .allowsHitTesting(false)

            VStack(alignment: .leading, spacing: 0) {
                header
                    .padding(.horizontal, 24)
                    .padding(.top, 54)

                content
                    .padding(.horizontal, 28)
                    .padding(.top, 40)
                    .padding(.bottom, 110)
            }
        }
        .opacity(appeared ? 1.0 : 0.0)
        .onAppear {
            withAnimation(.easeOut(duration: 0.6)) { appeared = true }
        }
    }

    // MARK: - Background

    private var background: some View {
        Group {
            if armed {
                RadialGradient(
                    gradient: Gradient(stops: [
                        .init(color: Color(hex: "131a2a"), location: 0.0),
                        .init(color: Color(hex: "0a0e1a"), location: 0.65),
                        .init(color: Color(hex: "07090f"), location: 1.0)
                    ]),
                    center: UnitPoint(x: 0.5, y: 0.3),
                    startRadius: 0,
                    endRadius: 600
                )
            } else {
                LinearGradient(
                    gradient: Gradient(stops: [
                        .init(color: Color(hex: "1a1d2a"), location: 0.0),
                        .init(color: Color(hex: "0f1320"), location: 0.4),
                        .init(color: Color(hex: "0a0e1a"), location: 1.0)
                    ]),
                    startPoint: .top,
                    endPoint: .bottom
                )
            }
        }
        .animation(.easeInOut(duration: 1.2), value: armed)
    }

    // MARK: - Header

    private var header: some View {
        HStack(alignment: .center) {
            Text("22:47 · tue · 17 may")
                .dbMeta(Color(red: 232/255, green: 226/255, blue: 212/255, opacity: 0.55))
            Spacer()
            WispView(size: 20, state: armed ? .witnessing : .composing, mode: .witness)
        }
    }

    // MARK: - Content stack

    private var content: some View {
        VStack(alignment: .leading, spacing: 0) {
            heading

            Spacer(minLength: 24)

            intentInput
                .padding(.bottom, 24)

            cuePlanCard
                .padding(.bottom, 18)

            armButton

            armCaption
                .padding(.top, 12)
        }
    }

    private var heading: some View {
        VStack(alignment: .leading, spacing: 22) {
            Text("Threshold.")
                .font(DBFont.serif(64))
                .tracking(-0.64)
                .foregroundStyle(Color(hex: "E8E2D4"))

            HStack(alignment: .top, spacing: 12) {
                WispMark(size: 14, mode: .witness)
                    .padding(.top, 4)

                RegisQuote(
                    armed
                        ? "Settle in. I've got the watch."
                        : "There you are. Lights soon — don't fight it.",
                    size: 22
                )
            }
        }
    }

    // MARK: - Intent input

    private var intentInput: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("one image to carry in")
                .dbEyebrow(Color(red: 232/255, green: 226/255, blue: 212/255, opacity: 0.55))
                .padding(.bottom, 2)

            TextField("", text: $intent)
                .font(DBFont.serif(38, italic: armed))
                .foregroundStyle(Color(hex: "FFCB95"))
                .tint(Color(hex: "FFCB95"))
                .textFieldStyle(.plain)
                .disabled(armed)
                .padding(.bottom, 10)
                .overlay(alignment: .bottom) {
                    Rectangle()
                        .fill(Color(red: 232/255, green: 226/255, blue: 212/255, opacity: 0.2))
                        .frame(height: 0.5)
                }

            Text(armed ? "held." : "Don't make it complicated.")
                .font(DBFont.serif(14, italic: true))
                .foregroundStyle(Color(red: 232/255, green: 226/255, blue: 212/255, opacity: 0.4))
                .padding(.top, 8)
        }
    }

    // MARK: - Cue plan card

    private struct CueRow {
        let time: String
        let cue: String
    }

    private let cueRows: [CueRow] = [
        .init(time: "~01:40", cue: "you are dreaming"),
        .init(time: "~03:10", cue: "notice the color"),
        .init(time: "~04:35", cue: "stay a moment longer"),
        .init(time: "~05:50", cue: "carry it back with you")
    ]

    private var cuePlanCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline) {
                Text("tonight's plan")
                    .dbEyebrow(Color(red: 232/255, green: 226/255, blue: 212/255, opacity: 0.5))
                Spacer()
                Text("4 cues · max")
                    .dbMeta(Color(red: 232/255, green: 226/255, blue: 212/255, opacity: 0.4))
            }
            .padding(.bottom, 4)

            VStack(spacing: 5) {
                ForEach(Array(cueRows.enumerated()), id: \.offset) { _, row in
                    HStack(alignment: .firstTextBaseline) {
                        Text(row.time)
                            .font(DBFont.mono(11))
                            .foregroundStyle(Color(red: 232/255, green: 226/255, blue: 212/255, opacity: 0.5))
                        Spacer()
                        RegisQuote("\"\(row.cue)\"", size: 14)
                    }
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 14)
        .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(Color(red: 232/255, green: 226/255, blue: 212/255, opacity: 0.04))
                .overlay(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .stroke(Color(red: 232/255, green: 226/255, blue: 212/255, opacity: 0.08), lineWidth: 0.5)
                )
        )
    }

    // MARK: - Arm button

    private var armButton: some View {
        Button {
            withAnimation(.easeInOut(duration: 0.25)) { armed.toggle() }
            // TODO: when armed, persist the intent and arm the real cue scheduler.
        } label: {
            ZStack {
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(armButtonFill)
                    .overlay(armButtonStroke)
                    .shadow(
                        color: armed
                            ? .clear
                            : Color(red: 232/255, green: 148/255, blue: 86/255, opacity: 0.35),
                        radius: 30,
                        x: 0,
                        y: 8
                    )

                Text(armed ? "witnessing · tap to disarm" : "begin night")
                    .font(DBFont.serif(22))
                    .tracking(-0.22)
                    .foregroundStyle(armed ? Color(hex: "FFCB95") : Color(hex: "1a0e05"))
            }
            .frame(maxWidth: .infinity)
            .frame(height: 56)
        }
        .buttonStyle(.plain)
    }

    private var armButtonFill: AnyShapeStyle {
        if armed {
            return AnyShapeStyle(Color(red: 232/255, green: 148/255, blue: 86/255, opacity: 0.18))
        }
        return AnyShapeStyle(
            LinearGradient(
                gradient: Gradient(stops: [
                    .init(color: Color(hex: "E89456"), location: 0.0),
                    .init(color: Color(hex: "C97C3A"), location: 1.0)
                ]),
                startPoint: .top,
                endPoint: .bottom
            )
        )
    }

    @ViewBuilder
    private var armButtonStroke: some View {
        if armed {
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(Color(red: 255/255, green: 203/255, blue: 149/255, opacity: 0.4), lineWidth: 0.5)
        }
    }

    private var armCaption: some View {
        HStack {
            Spacer()
            Text(armed
                 ? "I'll be quiet for the next eight hours."
                 : "Try not to think too hard. Last time, it didn't help.")
                .regisVoice(Color(red: 255/255, green: 203/255, blue: 149/255, opacity: 0.55), size: 13)
                .multilineTextAlignment(.center)
            Spacer()
        }
    }
}

#Preview {
    let theme = Theme()
    theme.mode = .transit
    return ThresholdView()
        .environment(theme)
}
