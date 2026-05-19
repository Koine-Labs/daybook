import SwiftUI

// Three-dot constellation indicator. Active dot is wide + glows amber; adjacent
// is dim pearl. Tappable for jump navigation.

struct ConstellationDots: View {
    var index: Int
    var onNavigate: (Int) -> Void

    var body: some View {
        HStack(spacing: 8) {
            ForEach(0..<3, id: \.self) { i in
                Button(action: { onNavigate(i) }) {
                    let isActive = i == index
                    let isAdjacent = abs(i - index) == 1
                    RoundedRectangle(cornerRadius: isActive ? 4 : 3, style: .continuous)
                        .fill(
                            isActive ? Theme.amber :
                            isAdjacent ? Theme.pearlDim :
                            Theme.pearlGhost
                        )
                        .frame(width: isActive ? 22 : 6, height: 6)
                        .shadow(color: isActive ? Theme.amberGlow : .clear, radius: 6, x: 0, y: 0)
                        .shadow(color: isActive ? Theme.amberGlow : .clear, radius: 11, x: 0, y: 0)
                        .animation(.spring(response: 0.5, dampingFraction: 0.85), value: index)
                        .padding(6) // expand hit target
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }
        }
    }
}
