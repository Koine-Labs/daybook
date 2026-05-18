import SwiftUI

// ArchiveView — your captured artifacts: dreams, voice memos, journal entries.
// Empty state for a brand-new user: nothing logged yet.

struct ArchiveView: View {
    @Environment(AppState.self) private var appState
    @Environment(Theme.self) private var theme

    // TODO: wire to APIClient.get("/dreams"). Empty for now.
    @State private var hasAnyDreams: Bool = false

    var body: some View {
        VStack(spacing: 0) {
            // Top bar
            HStack(alignment: .center) {
                Text("ARCHIVE")
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

            if hasAnyDreams {
                Text("(populated state will live here)")
                    .font(.system(size: 13))
                    .foregroundStyle(theme.ink3)
            } else {
                // Empty state — single capture affordance
                VStack(spacing: 22) {
                    Spacer()
                    Text("no dreams yet.")
                        .regisVoice(theme.voice, size: 22)
                        .multilineTextAlignment(.center)
                    Text("open recall when you wake —\nor whenever you remember something.")
                        .font(.system(size: 13))
                        .foregroundStyle(theme.ink3)
                        .multilineTextAlignment(.center)
                        .lineSpacing(4)

                    Button {
                        // TODO: open recall capture flow
                    } label: {
                        Text("start recall")
                            .font(.system(size: 14, weight: .medium))
                            .foregroundStyle(theme.bg)
                            .padding(.horizontal, 20)
                            .padding(.vertical, 11)
                            .background(theme.ink)
                            .clipShape(Capsule())
                    }
                    .buttonStyle(.plain)
                    .padding(.top, 10)

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
