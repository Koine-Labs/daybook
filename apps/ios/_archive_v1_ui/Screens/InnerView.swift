import SwiftUI

// InnerView — what Regis has noticed about you. The bond's memory rendered
// visible: regis_observations + recurring themes + trait drift.
//
// Empty state for a brand-new user: no observations, no themes, no drift.
// Show that honestly; don't fake data.

struct InnerView: View {
    @Environment(AppState.self) private var appState
    @Environment(Theme.self) private var theme

    // TODO: wire to APIClient.get("/observations") + /regis/traits + /regis/themes.
    // Empty for now — a new user has no accumulated data.
    @State private var hasAnyContent: Bool = false

    var body: some View {
        VStack(spacing: 0) {
            // Top bar — eyebrow + settings entry (top-right wisp button)
            HStack(alignment: .center) {
                Text("INNER · WHAT I'M NOTICING")
                    .dbEyebrow(theme.ink3)
                Spacer()
                Button { appState.settingsOpen = true } label: {
                    WispMark(size: 14, mode: theme.mode)
                        .frame(width: 36, height: 36)
                        .contentShape(Circle())
                }
                .buttonStyle(.plain)
                .wispAnchor(.settingsCorner)
            }
            .padding(.horizontal, 22)
            .padding(.top, 54)
            .padding(.bottom, 14)

            if hasAnyContent {
                // Future: populated state. Real list of observations, themes, drift.
                Text("(populated state will live here)")
                    .font(.system(size: 13))
                    .foregroundStyle(theme.ink3)
            } else {
                // Empty state
                VStack(spacing: 18) {
                    Spacer()
                    Text("I haven't been with you long enough.")
                        .regisVoice(theme.voice, size: 22)
                        .multilineTextAlignment(.center)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.horizontal, 36)
                    Text("check back after we've shared\nsome nights and some days.")
                        .font(.system(size: 13))
                        .foregroundStyle(theme.ink3)
                        .multilineTextAlignment(.center)
                        .lineSpacing(4)
                    Spacer()
                    Spacer()
                }
                .frame(maxWidth: .infinity)
                .wispAnchor(.centerStage)
            }
        }
        .background(theme.bg.ignoresSafeArea())
    }
}
