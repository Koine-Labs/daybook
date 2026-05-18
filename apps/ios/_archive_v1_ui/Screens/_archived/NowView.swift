import SwiftUI

// NowView — the home / bond-moment screen.
// Minimal variant: just the wisp + Regis's line + a capture invitation.
// Below the fold: a single quiet observation if you scroll.
//
// The headline is "the line" — what Regis is reading about you right now.
// Everything else is in service.

struct NowView: View {
    @Environment(Theme.self) private var theme

    // TODO: wire to APIClient.get("/health") → derive a current empathic read.
    //       For now hardcoded to the design's reference line.
    private let lineA = "\u{201C}Settled. Quieter than yesterday.\u{201D}"
    private let lineB = "\u{201C}Holding something in your shoulders.\u{201D}"

    var body: some View {
        VStack(spacing: 0) {
            CompanionTopBar(sub: "tue · 17 may · 11:24", wispState: .dormant)

            ScrollView(.vertical, showsIndicators: false) {
                VStack(spacing: 0) {
                    // ── First screen-height: the bond moment ────────────────
                    VStack(spacing: 0) {
                        // Big wisp, centered
                        WispView(size: 44, state: .dormant, mode: theme.mode)
                            .frame(maxWidth: .infinity)
                            .padding(.bottom, 28)

                        // THE LINE — Regis's read of you right now.
                        VStack(alignment: .leading, spacing: 0) {
                            Text(lineA)
                                .regisVoice(theme.voice, size: 32)
                                .multilineTextAlignment(.leading)
                                .lineSpacing(2)
                                .padding(.bottom, 4)

                            Text(lineB)
                                .regisVoice(theme.voice, size: 32)
                                .multilineTextAlignment(.leading)
                                .lineSpacing(2)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)

                        Spacer(minLength: 60)

                        // Capture invitation
                        QuickCaptureButton(label: "tell me something") {
                            // TODO: open record / chat
                        }

                        Text("or stay · he'll wait")
                            .dbMeta(theme.ink3)
                            .frame(maxWidth: .infinity)
                            .padding(.top, 14)
                    }
                    .padding(.top, 64)
                    .padding(.horizontal, 30)
                    .frame(minHeight: 520, alignment: .top)

                    // ── Below the fold: one quiet morsel ────────────────────
                    VStack(spacing: 16) {
                        Text("if you scroll")
                            .dbEyebrow(theme.ink3)
                            .frame(maxWidth: .infinity)

                        RecentObservationCard(
                            text: "You walk less on the days you slept past 07:00. Coincidence is also a pattern.",
                            timeAgo: "2 hrs ago",
                            observationNo: 47
                        )
                    }
                    .padding(.horizontal, 30)
                    .padding(.top, 40)
                    .padding(.bottom, 130)
                }
            }
        }
        .background(theme.bg.ignoresSafeArea())
    }
}

#Preview {
    let state = AppState()
    return NowView()
        .environment(state)
        .environment(state.theme)
}
