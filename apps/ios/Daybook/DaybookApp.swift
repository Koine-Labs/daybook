import SwiftUI

@main
struct DaybookApp: App {
    @State private var appState = AppState()

    // MARK: - HealthKit (#13)
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(appState)
                .preferredColorScheme(.dark)
                // MARK: - HealthKit (#13)
                // Request auth + first sample sweep + start refresh timer.
                .task { appState.startHealthKit() }
                // Re-sync on foreground and again on background-bounce so
                // backgrounded HealthKit deltas land promptly.
                .onChange(of: scenePhase) { _, phase in
                    if phase == .active || phase == .background {
                        Task { await appState.uploadHealthSnapshot() }
                    }
                }
                // MARK: - WatchConnectivity (#14)
                // Activate the session once on launch. Idempotent.
                .task {
                    appState.bindWatch()
                    #if DEBUG
                    print("watch wire smoke: \(WatchMessage.runRoundTripSmoke())")
                    #endif
                }
        }
    }
}
