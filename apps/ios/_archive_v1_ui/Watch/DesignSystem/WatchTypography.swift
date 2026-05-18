import SwiftUI

enum WatchFont {
    static func serif(_ size: CGFloat, italic: Bool = false) -> Font {
        if italic {
            return .system(size: size, weight: .regular, design: .serif).italic()
        }
        return .system(size: size, weight: .regular, design: .serif)
    }

    static func sans(_ size: CGFloat, weight: Font.Weight = .regular) -> Font {
        .system(size: size, weight: weight, design: .default)
    }

    static func mono(_ size: CGFloat, weight: Font.Weight = .regular) -> Font {
        .system(size: size, weight: weight, design: .monospaced)
    }
}

struct WatchMeta: ViewModifier {
    let color: Color
    let size: CGFloat
    func body(content: Content) -> some View {
        content
            .font(WatchFont.mono(size, weight: .regular))
            .tracking(size * 0.12)
            .textCase(.uppercase)
            .foregroundStyle(color)
    }
}

extension View {
    func watchMeta(_ color: Color, size: CGFloat = 9) -> some View {
        modifier(WatchMeta(color: color, size: size))
    }
}
