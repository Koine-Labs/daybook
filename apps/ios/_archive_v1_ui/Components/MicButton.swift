import SwiftUI

// MicButton — the round recording button. Port of shell.jsx MicButton.
// Pulses when active (the listening-mic state). No-op handler for now.
struct MicButton: View {
    let size: CGFloat
    let active: Bool
    let action: () -> Void

    init(size: CGFloat = 56, active: Bool = false, action: @escaping () -> Void = {}) {
        self.size = size
        self.active = active
        self.action = action
    }

    @State private var pulseOn = false

    var body: some View {
        Button(action: action) {
            ZStack {
                Circle()
                    .fill(
                        RadialGradient(
                            gradient: Gradient(stops: active
                                ? [.init(color: Color(hex: "FFE9CC"), location: 0),
                                   .init(color: Color(hex: "E89456"), location: 0.7)]
                                : [.init(color: Color(hex: "F3D7B0"), location: 0),
                                   .init(color: Color(hex: "C97C3A"), location: 0.75)]
                            ),
                            center: UnitPoint(x: 0.5, y: 0.4),
                            startRadius: 0,
                            endRadius: size / 2
                        )
                    )
                    .frame(width: size, height: size)
                    .shadow(
                        color: active
                            ? Color(red: 232/255, green: 148/255, blue: 86/255, opacity: pulseOn ? 0.6 : 0.4)
                            : Color(red: 201/255, green: 124/255, blue: 58/255, opacity: 0.35),
                        radius: active ? (pulseOn ? 16 : 12) : 8,
                        x: 0,
                        y: active ? 0 : 4
                    )

                micGlyph
            }
        }
        .buttonStyle(.plain)
        .onAppear {
            if active {
                withAnimation(.easeInOut(duration: 0.8).repeatForever(autoreverses: true)) {
                    pulseOn.toggle()
                }
            }
        }
    }

    private var micGlyph: some View {
        // Simple mic icon — capsule + stand. Color matches the dark eye-dot.
        ZStack {
            RoundedRectangle(cornerRadius: size * 0.085)
                .fill(Color.wispEyeDot)
                .frame(width: size * 0.18, height: size * 0.27)
                .offset(y: -size * 0.06)

            Path { p in
                let w = size * 0.45
                let h = size * 0.08
                let centerX = size / 2
                let topY = size * 0.55
                p.move(to: CGPoint(x: centerX - w/2, y: topY))
                p.addQuadCurve(
                    to: CGPoint(x: centerX + w/2, y: topY),
                    control: CGPoint(x: centerX, y: topY + h * 4)
                )
            }
            .stroke(Color.wispEyeDot, style: StrokeStyle(lineWidth: size * 0.04, lineCap: .round))

            // Stand
            Rectangle()
                .fill(Color.wispEyeDot)
                .frame(width: size * 0.04, height: size * 0.10)
                .offset(y: size * 0.30)

            Rectangle()
                .fill(Color.wispEyeDot)
                .frame(width: size * 0.18, height: size * 0.04)
                .offset(y: size * 0.36)
        }
    }
}
