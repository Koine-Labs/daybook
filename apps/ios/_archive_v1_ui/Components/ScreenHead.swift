import SwiftUI

// ScreenHead — the calm header at the top of each screen.
// Date/subtitle on the left, ambient Wisp on the right.
struct ScreenHead<Trailing: View>: View {
    let title: String?
    let sub: String?
    let wispState: WispState
    let showWisp: Bool
    let trailing: () -> Trailing

    @Environment(Theme.self) private var theme

    init(
        title: String? = nil,
        sub: String? = nil,
        wispState: WispState = .dormant,
        showWisp: Bool = true,
        @ViewBuilder trailing: @escaping () -> Trailing = { EmptyView() }
    ) {
        self.title = title
        self.sub = sub
        self.wispState = wispState
        self.showWisp = showWisp
        self.trailing = trailing
    }

    var body: some View {
        HStack(alignment: .center) {
            VStack(alignment: .leading, spacing: 2) {
                if let sub {
                    Text(sub)
                        .dbMeta(theme.ink3)
                }
                if let title, !title.isEmpty {
                    Text(title)
                        .font(DBFont.sans(13.5, weight: .semibold))
                        .tracking(0.14)
                        .foregroundStyle(theme.ink)
                }
            }
            Spacer()
            HStack(spacing: 10) {
                trailing()
                if showWisp {
                    WispView(size: 22, state: wispState, mode: theme.mode)
                }
            }
        }
        .padding(.horizontal, Spacing.xl)
        .padding(.top, 54)
    }
}
