import SwiftUI

// Daybook design tokens — direct translation of styles.css :root variables.
// Two palettes: companion (paper, daylight) and witness (night, reverent).

extension Color {
    // Companion / paper mode
    static let companionBg = Color(hex: "F2ECDF")
    static let companionBg2 = Color(hex: "E9E1D0")
    static let companionCard = Color(hex: "FBF7EE")
    static let companionEdge = Color(red: 28/255, green: 26/255, blue: 23/255, opacity: 0.08)
    static let companionInk = Color(hex: "1C1A17")
    static let companionInk2 = Color(hex: "56504A")
    static let companionInk3 = Color(hex: "948A7E")
    static let companionAmber = Color(hex: "C97C3A")
    static let companionAmberSoft = Color(hex: "E5A971")
    static let companionAmberInk = Color(hex: "8B5A2B")
    static let companionViolet = Color(hex: "6B5982")

    // Witness / night mode
    static let witnessBg = Color(hex: "07090F")
    static let witnessBg2 = Color(hex: "0F131E")
    static let witnessCard = Color(hex: "141927")
    static let witnessEdge = Color(red: 232/255, green: 226/255, blue: 212/255, opacity: 0.07)
    static let witnessInk = Color(hex: "E8E2D4")
    static let witnessInk2 = Color(hex: "968F80")
    static let witnessInk3 = Color(hex: "5E5849")
    static let witnessEmber = Color(hex: "E89456")
    static let witnessGlow = Color(hex: "FFCB95")
    static let witnessViolet = Color(hex: "6F5DA0")

    // Inner highlight for wisp glyph
    static let wispHighlight = Color(hex: "FFEACB")
    static let wispEyeDot = Color(hex: "1A0E05")

    init(hex: String) {
        let trimmed = hex.trimmingCharacters(in: .alphanumerics.inverted)
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

enum Spacing {
    static let xs: CGFloat = 4
    static let sm: CGFloat = 8
    static let md: CGFloat = 14
    static let lg: CGFloat = 18
    static let xl: CGFloat = 22
    static let xxl: CGFloat = 28
}

enum Radius {
    static let chip: CGFloat = 999
    static let card: CGFloat = 18
}
