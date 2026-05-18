import SwiftUI

// LabView — advanced/dev surface. Sensor lab, system status, immersive-screen
// triggers. Intentionally less polished than the main tabs; this is where
// power-user tooling lives.

struct LabView: View {
    @Environment(AppState.self) private var appState
    @Environment(Theme.self) private var theme

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                ScreenHead(
                    title: "Lab",
                    sub: "SYSTEM · TRIGGERS · SENSORS",
                    wispState: .dormant
                )
                .padding(.horizontal, 22)

                VStack(alignment: .leading, spacing: 14) {
                    eyebrow("IMMERSIVE TRIGGERS")
                    Text("Manually open the ceremonial screens — these are wired automatically in production by sensor / wake events.")
                        .font(.system(size: 13))
                        .foregroundStyle(theme.ink2)
                        .padding(.bottom, 4)

                    triggerCard(
                        title: "Threshold",
                        sub: "pre-sleep wind-down + intent",
                        route: .threshold
                    )
                    triggerCard(
                        title: "Night",
                        sub: "REM cue — witness mode",
                        route: .night
                    )
                    triggerCard(
                        title: "Recall",
                        sub: "morning capture ceremony",
                        route: .recall
                    )
                }
                .padding(.horizontal, 22)

                VStack(alignment: .leading, spacing: 14) {
                    eyebrow("SYSTEM")
                    statRow(label: "API base", value: "http://localhost:8000")
                    statRow(label: "Backend", value: "FastAPI · gpt-5.2 (codex)")
                    statRow(label: "Embeddings", value: "BGE-M3 · 1024-dim · local")
                    statRow(label: "Database", value: "Neon · 16 tables")
                }
                .padding(.horizontal, 22)

                VStack(alignment: .leading, spacing: 14) {
                    eyebrow("SENSORS")
                    statRow(label: "Apple Watch", value: "passive · 10yr history")
                    statRow(label: "BioAmp EXG Pill", value: "ordered · ~10 days")
                    statRow(label: "Bone-conduction", value: "ordered · ~3 days")
                }
                .padding(.horizontal, 22)

                Spacer(minLength: 120)
            }
            .padding(.top, 12)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .background(theme.bg.ignoresSafeArea())
    }

    @ViewBuilder
    private func eyebrow(_ text: String) -> some View {
        Text(text)
            .font(.system(size: 11, weight: .medium, design: .default))
            .tracking(2)
            .foregroundStyle(theme.ink3)
    }

    @ViewBuilder
    private func triggerCard(title: String, sub: String, route: ImmersiveRoute) -> some View {
        Button {
            appState.immersive = route
        } label: {
            HStack(spacing: 14) {
                WispMark(size: 18, mode: theme.mode)
                VStack(alignment: .leading, spacing: 2) {
                    Text(title)
                        .font(.system(size: 17, weight: .semibold))
                        .foregroundStyle(theme.ink)
                    Text(sub)
                        .font(.system(size: 12))
                        .foregroundStyle(theme.ink3)
                }
                Spacer()
                Text("OPEN →")
                    .font(.system(size: 11, weight: .medium))
                    .tracking(1.5)
                    .foregroundStyle(theme.amber)
            }
            .padding(16)
            .frame(maxWidth: .infinity)
            .background(theme.card)
            .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .strokeBorder(theme.edge, lineWidth: 0.5)
            )
        }
        .buttonStyle(.plain)
    }

    @ViewBuilder
    private func statRow(label: String, value: String) -> some View {
        HStack(alignment: .firstTextBaseline) {
            Text(label)
                .font(.system(size: 13))
                .foregroundStyle(theme.ink2)
            Spacer()
            Text(value)
                .font(.system(.caption, design: .monospaced))
                .foregroundStyle(theme.ink)
        }
        .padding(.vertical, 6)
        .overlay(
            Rectangle()
                .fill(theme.edge)
                .frame(height: 0.5)
                .padding(.top, 28),
            alignment: .bottom
        )
    }
}

#Preview {
    let state = AppState()
    return LabView()
        .environment(state)
        .environment(state.theme)
}
