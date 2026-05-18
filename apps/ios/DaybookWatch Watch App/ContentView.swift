import SwiftUI

// Daybook Watch — clean slate. v1 face iteration archived under
// apps/ios/_archive_v1_ui/Watch/. Will be rebuilt alongside the iOS v2
// direction (single-surface fireball; watch will likely just be sensor
// stream + haptic cues + minimal complication, not full face designs).

struct ContentView: View {
    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            VStack(spacing: 4) {
                Text("Daybook")
                    .font(.system(size: 14, weight: .light, design: .serif))
                    .foregroundStyle(Color(red: 0.95, green: 0.90, blue: 0.83).opacity(0.55))
                Text("waiting")
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(Color(red: 0.95, green: 0.90, blue: 0.83).opacity(0.30))
                    .tracking(1.0)
            }
        }
        .ignoresSafeArea()
    }
}

#Preview { ContentView() }
