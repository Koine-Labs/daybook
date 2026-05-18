import SwiftUI

// A small wisp glyph used as the Settings entry in the top-right of every
// top-level screen. Tapping opens the SettingsSheet half-sheet.

struct WispProfileBtn: View {
    var size: CGFloat = 22
    var state: WispState = .dormant
    var action: () -> Void

    @Environment(Theme.self) private var theme

    var body: some View {
        Button(action: action) {
            WispView(size: size, state: state, mode: theme.mode)
                .frame(width: 36, height: 36)
                .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Settings")
    }
}
