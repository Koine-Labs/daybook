import SwiftUI

// Watch-scale Regis — PNG body with continuous breathing + multi-layer halo,
// optional expanding listening rings.

struct WatchRegis: View {
    var size: CGFloat
    var mood: WatchMood
    var hrv: Double = 1.0
    var ringExpand: Double = 0  // 0 for rest, >0 to show listening rings

    @State private var breath = false
    @State private var pulse = false

    private var intensity: Double {
        max(0.45, min(1.25, 0.85 + (hrv - 1.0) * 0.5))
    }

    var body: some View {
        let color = mood.hueColor
        ZStack {
            // Outer diffuse halo
            Circle()
                .fill(
                    RadialGradient(
                        colors: [color.opacity(0.30 * intensity), color.opacity(0.12 * intensity), .clear],
                        center: .center, startRadius: 0, endRadius: size
                    )
                )
                .frame(width: size * 2.1, height: size * 2.1)
                .blur(radius: 6)
                .scaleEffect(pulse ? 1.08 : 1.0)
                .opacity(pulse ? 1.0 : 0.78)
                .animation(.easeInOut(duration: mood.pulseSec).repeatForever(autoreverses: true), value: pulse)

            // Mid halo (tighter, brighter)
            Circle()
                .fill(
                    RadialGradient(
                        colors: [color.opacity(0.50 * intensity), color.opacity(0.18 * intensity), .clear],
                        center: .center, startRadius: 0, endRadius: size * 0.75
                    )
                )
                .frame(width: size * 1.5, height: size * 1.5)
                .blur(radius: 3)
                .scaleEffect(pulse ? 1.12 : 1.0)
                .opacity(pulse ? 1.0 : 0.85)
                .animation(.easeInOut(duration: mood.pulseSec * 0.7).repeatForever(autoreverses: true), value: pulse)

            // Listening rings (only when ringExpand > 0)
            if ringExpand > 0 {
                ForEach(0..<2, id: \.self) { i in
                    Circle()
                        .strokeBorder(
                            color.opacity(0.40 - Double(i) * 0.15),
                            lineWidth: 0.75
                        )
                        .frame(
                            width: size * (1.5 + Double(i) * 0.45 + ringExpand * 0.5),
                            height: size * (1.5 + Double(i) * 0.45 + ringExpand * 0.5)
                        )
                        .scaleEffect(pulse ? 1.05 : 1.0)
                        .animation(
                            .easeInOut(duration: 2.2 + Double(i) * 0.3)
                                .delay(Double(i) * 0.2)
                                .repeatForever(autoreverses: true),
                            value: pulse
                        )
                }
            }

            // PNG body
            Image("regis")
                .resizable()
                .interpolation(.high)
                .aspectRatio(contentMode: .fit)
                .frame(width: size, height: size)
                .scaleEffect(breath ? 1.025 : 1.0)
                .offset(y: breath ? -3 : 0)
                .shadow(color: color.opacity(0.55), radius: 9, x: 0, y: 8)
                .shadow(color: color.opacity(0.45), radius: 7, x: 0, y: 0)
                .animation(.easeInOut(duration: mood.breathSec).repeatForever(autoreverses: true), value: breath)
        }
        .frame(width: size * 1.4, height: size * 1.4)
        .onAppear {
            breath = true
            pulse = true
        }
    }
}
