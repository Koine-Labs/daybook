import SwiftUI

enum TabID: String, CaseIterable, Hashable, Sendable {
    case regis
    case inner
    case archive

    var label: String {
        switch self {
        case .regis: return "regis"
        case .inner: return "inner"
        case .archive: return "archive"
        }
    }

    var usesWispMark: Bool { self == .regis }
}

struct TabBar: View {
    @Binding var selected: TabID
    let mode: ThemeMode

    private var isNight: Bool {
        mode == .witness || mode == .transit || mode == .warming
    }

    private var topBorderColor: Color {
        isNight ? Color.white.opacity(0.06) : Color.black.opacity(0.05)
    }

    private var activeColor: Color {
        isNight ? .witnessGlow : .companionInk
    }

    private var inactiveColor: Color {
        isNight ? Color(red: 232/255, green: 226/255, blue: 212/255, opacity: 0.45)
                : Color(red: 28/255, green: 26/255, blue: 23/255, opacity: 0.45)
    }

    var body: some View {
        HStack(alignment: .center, spacing: 0) {
            ForEach(TabID.allCases, id: \.self) { tab in
                tabButton(tab)
            }
        }
        .padding(.horizontal, 8)
        .padding(.top, 10)
        .padding(.bottom, 30)
        .frame(maxWidth: .infinity)
        .background {
            Rectangle()
                .fill(.ultraThinMaterial)
                .overlay(
                    (isNight ? Color(red: 7/255, green: 9/255, blue: 15/255, opacity: 0.5)
                             : Color(red: 242/255, green: 236/255, blue: 223/255, opacity: 0.3))
                )
        }
        .overlay(alignment: .top) {
            Rectangle()
                .fill(topBorderColor)
                .frame(height: 0.5)
        }
    }

    private func tabButton(_ tab: TabID) -> some View {
        let isActive = selected == tab
        let color = isActive ? activeColor : inactiveColor

        return Button {
            selected = tab
        } label: {
            VStack(spacing: 4) {
                // Fixed-height icon container so labels align baseline across
                // tabs regardless of whether the indicator is a wisp or a dot.
                ZStack {
                    if tab.usesWispMark {
                        WispMark(size: 12, mode: mode)
                            .opacity(isActive ? 1.0 : 0.7)
                    } else {
                        Circle()
                            .fill(color)
                            .frame(width: 5, height: 5)
                            .opacity(isActive ? 1.0 : 0.55)
                    }
                }
                .frame(height: 16)

                Text(tab.label)
                    .font(DBFont.sans(10.5, weight: isActive ? .semibold : .medium))
                    .tracking(0.63)
                    .foregroundStyle(color)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 6)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}
