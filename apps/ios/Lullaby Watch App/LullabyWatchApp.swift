import SwiftUI

@main
struct LullabyWatchApp: App {
    @State private var coordinator = WatchSessionCoordinator()

    var body: some Scene {
        WindowGroup {
            WatchRootView(coordinator: coordinator)
        }
    }
}
