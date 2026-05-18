import SwiftUI

// ContentView — clean slate.
//
// The v1 UI iteration is archived under apps/ios/_archive_v1_ui/.
//
// NEXT DIRECTION (decided 2026-05-17):
//   - Single-surface-that-morphs
//   - Mostly dark background
//   - Persistent fireball at the center — Regis as visible presence
//   - No tabs, no traditional navigation chrome
//   - Context changes around the fireball via gestures (pull / pinch / long-press)
//   - The fireball's BODY reflects what the backend Regis AI is actually
//     doing (composing / alert / idle / witnessing) — event-driven, not
//     choreographed
//   - The phone is the *visible memory* of an invisible companion that lives
//     across surfaces (phone + headphones + future BCI)
//
// For now: empty surface. Build the actual experience from a clear brief
// rather than another iteration of the wrong paradigm.

struct ContentView: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            VStack(spacing: 12) {
                Text("Daybook")
                    .font(.system(size: 18, weight: .light, design: .serif))
                    .foregroundStyle(Color(red: 0.95, green: 0.90, blue: 0.83).opacity(0.55))
                Text("clean slate · waiting for next direction")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(Color(red: 0.95, green: 0.90, blue: 0.83).opacity(0.25))
                    .tracking(1.2)
            }
        }
    }
}

#Preview {
    ContentView()
        .environment(AppState())
}
