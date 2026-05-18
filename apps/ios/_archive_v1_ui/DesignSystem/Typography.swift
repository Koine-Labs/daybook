import SwiftUI

// Typography registers mirror styles.css typographic classes (db-h, db-h-lg,
// db-eyebrow, db-meta, regis-voice). Fonts are currently system fallbacks —
// see README for the Instrument Serif / Instrument Sans / JetBrains Mono swap.

enum DBFont {
    // Serif used for headlines, dream fragments, and Regis's voice.
    // Charter is bundled on iOS and reads close enough to Instrument Serif
    // for this scaffolding pass.
    static func serif(_ size: CGFloat, italic: Bool = false) -> Font {
        let descriptor = UIFont.Descriptor.serif(size: size, italic: italic)
        return Font(UIFont(descriptor: descriptor, size: size))
    }

    static func sans(_ size: CGFloat, weight: Font.Weight = .regular) -> Font {
        .system(size: size, weight: weight, design: .default)
    }

    static func mono(_ size: CGFloat, weight: Font.Weight = .regular) -> Font {
        .system(size: size, weight: weight, design: .monospaced)
    }
}

private extension UIFont {
    enum Descriptor {
        static func serif(size: CGFloat, italic: Bool) -> UIFontDescriptor {
            let base = UIFont.systemFont(ofSize: size).fontDescriptor
                .withDesign(.serif) ?? UIFont.systemFont(ofSize: size).fontDescriptor
            if italic {
                return base.withSymbolicTraits(.traitItalic) ?? base
            }
            return base
        }
    }
}

struct DBHeadlineLarge: ViewModifier {
    let color: Color
    func body(content: Content) -> some View {
        content
            .font(DBFont.serif(64))
            .tracking(-0.64)
            .lineSpacing(0)
            .foregroundStyle(color)
    }
}

struct DBHeadline: ViewModifier {
    let color: Color
    func body(content: Content) -> some View {
        content
            .font(DBFont.serif(34))
            .tracking(-0.34)
            .foregroundStyle(color)
    }
}

struct DBEyebrow: ViewModifier {
    let color: Color
    func body(content: Content) -> some View {
        content
            .font(DBFont.sans(11, weight: .medium))
            .tracking(1.54)
            .textCase(.uppercase)
            .foregroundStyle(color)
    }
}

struct DBMeta: ViewModifier {
    let color: Color
    func body(content: Content) -> some View {
        content
            .font(DBFont.mono(10.5, weight: .regular))
            .tracking(0.42)
            .textCase(.uppercase)
            .foregroundStyle(color)
    }
}

struct RegisVoice: ViewModifier {
    let color: Color
    let size: CGFloat
    func body(content: Content) -> some View {
        content
            .font(DBFont.serif(size, italic: true))
            .tracking(0.09)
            .foregroundStyle(color)
    }
}

extension View {
    func dbHeadlineLarge(_ color: Color) -> some View { modifier(DBHeadlineLarge(color: color)) }
    func dbHeadline(_ color: Color) -> some View { modifier(DBHeadline(color: color)) }
    func dbEyebrow(_ color: Color) -> some View { modifier(DBEyebrow(color: color)) }
    func dbMeta(_ color: Color) -> some View { modifier(DBMeta(color: color)) }
    func regisVoice(_ color: Color, size: CGFloat = 18) -> some View {
        modifier(RegisVoice(color: color, size: size))
    }
}
