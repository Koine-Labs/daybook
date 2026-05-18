import SwiftUI

enum WispState: String, Hashable, Sendable {
    case dormant
    case listening
    case composing
    case witnessing
    case held
}

// WispView — the Regis glyph. SwiftUI translation of wisp.jsx.
// Body is a teardrop with two horn tufts, two eye-dots, a radial gradient
// fill, and a soft outer glow halo. Breathes per state; ripples only when
// listening; eye-dots blink during composing; eye-dots can ALSO offset toward
// a gaze target (driven by the WispAgent's gazeOffset).
struct WispView: View {
    let size: CGFloat
    let state: WispState
    let mode: ThemeMode
    let gazeOffset: CGSize

    init(
        size: CGFloat = 28,
        state: WispState = .dormant,
        mode: ThemeMode = .companion,
        gazeOffset: CGSize = .zero
    ) {
        self.size = size
        self.state = state
        self.mode = mode
        self.gazeOffset = gazeOffset
    }

    @State private var breathOn: Bool = false
    @State private var ripple1On: Bool = false
    @State private var ripple2On: Bool = false
    @State private var eyesOn: Bool = false

    private var isNight: Bool {
        mode == .witness || state == .witnessing
    }

    private var core: Color { isNight ? .witnessGlow : .companionAmberSoft }
    private var amber: Color { isNight ? .witnessEmber : .companionAmber }
    private var glow: Color {
        isNight ? Color(red: 1, green: 203/255, blue: 149/255, opacity: 0.45)
                : Color(red: 201/255, green: 124/255, blue: 58/255, opacity: 0.35)
    }
    private var glowOuter: Color {
        isNight ? Color(red: 232/255, green: 148/255, blue: 86/255, opacity: 0.20)
                : Color(red: 201/255, green: 124/255, blue: 58/255, opacity: 0.14)
    }

    private var breathDuration: Double {
        switch state {
        case .listening: return 1.4
        case .composing: return 0.9
        case .witnessing: return 3.6
        case .held: return 6.0
        case .dormant: return 4.2
        }
    }

    private var eyeBlinkDuration: Double? {
        switch state {
        case .composing: return 0.7
        case .listening: return 1.2
        default: return nil
        }
    }

    private var restingEyeOpacity: Double {
        state == .dormant ? 0.55 : 0.85
    }

    private var container: CGFloat { size * 1.6 }
    private var bodyHeight: CGFloat { size * 1.15 }
    private var haloSize: CGFloat { size * 1.55 }

    var body: some View {
        ZStack {
            if state == .listening {
                ripple(delay: 0)
                ripple(delay: 0.6)
            }

            // Outer glow halo, breathing
            Circle()
                .fill(
                    RadialGradient(
                        gradient: Gradient(stops: [
                            .init(color: glow, location: 0.0),
                            .init(color: glowOuter, location: 0.35),
                            .init(color: .clear, location: 0.7)
                        ]),
                        center: .center,
                        startRadius: 0,
                        endRadius: haloSize / 2
                    )
                )
                .frame(width: haloSize, height: haloSize)
                .blur(radius: 2)
                .scaleEffect(breathScale)
                .opacity(breathOpacity)

            // SVG-equivalent body using SwiftUI Paths.
            wispBody
                .frame(width: size, height: bodyHeight)
                .scaleEffect(breathScale)
                .opacity(breathOpacity)
        }
        .frame(width: container, height: container)
        .onAppear { startAnimations() }
        .onChange(of: state) { _, _ in restartAnimations() }
    }

    private var breathScale: CGFloat {
        let high: CGFloat = state == .listening ? 1.18 : 1.05
        return breathOn ? high : 1.0
    }

    private var breathOpacity: Double {
        let low: Double = state == .listening ? 0.7 : 0.88
        return breathOn ? 1.0 : low
    }

    private func ripple(delay: Double) -> some View {
        Circle()
            .stroke(glow, lineWidth: 1)
            .frame(width: container * 0.6, height: container * 0.6)
            .scaleEffect(rippleScale(delayed: delay))
            .opacity(rippleOpacity(delayed: delay))
    }

    private func rippleScale(delayed: Double) -> CGFloat {
        let on = delayed == 0 ? ripple1On : ripple2On
        return on ? 2.2 : 0.5
    }

    private func rippleOpacity(delayed: Double) -> Double {
        let on = delayed == 0 ? ripple1On : ripple2On
        return on ? 0 : 0.55
    }

    private var wispBody: some View {
        ZStack {
            // Horns (soft amber tufts above the body)
            WispHornsShape()
                .fill(amber.opacity(0.55))

            // Teardrop body with the radial gradient fill
            WispTeardropShape()
                .fill(
                    RadialGradient(
                        gradient: Gradient(stops: [
                            .init(color: .wispHighlight, location: 0.0),
                            .init(color: core, location: 0.35),
                            .init(color: amber, location: 0.75),
                            .init(color: amber.opacity(0), location: 1.0)
                        ]),
                        center: UnitPoint(x: 0.5, y: 0.55),
                        startRadius: 0,
                        endRadius: size * 0.55
                    )
                )

            // Inner highlight (off-center, gives a glassy roundness)
            Ellipse()
                .fill(Color.wispHighlight.opacity(0.5))
                .frame(width: size * 0.175, height: size * 0.1)
                .offset(x: -size * 0.10, y: -size * 0.16)

            // Eye dots — offset by gaze for tracking. Y baseline ~ 0.10*size.
            HStack(spacing: size * 0.225) {
                Circle().fill(Color.wispEyeDot).frame(width: size * 0.07, height: size * 0.07)
                Circle().fill(Color.wispEyeDot).frame(width: size * 0.07, height: size * 0.07)
            }
            .opacity(eyesOn ? 1.0 : restingEyeOpacity)
            .offset(x: gazeOffset.width, y: size * 0.10 + gazeOffset.height)
            .animation(.easeOut(duration: 0.25), value: gazeOffset)
        }
    }

    private func startAnimations() {
        breathOn = false
        ripple1On = false
        ripple2On = false
        eyesOn = false

        withAnimation(.easeInOut(duration: breathDuration / 2).repeatForever(autoreverses: true)) {
            breathOn = true
        }

        if state == .listening {
            withAnimation(.easeOut(duration: 1.8).repeatForever(autoreverses: false)) {
                ripple1On = true
            }
            withAnimation(.easeOut(duration: 1.8).repeatForever(autoreverses: false).delay(0.6)) {
                ripple2On = true
            }
        }

        if let dur = eyeBlinkDuration {
            withAnimation(.easeInOut(duration: dur / 2).repeatForever(autoreverses: true)) {
                eyesOn = true
            }
        }
    }

    private func restartAnimations() {
        withAnimation(.linear(duration: 0.001)) {
            breathOn = false
            ripple1On = false
            ripple2On = false
            eyesOn = false
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.02) {
            startAnimations()
        }
    }
}

// Teardrop body — approximates the SVG cubic path:
// M20 6 C 10 6, 6 16, 6 24 C 6 33, 12 40, 20 40 C 28 40, 34 33, 34 24 C 34 16, 30 6, 20 6 Z
// Original viewBox is 0 0 40 46. We draw to the available rect (width, height),
// mapping x: x/40, y: y/46.
struct WispTeardropShape: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        let w = rect.width
        let h = rect.height

        // viewBox units → rect units
        func p(_ x: CGFloat, _ y: CGFloat) -> CGPoint {
            CGPoint(x: rect.minX + (x / 40) * w, y: rect.minY + (y / 46) * h)
        }

        path.move(to: p(20, 6))
        path.addCurve(to: p(6, 24), control1: p(10, 6), control2: p(6, 16))
        path.addCurve(to: p(20, 40), control1: p(6, 33), control2: p(12, 40))
        path.addCurve(to: p(34, 24), control1: p(28, 40), control2: p(34, 33))
        path.addCurve(to: p(20, 6), control1: p(34, 16), control2: p(30, 6))
        path.closeSubpath()
        return path
    }
}

// Two horn tufts (small triangles flanking the top of the teardrop).
// Original SVG: M14 10 L11 4 L17 8 Z  and  M26 10 L29 4 L23 8 Z
struct WispHornsShape: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        let w = rect.width
        let h = rect.height

        func p(_ x: CGFloat, _ y: CGFloat) -> CGPoint {
            CGPoint(x: rect.minX + (x / 40) * w, y: rect.minY + (y / 46) * h)
        }

        // Left horn
        path.move(to: p(14, 10))
        path.addLine(to: p(11, 4))
        path.addLine(to: p(17, 8))
        path.closeSubpath()

        // Right horn
        path.move(to: p(26, 10))
        path.addLine(to: p(29, 4))
        path.addLine(to: p(23, 8))
        path.closeSubpath()

        return path
    }
}
