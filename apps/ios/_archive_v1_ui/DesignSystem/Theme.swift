import SwiftUI

enum ThemeMode: String, Hashable, Sendable {
    case companion
    case witness
    case transit
    case warming
}

// Theme is an @Observable instead of EnvironmentValue so screens can mutate it
// without needing a custom binding ceremony. It still flows via .environment(theme).
@Observable
final class Theme {
    var mode: ThemeMode = .companion

    var bg: Color { isNightish ? .witnessBg : .companionBg }
    var bg2: Color { isNightish ? .witnessBg2 : .companionBg2 }
    var card: Color { isNightish ? .witnessCard : .companionCard }
    var edge: Color { isNightish ? .witnessEdge : .companionEdge }
    var ink: Color { isNightish ? .witnessInk : .companionInk }
    var ink2: Color { isNightish ? .witnessInk2 : .companionInk2 }
    var ink3: Color { isNightish ? .witnessInk3 : .companionInk3 }
    var amber: Color { isNightish ? .witnessEmber : .companionAmber }
    var amberSoft: Color { isNightish ? .witnessGlow : .companionAmberSoft }
    // The voice color is what Regis "speaks in" — warm ink on paper, warm glow at night.
    var voice: Color { isNightish ? .witnessGlow : .companionAmberInk }
    var violet: Color { isNightish ? .witnessViolet : .companionViolet }

    // Witness, transit, and warming all share the night palette per app.jsx logic.
    private var isNightish: Bool {
        mode == .witness || mode == .transit || mode == .warming
    }
}
