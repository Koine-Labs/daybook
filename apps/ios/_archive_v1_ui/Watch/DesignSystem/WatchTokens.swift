import SwiftUI

extension Color {
    static let watchEmber = Color(watchHex: "E89456")
    static let watchGlow = Color(watchHex: "FFCB95")
    static let watchInk = Color(watchHex: "E8E2D4")
    static let watchInkDim = Color(watchHex: "968F80")
    static let watchMorningInk = Color(watchHex: "FFE9CC")
    static let watchHighlight = Color(watchHex: "FFEACB")
    static let watchEyeDot = Color(watchHex: "1A0E05")

    init(watchHex: String) {
        let trimmed = watchHex.trimmingCharacters(in: .alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: trimmed).scanHexInt64(&int)
        let r, g, b, a: UInt64
        switch trimmed.count {
        case 6:
            (r, g, b, a) = ((int >> 16) & 0xFF, (int >> 8) & 0xFF, int & 0xFF, 255)
        case 8:
            (r, g, b, a) = ((int >> 24) & 0xFF, (int >> 16) & 0xFF, (int >> 8) & 0xFF, int & 0xFF)
        default:
            (r, g, b, a) = (0, 0, 0, 255)
        }
        self.init(
            .sRGB,
            red: Double(r) / 255,
            green: Double(g) / 255,
            blue: Double(b) / 255,
            opacity: Double(a) / 255
        )
    }
}

enum WatchMode: String, Hashable, Sendable {
    case companion
    case witness
}
