import SwiftUI

// ContentView — clean slate.
//
// The v1 UI iteration is archived under apps/ios/_archive_v1_ui/.
// A first attempt at a sprite-sheet-based fire wisp (Components/WispCharacter
// + Assets.xcassets/wisp_idle_*) was also erased — wrong direction.
//
// CONFIRMED next direction:
//   - Single-surface-that-morphs
//   - Mostly dark
//   - The flame creature (Regis) is to be built procedurally — SwiftUI
//     shapes + Metal shaders — NOT sliced from AI-generated sprites.
//   - Claude Design will deliver the visual spec for the rebuild.
//
// For now: empty surface. Awaiting Claude Design's brief.

struct ContentView: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            VStack(spacing: 12) {
                Text("Daybook")
                    .font(.system(size: 18, weight: .light, design: .serif))
                    .foregroundStyle(Color(red: 0.95, green: 0.90, blue: 0.83).opacity(0.55))
                Text("awaiting design")
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
