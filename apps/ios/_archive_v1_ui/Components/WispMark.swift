import SwiftUI

// Static wisp mark for inline use (tab bar, list items, etc.).
// No animations — port of WispMark from wisp.jsx.
struct WispMark: View {
    let size: CGFloat
    let mode: ThemeMode

    init(size: CGFloat = 14, mode: ThemeMode = .companion) {
        self.size = size
        self.mode = mode
    }

    private var isNight: Bool { mode == .witness }
    private var core: Color { isNight ? .witnessGlow : .companionAmberSoft }
    private var amber: Color { isNight ? .witnessEmber : .companionAmber }

    var body: some View {
        ZStack {
            WispHornsShape()
                .fill(amber.opacity(0.55))

            WispTeardropShape()
                .fill(
                    RadialGradient(
                        gradient: Gradient(stops: [
                            .init(color: .wispHighlight, location: 0.0),
                            .init(color: core, location: 0.4),
                            .init(color: amber, location: 1.0)
                        ]),
                        center: UnitPoint(x: 0.5, y: 0.55),
                        startRadius: 0,
                        endRadius: size * 0.55
                    )
                )

            HStack(spacing: size * 0.225) {
                Circle().fill(Color.wispEyeDot.opacity(0.7))
                    .frame(width: size * 0.07, height: size * 0.07)
                Circle().fill(Color.wispEyeDot.opacity(0.7))
                    .frame(width: size * 0.07, height: size * 0.07)
            }
            .offset(y: size * 0.10)
        }
        .frame(width: size, height: size * 1.15)
    }
}
