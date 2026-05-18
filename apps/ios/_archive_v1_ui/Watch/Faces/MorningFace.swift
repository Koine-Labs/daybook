import SwiftUI

struct MorningFace: View {
    var time: String = "06:47"

    var body: some View {
        ZStack {
            LinearGradient(
                gradient: Gradient(stops: [
                    .init(color: Color(watchHex: "1A1108"), location: 0.0),
                    .init(color: Color(watchHex: "2A1A0C"), location: 0.6),
                    .init(color: Color(watchHex: "3A230F"), location: 1.0)
                ]),
                startPoint: .top,
                endPoint: .bottom
            )
            .ignoresSafeArea()

            VStack(alignment: .leading, spacing: 0) {
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("morning")
                            .watchMeta(Color.watchMorningInk.opacity(0.55), size: 8.5)
                        Text(time)
                            .font(WatchFont.serif(28))
                            .foregroundStyle(Color.watchMorningInk)
                            .monospacedDigit()
                            .lineLimit(1)
                    }
                    Spacer()
                    WatchWisp(size: 20, state: .composing, mode: .witness)
                        .frame(width: 32, height: 32)
                }

                Spacer()

                VStack(alignment: .leading, spacing: 12) {
                    WatchRegisQuote("\u{201C}So. What did you bring back?\u{201D}", size: 13, color: .watchGlow)

                    HStack(spacing: 6) {
                        Circle()
                            .fill(Color.watchEmber)
                            .frame(width: 6, height: 6)
                        Text("hold to speak")
                            .font(WatchFont.sans(10.5))
                            .foregroundStyle(Color.watchGlow)
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 7)
                    .frame(maxWidth: .infinity)
                    .background(
                        Capsule().fill(Color.watchGlow.opacity(0.12))
                    )
                    .overlay(
                        Capsule().stroke(Color.watchGlow.opacity(0.2), lineWidth: 0.5)
                    )
                }
            }
            .padding(14)
        }
    }
}

#Preview {
    MorningFace()
}
