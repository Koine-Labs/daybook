import SwiftUI

// One recent Regis observation. Tappable — should open the thread.

struct RecentObservationCard: View {
    var text: String
    var timeAgo: String
    var observationNo: Int
    var onTap: () -> Void = {}

    @Environment(Theme.self) private var theme

    var body: some View {
        Button(action: onTap) {
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 8) {
                    WispMark(size: 14, mode: theme.mode)
                    Text("regis noticed · \(timeAgo)")
                        .dbEyebrow(theme.ink3)
                }

                Text("\u{201C}\(text)\u{201D}")
                    .regisVoice(theme.voice, size: 22)
                    .multilineTextAlignment(.leading)
                    .lineLimit(nil)

                Divider()
                    .background(theme.edge)
                    .padding(.top, 4)

                HStack {
                    Text("observation no. \(observationNo)")
                        .dbMeta(theme.ink3)
                    Spacer()
                    Text("OPEN THREAD →")
                        .dbMeta(theme.amber)
                }
            }
            .padding(.vertical, 18)
            .padding(.horizontal, 20)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(theme.card)
            .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .strokeBorder(theme.edge, lineWidth: 0.5)
            )
        }
        .buttonStyle(.plain)
    }
}
