import SwiftUI

// VuBars — animated VU meter shown while Regis (or the user) is recording.
// Port of shell.jsx VuBars. Each bar pulses on its own timer.
struct VuBars: View {
    let count: Int
    let color: Color
    let height: CGFloat

    init(count: Int = 24, color: Color = .companionAmber, height: CGFloat = 36) {
        self.count = count
        self.color = color
        self.height = height
    }

    @State private var animating = false

    var body: some View {
        HStack(alignment: .center, spacing: 3) {
            ForEach(0..<count, id: \.self) { i in
                bar(at: i)
            }
        }
        .frame(height: height)
        .onAppear { animating = true }
    }

    private func bar(at index: Int) -> some View {
        let baseHeight = 0.30 + Double((index * 13) % 70) / 100.0
        let duration = 0.6 + Double(index % 5) * 0.12
        let delay = Double(index) * 0.04

        return RoundedRectangle(cornerRadius: 1.5)
            .fill(color.opacity(0.7))
            .frame(width: 3, height: height * baseHeight)
            .scaleEffect(y: animating ? 1.0 : 0.3, anchor: .center)
            .animation(
                .easeInOut(duration: duration)
                    .repeatForever(autoreverses: true)
                    .delay(delay),
                value: animating
            )
    }
}
