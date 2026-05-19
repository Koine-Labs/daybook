import SwiftUI

// Ambient particles — drifting warm motes. Honest implementation via TimelineView so
// many particles tick efficiently as one redraw.

struct AmbientParticles: View {
    var count: Int = 16
    var show: Bool = true

    // Static seed table — same particle topology every launch (parity with the React
    // version's useMemo). Phase drifts via time so it doesn't loop on a hard boundary.
    private let particles: [Particle]

    init(count: Int = 16, show: Bool = true) {
        self.count = count
        self.show = show
        var rng = SystemRandomNumberGenerator()
        self.particles = (0..<count).map { i in
            Particle(
                id: i,
                xFrac: Double.random(in: 0...1, using: &rng),
                yFrac: 0.30 + Double.random(in: 0...0.70, using: &rng),
                size: 1.0 + Double.random(in: 0...2.5, using: &rng),
                dx: Double.random(in: -30...30, using: &rng),
                dy: -40.0 - Double.random(in: 0...80, using: &rng),
                durSec: 9.0 + Double.random(in: 0...8, using: &rng),
                phase: Double.random(in: 0...1, using: &rng),
                maxOpacity: 0.25 + Double.random(in: 0...0.45, using: &rng)
            )
        }
    }

    var body: some View {
        if show {
            GeometryReader { geo in
                TimelineView(.animation) { ctx in
                    let t = ctx.date.timeIntervalSinceReferenceDate
                    Canvas { canvas, size in
                        for p in particles {
                            let local = (t / p.durSec + p.phase).truncatingRemainder(dividingBy: 1.0)
                            let xBase = p.xFrac * Double(size.width)
                            let yBase = p.yFrac * Double(size.height)
                            let x = xBase + p.dx * local
                            let y = yBase + p.dy * local
                            let alpha: Double = {
                                if local < 0.2 { return (local / 0.2) * p.maxOpacity }
                                if local > 0.8 { return ((1.0 - local) / 0.2) * p.maxOpacity }
                                return p.maxOpacity
                            }()
                            let rect = CGRect(
                                x: x - p.size,
                                y: y - p.size,
                                width: p.size * 2,
                                height: p.size * 2
                            )
                            canvas.fill(
                                Path(ellipseIn: rect),
                                with: .radialGradient(
                                    Gradient(colors: [
                                        Color(red: 1.0, green: 231/255.0, blue: 184/255.0).opacity(alpha),
                                        .clear,
                                    ]),
                                    center: CGPoint(x: x, y: y),
                                    startRadius: 0,
                                    endRadius: p.size * 2.5
                                )
                            )
                        }
                    }
                    .frame(width: geo.size.width, height: geo.size.height)
                }
            }
            .allowsHitTesting(false)
        }
    }
}

private struct Particle: Identifiable {
    let id: Int
    var xFrac: Double
    var yFrac: Double
    var size: Double
    var dx: Double
    var dy: Double
    var durSec: Double
    var phase: Double
    var maxOpacity: Double
}
