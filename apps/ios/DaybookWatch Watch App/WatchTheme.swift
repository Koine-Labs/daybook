import SwiftUI

// Minimal palette for the watch. Subset of the iOS Theme — kept self-contained
// here since the iOS target's DesignSystem isn't shared into the watch bundle.

enum WatchTheme {
    static let ink         = Color(red: 0x07 / 255.0, green: 0x09 / 255.0, blue: 0x12 / 255.0)
    static let inkLight    = Color(red: 0x1B / 255.0, green: 0x1F / 255.0, blue: 0x36 / 255.0)
    static let pearl       = Color(red: 0xF4 / 255.0, green: 0xEC / 255.0, blue: 0xE0 / 255.0)
    static let pearlDim    = pearl.opacity(0.72)
    static let pearlFaint  = pearl.opacity(0.40)
    static let pearlGhost  = pearl.opacity(0.25)
    static let amber       = Color(red: 0xF5 / 255.0, green: 0xB8 / 255.0, blue: 0x6A / 255.0)
    static let amberDeep   = Color(red: 0xE8 / 255.0, green: 0x92 / 255.0, blue: 0x43 / 255.0)
    static let amberGlow   = Color(red: 1.0, green: 178/255.0, blue: 92/255.0).opacity(0.55)
    static let amberTime   = Color(red: 1.0, green: 200/255.0, blue: 140/255.0).opacity(0.85)
    static let amberSpeech = Color(red: 1.0, green: 0xE3 / 255.0, blue: 0xBD / 255.0)
}

enum WatchMood: String, CaseIterable {
    case calm, curious, concerned
    var hueColor: Color {
        switch self {
        case .calm:      return WatchTheme.amber
        case .curious:   return Color(red: 1.0, green: 0xC9 / 255.0, blue: 0x7A / 255.0)
        case .concerned: return Color(red: 0xE0 / 255.0, green: 0x8C / 255.0, blue: 0x55 / 255.0)
        }
    }
    var breathSec: Double {
        switch self {
        case .calm:      return 5.2
        case .curious:   return 4.2
        case .concerned: return 6.2
        }
    }
    var pulseSec: Double {
        switch self {
        case .calm:      return 3.2
        case .curious:   return 2.4
        case .concerned: return 4.2
        }
    }
}

enum WatchFonts {
    static func body(_ size: CGFloat, _ weight: Font.Weight = .regular) -> Font {
        .system(size: size, weight: weight, design: .rounded)
    }
    static func quote(_ size: CGFloat) -> Font {
        .system(size: size, weight: .regular, design: .serif).italic()
    }
    static func mono(_ size: CGFloat, _ weight: Font.Weight = .regular) -> Font {
        .system(size: size, weight: weight, design: .monospaced)
    }
}
