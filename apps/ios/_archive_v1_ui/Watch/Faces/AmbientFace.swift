import SwiftUI

struct AmbientFace: View {
    var time: String = "11:24"
    var date: String = "tue 17 may"

    var body: some View {
        ZStack {
            RadialGradient(
                gradient: Gradient(stops: [
                    .init(color: Color(watchHex: "2A1A08"), location: 0.0),
                    .init(color: Color(watchHex: "0A0807"), location: 0.6),
                    .init(color: .black, location: 1.0)
                ]),
                center: UnitPoint(x: 0.5, y: 0.8),
                startRadius: 0,
                endRadius: 180
            )
            .ignoresSafeArea()

            VStack(alignment: .leading, spacing: 0) {
                HStack(alignment: .top) {
                    Text(date)
                        .watchMeta(Color.watchInk.opacity(0.55), size: 9)
                    Spacer()
                    WatchWisp(size: 16, state: .dormant, mode: .witness)
                        .frame(width: 26, height: 26)
                }

                Spacer(minLength: 4)

                VStack(alignment: .leading, spacing: 10) {
                    Text(time)
                        .font(WatchFont.serif(56))
                        .tracking(-1.68)
                        .foregroundStyle(Color.watchGlow)
                        .monospacedDigit()
                        .lineLimit(1)
                        .minimumScaleFactor(0.7)

                    WatchRegisQuote("\u{201C}I've got the watch.\u{201D}", size: 12, color: .watchEmber)
                }

                Spacer(minLength: 4)

                HStack {
                    Text("oura \u{00B7} 87")
                        .font(WatchFont.mono(8.5))
                        .tracking(0.85)
                        .foregroundStyle(Color.watchInk.opacity(0.4))
                    Spacer()
                    Text("14 nights")
                        .font(WatchFont.mono(8.5))
                        .tracking(0.85)
                        .foregroundStyle(Color.watchInk.opacity(0.4))
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
            .foregroundStyle(Color.watchInk)
        }
    }
}

#Preview {
    AmbientFace()
}
