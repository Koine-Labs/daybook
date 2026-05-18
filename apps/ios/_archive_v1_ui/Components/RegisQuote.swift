import SwiftUI

// RegisQuote — typographic primitive for anywhere Regis is "speaking".
// Italic serif in the warm voice color. Optional leading prefix.
struct RegisQuote: View {
    let text: String
    let prefix: String
    let size: CGFloat

    @Environment(Theme.self) private var theme

    init(_ text: String, prefix: String = "", size: CGFloat = 18) {
        self.text = text
        self.prefix = prefix
        self.size = size
    }

    var body: some View {
        Text(prefix + text)
            .regisVoice(theme.voice, size: size)
            .lineSpacing(size * 0.25 - size)
            .fixedSize(horizontal: false, vertical: true)
    }
}
