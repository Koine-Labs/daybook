import SwiftUI

// Glass panel — translucent pearl-tinted material with inner top shine, dim bottom
// inset, warm spill highlight from upper-left, and a 0.5px warm border. Mirrors the
// .glass class in styles.css.
struct GlassPanel: ViewModifier {
    var cornerRadius: CGFloat = 26
    var strong: Bool = false

    func body(content: Content) -> some View {
        content
            .background(
                ZStack {
                    // backdrop-filter: blur + saturation
                    RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                        .fill(.ultraThinMaterial)

                    // pearl tint on top of blur
                    RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                        .fill(Theme.pearl.opacity(strong ? 0.085 : 0.045))

                    // warm spill highlight from top-left
                    RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                        .fill(
                            RadialGradient(
                                colors: [
                                    Color(red: 1.0, green: 200/255.0, blue: 140/255.0).opacity(0.10),
                                    .clear
                                ],
                                center: UnitPoint(x: 0.18, y: -0.10),
                                startRadius: 0,
                                endRadius: 240
                            )
                        )
                        .blendMode(.plusLighter)
                }
            )
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .strokeBorder(Color(red: 1.0, green: 230/255.0, blue: 200/255.0).opacity(0.14), lineWidth: 0.5)
            )
            .overlay(
                // inner top shine (1px)
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .trim(from: 0.0, to: 1.0)
                    .stroke(
                        LinearGradient(
                            colors: [Color(red: 1.0, green: 245/255.0, blue: 230/255.0).opacity(0.35), .clear],
                            startPoint: .top, endPoint: .center
                        ),
                        lineWidth: 0.8
                    )
                    .blendMode(.plusLighter)
                    .allowsHitTesting(false)
            )
            .shadow(color: .black.opacity(0.22), radius: 12, x: 0, y: 1)
    }
}

extension View {
    func glassPanel(cornerRadius: CGFloat = 26, strong: Bool = false) -> some View {
        modifier(GlassPanel(cornerRadius: cornerRadius, strong: strong))
    }
}

// The amber-lipped pill used for the "say something to regis" affordance and the chat
// voice mode container.
struct TalkPillBackground: View {
    var cornerRadius: CGFloat = .infinity
    var body: some View {
        ZStack {
            Capsule(style: .continuous)
                .fill(.ultraThinMaterial)
            Capsule(style: .continuous)
                .fill(Theme.pearl.opacity(0.06))
            Capsule(style: .continuous)
                .strokeBorder(Color(red: 1.0, green: 230/255.0, blue: 200/255.0).opacity(0.16), lineWidth: 0.5)
            Capsule(style: .continuous)
                .stroke(
                    LinearGradient(
                        colors: [Color(red: 1.0, green: 245/255.0, blue: 230/255.0).opacity(0.32), .clear],
                        startPoint: .top, endPoint: .center
                    ),
                    lineWidth: 0.8
                )
                .blendMode(.plusLighter)
                .allowsHitTesting(false)
        }
        .shadow(color: .black.opacity(0.35), radius: 11, x: 0, y: 6)
    }
}
