import SwiftUI

// Watch background — deep ink ground + warm amber spill from where Regis sits
// + a handful of faint stars.
//
// Implementation note: every element must be sized RELATIVE to the parent
// (GeometryReader) — never with an explicit pt width larger than the watch
// screen. An oversized child causes the enclosing ZStack to grow beyond the
// screen, which centers content in a frame wider than the visible area and
// crops it on both sides. (Same bug pattern as the iOS app's RoomBackground.)

struct WatchBackground: View {
    var mood: WatchMood
    var intensity: Double = 1.0

    var body: some View {
        GeometryReader { geo in
            ZStack {
                // Deep ink radial ground — darker at edges
                RadialGradient(
                    colors: [
                        Color(red: 0x1A / 255.0, green: 0x1D / 255.0, blue: 0x30 / 255.0),
                        Color(red: 0x0B / 255.0, green: 0x0D / 255.0, blue: 0x1C / 255.0),
                        Color(red: 0x04 / 255.0, green: 0x05 / 255.0, blue: 0x0B / 255.0),
                    ],
                    center: UnitPoint(x: 0.5, y: 1.0),
                    startRadius: 20,
                    endRadius: max(geo.size.width, geo.size.height) * 1.2
                )

                // Warm spill from Regis position (upper-center) — sized to fit
                // the visible area, not a hardcoded value larger than it.
                let color = mood.hueColor
                Circle()
                    .fill(
                        RadialGradient(
                            colors: [
                                color.opacity(0.35 * intensity),
                                color.opacity(0.14 * intensity),
                                .clear,
                            ],
                            center: .center,
                            startRadius: 0,
                            endRadius: geo.size.width * 0.55
                        )
                    )
                    .frame(width: geo.size.width * 1.1, height: geo.size.height * 0.6)
                    .position(x: geo.size.width / 2, y: geo.size.height * 0.30)
                    .blur(radius: 8)

                StarsField()
            }
        }
        .ignoresSafeArea()
        .allowsHitTesting(false)
    }
}

private struct StarsField: View {
    private let stars: [(x: Double, y: Double)] = [
        (0.22, 0.18), (0.78, 0.28), (0.12, 0.72), (0.88, 0.68), (0.48, 0.12),
    ]
    var body: some View {
        GeometryReader { geo in
            ForEach(0..<stars.count, id: \.self) { i in
                Circle()
                    .fill(Color(red: 1.0, green: 230/255.0, blue: 180/255.0).opacity(0.55))
                    .frame(width: 1, height: 1)
                    .position(
                        x: stars[i].x * geo.size.width,
                        y: stars[i].y * geo.size.height
                    )
            }
        }
        .allowsHitTesting(false)
    }
}
