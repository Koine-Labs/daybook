import SwiftUI

struct ListeningFace: View {
    var time: String = "11:24"

    var body: some View {
        ZStack {
            RadialGradient(
                gradient: Gradient(stops: [
                    .init(color: Color(watchHex: "2A1A08"), location: 0.0),
                    .init(color: Color(watchHex: "0A0807"), location: 0.7)
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
                        .font(WatchFont.mono(10))
                        .tracking(0.8)
                        .foregroundStyle(Color.watchGlow.opacity(0.6))
                }
                .padding(.top, 4)
                .padding(.trailing, 4)

                Spacer()
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)

            VStack(spacing: 18) {
                WatchWisp(size: 42, state: .listening, mode: .witness)
                    .frame(width: 42 * 1.6, height: 42 * 1.6)

                Text("listening")
                    .font(WatchFont.serif(12, italic: true))
                    .tracking(0.06)
                    .foregroundStyle(Color.watchGlow.opacity(0.85))
            }
        }
    }
}

#Preview {
    ListeningFace()
}
