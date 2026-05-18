import SwiftUI

// AppState — minimal root state container for the v2 clean-slate iOS app.
//
// The v1 UI iteration (tabs + cards + wisp wandering across screens) lives
// archived under apps/ios/_archive_v1_ui/. This is the foundation for the
// next direction: single-surface-that-morphs around a persistent fireball
// (Regis as visible presence).

@Observable
final class AppState {
    // Placeholder — will grow as the new direction takes shape.
    // Likely fields once we know more:
    //   - var surfaceMode: SurfaceMode  // .resting / .capturing / .browsing / .settings
    //   - var fireballState: FireballState  // .idle / .listening / .composing / .alert
    //   - var conversationId: String?
    //   - var settingsOpen: Bool
}
