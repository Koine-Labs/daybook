import SwiftUI

struct SectionHeader: View {
    var title: String
    var meta: String? = nil
    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(title)
                .font(Fonts.body(19, .medium))
                .tracking(-0.3)
                .foregroundStyle(Theme.pearl)
            Spacer()
            if let meta = meta {
                Text(meta).labelTiny()
            }
        }
    }
}
