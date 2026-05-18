import SwiftUI

struct ComposingFace: View {
    var time: String = "11:31"

    var body: some View {
        ZStack {
            RadialGradient(
                gradient: Gradient(stops: [
                    .init(color: Color(watchHex: "1C1206"), location: 0.0),
                    .init(color: Color(watchHex: "060404"), location: 0.8)
                ]),
                center: .center,
                startRadius: 0,
                endRadius: 180
            )
            .ignoresSafeArea()

            VStack {
                HStack {
                    Spacer()
                    Text(time)
                        .font(WatchFont.mono(9.5))
                        .tracking(0.76)
                        .foregroundStyle(Color.watchGlow.opacity(0.6))
                }
                .padding(.top, 4)
                .padding(.trailing, 4)

                Spacer()
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)

            VStack(spacing: 14) {
                WatchWisp(size: 36, state: .composing, mode: .witness)
                    .frame(width: 36 * 1.6, height: 36 * 1.6)

                Text("Regis is composing")
                    .font(WatchFont.serif(11.5, italic: true))
                    .tracking(0.06)
                    .foregroundStyle(Color.watchGlow.opacity(0.7))

                BreathingDots()
            }
        }
    }
}

private struct BreathingDots: View {
    @State private var opacities: [Double] = [0.6, 0.6, 0.6]

    var body: some View {
        HStack(spacing: 3) {
            ForEach(0..<3, id: \.self) { i in
                Circle()
                    .fill(Color.watchEmber)
                    .frame(width: 4, height: 4)
                    .opacity(opacities[i])
            }
        }
        .onAppear {
            for i in 0..<3 {
                withAnimation(
                    .easeInOut(duration: 0.45)
                        .repeatForever(autoreverses: true)
                        .delay(Double(i) * 0.2)
                ) {
                    opacities[i] = 1.0
                }
            }
        }
    }
}

#Preview {
    ComposingFace()
}
