import SwiftUI

// StarfieldView — the eight faint stars from the .starfield CSS rule.
// Positions and colors are 1:1 with styles.css. Soft circles with a 50% radial
// fade. Non-interactive overlay; layer behind content.
struct StarfieldView: View {
    private struct Star {
        let x: Double
        let y: Double
        let color: Color
    }

    private static let glow = Color(red: 255/255, green: 203/255, blue: 149/255, opacity: 0.6)
    private static let pale = Color(red: 232/255, green: 226/255, blue: 212/255, opacity: 0.5)
    private static let glowDim = Color(red: 255/255, green: 203/255, blue: 149/255, opacity: 0.35)
    private static let paleDim = Color(red: 232/255, green: 226/255, blue: 212/255, opacity: 0.35)
    private static let paleMid = Color(red: 232/255, green: 226/255, blue: 212/255, opacity: 0.4)
    private static let glowMid = Color(red: 255/255, green: 203/255, blue: 149/255, opacity: 0.4)
    private static let paleFaint = Color(red: 232/255, green: 226/255, blue: 212/255, opacity: 0.3)
    private static let glowSoft = Color(red: 255/255, green: 203/255, blue: 149/255, opacity: 0.5)

    private static let stars: [Star] = [
        .init(x: 0.18, y: 0.22, color: glow),
        .init(x: 0.72, y: 0.14, color: pale),
        .init(x: 0.38, y: 0.64, color: glowDim),
        .init(x: 0.84, y: 0.78, color: paleDim),
        .init(x: 0.12, y: 0.84, color: paleMid),
        .init(x: 0.58, y: 0.36, color: glowMid),
        .init(x: 0.92, y: 0.48, color: paleFaint),
        .init(x: 0.28, y: 0.08, color: glowSoft)
    ]

    var body: some View {
        GeometryReader { geo in
            ZStack {
                ForEach(Array(Self.stars.enumerated()), id: \.offset) { _, star in
                    Circle()
                        .fill(
                            RadialGradient(
                                gradient: Gradient(stops: [
                                    .init(color: star.color, location: 0.0),
                                    .init(color: .clear, location: 0.5)
                                ]),
                                center: .center,
                                startRadius: 0,
                                endRadius: 4
                            )
                        )
                        .frame(width: 8, height: 8)
                        .position(
                            x: geo.size.width * star.x,
                            y: geo.size.height * star.y
                        )
                }
            }
        }
    }
}
