import SwiftUI

// CompanionTopBar — calm header used by every non-immersive screen.
// Date / meta on left, wisp profile button (settings entry) on right.

struct CompanionTopBar: View {
    var sub: String = "tue · 17 may · 11:24"
    var wispState: WispState = .dormant

    @Environment(AppState.self) private var appState
    @Environment(Theme.self) private var theme

    var body: some View {
        HStack(alignment: .center) {
            Text(sub)
                .dbMeta(theme.ink3)
            Spacer()
            WispProfileBtn(state: wispState) {
                appState.settingsOpen = true
            }
        }
        .padding(.horizontal, 22)
        .padding(.top, 54)
        .padding(.bottom, 4)
    }
}
