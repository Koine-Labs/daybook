import SwiftUI

// RoomBackground — ink-navy radial ground + warm spill from where Regis sits +
// vignette + faint twinkling stars. Spill falls off as you swipe away from Now.

struct RoomBackground: View {
    var tweaks: Tweaks
    var roomIndex: Int     // 0 = self, 1 = now, 2 = connections

    private var localSpill: Double {
        let dist = Double(abs(roomIndex - 1))
        return tweaks.timeSpec.spill * tweaks.glassIntensity * (1.0 - dist * 0.4)
    }

    var body: some View {
        ZStack {
            // Base ink gradient — bottom up, deeper toward edges
            RadialGradient(
                colors: [Theme.inkLight, Theme.inkDark, Theme.bgDeep],
                center: UnitPoint(x: 0.5, y: 1.0),
                startRadius: 40,
                endRadius: 620
            )
            .ignoresSafeArea()

            // Warm spill — from where Regis sits (upper-center)
            WarmSpill(intensity: localSpill)

            // Vignette
            RadialGradient(
                colors: [.clear, .black.opacity(0.5)],
                center: .center, startRadius: 220, endRadius: 520
            )
            .ignoresSafeArea()
            .allowsHitTesting(false)

            // Faint top stars
            StarsField()
        }
    }
}

private struct WarmSpill: View {
    var intensity: Double
    @State private var pulse = false

    var body: some View {
        GeometryReader { geo in
            let w = geo.size.width
            let h = geo.size.height
            Circle()
                .fill(
                    RadialGradient(
                        colors: [
                            Theme.amber.opacity(0.55 * intensity),
                            Theme.amberDeep.opacity(0.25 * intensity),
                            .clear,
                        ],
                        center: .center,
                        startRadius: 0,
                        endRadius: 320
                    )
                )
                .frame(width: w * 1.7, height: h * 0.45)
                .position(x: w / 2, y: h * 0.18)
                .blur(radius: 20)
                .scaleEffect(pulse ? 1.05 : 0.96)
                .opacity(pulse ? 1.0 : 0.85)
                .animation(.easeInOut(duration: 6).repeatForever(autoreverses: true), value: pulse)
                .onAppear { pulse = true }
        }
        .clipped()
        .allowsHitTesting(false)
    }
}

private struct StarsField: View {
    private let stars: [(x: Double, y: Double, phase: Double, dur: Double)] = [
        (0.12, 0.18, 0.0, 3.0),
        (0.44, 0.08, 0.5, 4.0),
        (0.67, 0.22, 1.0, 5.0),
        (0.88, 0.12, 1.5, 3.0),
        (0.22, 0.32, 2.0, 4.0),
        (0.78, 0.38, 2.5, 5.0),
        (0.35, 0.06, 3.0, 3.0),
        (0.58, 0.28, 3.5, 4.0),
    ]
    var body: some View {
        GeometryReader { geo in
            TimelineView(.animation(minimumInterval: 1.0/30.0, paused: false)) { ctx in
                let t = ctx.date.timeIntervalSinceReferenceDate
                Canvas { canvas, size in
                    for s in stars {
                        let phase = (t / s.dur + s.phase).truncatingRemainder(dividingBy: 1.0)
                        let alpha = 0.3 + 0.7 * (sin(phase * 2 * .pi) * 0.5 + 0.5)
                        let rect = CGRect(
                            x: s.x * size.width - 0.75,
                            y: s.y * size.height - 0.75,
                            width: 1.5, height: 1.5
                        )
                        canvas.fill(
                            Path(ellipseIn: rect),
                            with: .color(Color(red: 1.0, green: 246/255.0, blue: 226/255.0).opacity(alpha * 0.4))
                        )
                    }
                }
                .frame(width: geo.size.width, height: geo.size.height)
            }
        }
        .allowsHitTesting(false)
    }
}
