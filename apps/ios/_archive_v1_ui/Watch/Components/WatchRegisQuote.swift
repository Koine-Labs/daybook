import SwiftUI

struct WatchRegisQuote: View {
    let text: String
    let size: CGFloat
    let color: Color

    init(_ text: String, size: CGFloat = 12, color: Color = .watchEmber) {
        self.text = text
        self.size = size
        self.color = color
    }

    var body: some View {
        Text(text)
            .font(WatchFont.serif(size, italic: true))
            .tracking(size * 0.005)
            .foregroundStyle(color)
            .lineSpacing(2)
    }
}
