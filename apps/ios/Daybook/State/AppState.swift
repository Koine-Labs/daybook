import SwiftUI

// AppState — minimal root state container for the v2 clean-slate iOS app.
//
// The v1 UI iteration (tabs + cards + wisp wandering across screens) lives
// archived under apps/ios/_archive_v1_ui/. This is the foundation for the
// next direction: single-surface-that-morphs around a persistent fireball
// (Regis as visible presence).

@Observable
final class AppState {
    // HTTP client pointed at the FastAPI bridge. Uses `APIClient.shared`
    // which reads the base URL from Info.plist (`DaybookAPIBaseURL`).
    let api: APIClient = .shared

    // First /chat reply from the server seeds this. Subsequent messages reuse
    // it so the whole session shares one conversation row in Postgres.
    var conversationId: String? = nil

    // Likely future fields (deferred until the next direction settles):
    //   - var surfaceMode: SurfaceMode  // .resting / .capturing / .browsing / .settings
    //   - var fireballState: FireballState  // .idle / .listening / .composing / .alert
    //   - var settingsOpen: Bool
}
