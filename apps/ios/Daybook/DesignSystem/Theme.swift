import SwiftUI

// Design system — mirrored from styles.css in the Claude Design handoff.
// CSS oklch() values are approximated as RGB; SwiftUI has no native oklch.

enum Theme {
    // Ink-navy ground (deep blue-black)
    static let bgBase = Color(red: 0x0A / 255.0, green: 0x0C / 255.0, blue: 0x14 / 255.0)
    static let bgDeep = Color(red: 0x07 / 255.0, green: 0x09 / 255.0, blue: 0x12 / 255.0)
    static let inkLight = Color(red: 0x28 / 255.0, green: 0x2C / 255.0, blue: 0x46 / 255.0) // oklch(0.24 0.055 255)
    static let inkMid   = Color(red: 0x1B / 255.0, green: 0x1F / 255.0, blue: 0x36 / 255.0) // oklch(0.18 0.05  255)
    static let inkDark  = Color(red: 0x13 / 255.0, green: 0x16 / 255.0, blue: 0x28 / 255.0) // oklch(0.13 0.045 255)

    // Pearl text family (#F4ECE0 at varying opacity)
    static let pearl       = Color(red: 0xF4 / 255.0, green: 0xEC / 255.0, blue: 0xE0 / 255.0)
    static let pearlDim    = pearl.opacity(0.62)
    static let pearlFaint  = pearl.opacity(0.38)
    static let pearlGhost  = pearl.opacity(0.18)

    // Amber (Regis-glow)
    static let amber       = Color(red: 0xF5 / 255.0, green: 0xB8 / 255.0, blue: 0x6A / 255.0) // oklch(0.82 0.17 65)
    static let amberDeep   = Color(red: 0xE8 / 255.0, green: 0x92 / 255.0, blue: 0x43 / 255.0) // oklch(0.72 0.19 55)
    static let amberGlow   = Color(red: 1.0, green: 178/255.0, blue: 92/255.0).opacity(0.55)
    static let amberWarm   = Color(red: 1.0, green: 0xE7 / 255.0, blue: 0xB8 / 255.0) // #FFE7B8 particle core
    static let amberQuote  = Color(red: 1.0, green: 0xE9 / 255.0, blue: 0xCB / 255.0) // memory thread quote color
    static let amberSpeech = Color(red: 1.0, green: 0xE4 / 255.0, blue: 0xBD / 255.0) // Regis ping speech
    static let amberReply  = Color(red: 1.0, green: 0xE7 / 255.0, blue: 0xC4 / 255.0) // chat transcript Regis voice
    static let amberPortrait = Color(red: 0xF0 / 255.0, green: 0xE2 / 255.0, blue: 0xC8 / 255.0)

    // Functional accents
    static let cool        = Color(red: 0x9B / 255.0, green: 0xB3 / 255.0, blue: 0xC8 / 255.0) // body whisper "mind"
    static let green       = Color(red: 0x9C / 255.0, green: 0xC7 / 255.0, blue: 0x95 / 255.0) // active dot / Spotify
}

extension Color {
    // Builder used in gradients with amber at variable intensity
    static func amber(_ alpha: Double) -> Color { Theme.amber.opacity(alpha) }
    static func pearl(_ alpha: Double) -> Color { Theme.pearl.opacity(alpha) }
}

// Typography. Bundled fonts are not yet wired; using system-rounded / serif / monospaced
// as a clean fallback that respects the same character (rounded sans body, serif italic
// for Regis's voice, mono for labels). Once Plus Jakarta Sans / Cardo / JetBrains Mono
// .ttf files are added to Resources + UIAppFonts, swap names below.
enum Fonts {
    // Body — rounded modern sans (Plus Jakarta Sans target)
    static func body(_ size: CGFloat, _ weight: Font.Weight = .regular) -> Font {
        .system(size: size, weight: weight, design: .rounded)
    }

    // Regis's quoted speech — Cardo italic target
    static func quote(_ size: CGFloat) -> Font {
        .system(size: size, weight: .regular, design: .serif).italic()
    }

    // Labels — JetBrains Mono target
    static func mono(_ size: CGFloat, _ weight: Font.Weight = .regular) -> Font {
        .system(size: size, weight: weight, design: .monospaced)
    }
}

// Common reusable text styles
struct LabelTinyStyle: ViewModifier {
    var color: Color = Theme.pearlFaint
    func body(content: Content) -> some View {
        content
            .font(Fonts.body(10, .semibold))
            .tracking(1.6)
            .textCase(.uppercase)
            .foregroundStyle(color)
    }
}
struct LabelMonoStyle: ViewModifier {
    var color: Color = Theme.pearlFaint
    var size: CGFloat = 10.5
    func body(content: Content) -> some View {
        content
            .font(Fonts.mono(size))
            .tracking(0.2)
            .foregroundStyle(color)
    }
}
struct WhisperStyle: ViewModifier {
    func body(content: Content) -> some View {
        content
            .font(Fonts.body(14))
            .lineSpacing(2)
            .foregroundStyle(Theme.pearlDim)
    }
}
extension View {
    func labelTiny(_ color: Color = Theme.pearlFaint) -> some View { modifier(LabelTinyStyle(color: color)) }
    func labelMono(_ color: Color = Theme.pearlFaint, size: CGFloat = 10.5) -> some View {
        modifier(LabelMonoStyle(color: color, size: size))
    }
    func whisper() -> some View { modifier(WhisperStyle()) }
}
