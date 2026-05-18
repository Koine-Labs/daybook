import SwiftUI

struct WitnessFace: View {
    var time: String = "02:34"
    var cue: String = "You are dreaming."
    var whisperIndex: Int = 1
    var whisperTotal: Int = 4

    var body: some View {
        ZStack {
            RadialGradient(
                gradient: Gradient(stops: [
                    .init(color: Color(watchHex: "1C1206"), location: 0.0),
                    .init(color: Color(watchHex: "050304"), location: 0.8)
                ]),
                center: .center,
                startRadius: 0,
                endRadius: 180
            )
            .ignoresSafeArea()

            VStack {
                Text("REM \u{00B7} WHISPER \(whisperIndex) of \(whisperTotal)")
                    .font(WatchFont.mono(9))
                    .tracking(1.08)
                    .foregroundStyle(Color.watchGlow.opacity(0.4))
                    .padding(.top, 10)

                Spacer()

                Text(time)
                    .font(WatchFont.mono(9))
                    .tracking(1.08)
                    .foregroundStyle(Color.watchGlow.opacity(0.35))
                    .padding(.bottom, 10)
            }

            VStack(spacing: 18) {
                WatchWisp(size: 32, state: .witnessing, mode: .witness)
                    .frame(width: 32 * 1.6, height: 32 * 1.6)

                Text("\u{201C}\(cue)\u{201D}")
                    .font(WatchFont.serif(18, italic: true))
                    .tracking(0.09)
                    .foregroundStyle(Color.watchGlow)
                    .multilineTextAlignment(.center)
                    .lineSpacing(1)
                    .padding(.horizontal, 16)
            }
        }
    }
}

#Preview {
    WitnessFace()
}
