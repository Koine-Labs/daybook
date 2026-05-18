import SwiftUI

// Big soft serif-italic invitation. The primary capture affordance on Now.

struct QuickCaptureButton: View {
    var label: String = "tell me something"
    var action: () -> Void = {}

    @Environment(Theme.self) private var theme

    var body: some View {
        Button(action: action) {
            HStack(alignment: .center, spacing: 14) {
                Text(label)
                    .font(.custom("Charter-Italic", size: 22, relativeTo: .title2))
                    .italic()
                    .foregroundStyle(theme.ink2)
                    .lineLimit(2)
                    .frame(maxWidth: .infinity, alignment: .leading)

                ZStack {
                    Circle()
                        .fill(
                            RadialGradient(
                                colors: [
                                    Color(red: 243/255, green: 215/255, blue: 176/255),
                                    theme.amber
                                ],
                                center: UnitPoint(x: 0.5, y: 0.4),
                                startRadius: 0,
                                endRadius: 26
                            )
                        )
                        .frame(width: 42, height: 42)
                        .shadow(color: theme.amber.opacity(0.25), radius: 7, x: 0, y: 4)

                    // mic icon
                    VStack(spacing: 0) {
                        RoundedRectangle(cornerRadius: 3)
                            .fill(Color(red: 26/255, green: 14/255, blue: 5/255))
                            .frame(width: 6, height: 10)
                        Image(systemName: "")  // intentional empty — we use stack glyph
                            .frame(height: 0)
                    }
                    .overlay(alignment: .bottom) {
                        Image(systemName: "mic.fill")
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundStyle(Color(red: 26/255, green: 14/255, blue: 5/255))
                            .offset(y: -10)
                    }
                }
            }
            .padding(.vertical, 18)
            .padding(.horizontal, 22)
            .frame(maxWidth: .infinity)
            .background(theme.card)
            .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 22, style: .continuous)
                    .strokeBorder(theme.edge, lineWidth: 0.5)
            )
            .shadow(color: .black.opacity(0.04), radius: 12, x: 0, y: 8)
        }
        .buttonStyle(.plain)
    }
}
