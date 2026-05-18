import SwiftUI

// WispAnchor — semantic identifier for a location the wisp can visit.
//
// CHANGED in v2: anchors no longer overwrite each other. Screens declare
// MULTIPLE anchors (input, header, recent-message-area, settings-button, etc.)
// and the WispBrain picks among them based on curiosity / freshness / context.

enum WispAnchor: String, Hashable, Sendable {
    /// Top-right corner — settings entry point area.
    case settingsCorner
    /// Top-left of header — Regis identity area.
    case headerLeft
    /// Centered above the chat input — used when user is focused on input.
    case inputComposing
    /// The most recent message in the thread.
    case latestMessage
    /// The top of the chat thread (older context).
    case threadTop
    /// Centered in the screen — meditation / empty-state.
    case centerStage
    /// Top center, drifting — pre-sleep or threshold.
    case driftTop
    /// Center, witness-mode — immersive night.
    case nightCenter
    /// An edge drift point — used when wisp is bored.
    case edgeLeft, edgeRight, edgeTop, edgeBottom
    /// Hidden — wisp doesn't render (used by immersive screens).
    case hidden

    /// Suggested rendering size for this anchor context.
    var defaultSize: CGFloat {
        switch self {
        case .headerLeft, .settingsCorner, .latestMessage, .threadTop: return 24
        case .inputComposing: return 30
        case .centerStage: return 56
        case .driftTop: return 36
        case .nightCenter: return 48
        case .edgeLeft, .edgeRight, .edgeTop, .edgeBottom: return 22
        case .hidden: return 0
        }
    }

    var defaultAnimationState: WispState {
        switch self {
        case .nightCenter: return .witnessing
        case .inputComposing: return .composing
        default: return .dormant
        }
    }

    /// How interesting is this anchor by default? Higher = more curious-attractive.
    /// The WispBrain weights its random walk by this.
    var baseInterest: Double {
        switch self {
        case .inputComposing: return 0.0  // only visit when user is typing
        case .latestMessage: return 1.0   // fresh content is interesting
        case .threadTop:     return 0.3
        case .headerLeft:    return 0.6
        case .settingsCorner: return 0.4
        case .centerStage:   return 0.5
        case .edgeLeft, .edgeRight, .edgeTop, .edgeBottom: return 0.2
        default: return 0.5
        }
    }

    /// Edges the wisp drifts to when bored — chosen by WispBrain only when boredom is high.
    static var edgeAnchors: [WispAnchor] {
        [.edgeLeft, .edgeRight, .edgeTop, .edgeBottom]
    }
}

// MARK: - Preference key (now COLLECTS multiple anchors)

struct WispAnchorEntry: Equatable {
    let anchor: WispAnchor
    let frame: CGRect
}

struct WispAnchorKey: PreferenceKey {
    static var defaultValue: [WispAnchorEntry] = []

    static func reduce(value: inout [WispAnchorEntry], nextValue: () -> [WispAnchorEntry]) {
        value.append(contentsOf: nextValue())
    }
}

extension View {
    /// Declare this view as a candidate target for the wisp's curiosity.
    /// The WispBrain may visit it, or may not, depending on its mood.
    func wispAnchor(_ anchor: WispAnchor, active: Bool = true) -> some View {
        background(
            GeometryReader { proxy in
                Color.clear
                    .preference(
                        key: WispAnchorKey.self,
                        value: active
                            ? [WispAnchorEntry(anchor: anchor, frame: proxy.frame(in: .global))]
                            : []
                    )
            }
        )
    }
}
