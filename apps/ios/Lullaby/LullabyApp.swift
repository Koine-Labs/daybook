import SwiftUI
import GoogleSignIn

@main
struct LullabyApp: App {
    @State private var authManager = AuthManager()
    @State private var coordinator: PhoneSessionCoordinator
    @State private var progressionManager: ProgressionManager
    @State private var dreamStoreManager = DreamStoreManager()

    init() {
        let pm = ProgressionManager()
        let coord = PhoneSessionCoordinator()
        coord.progressionManager = pm
        _coordinator = State(initialValue: coord)
        _progressionManager = State(initialValue: pm)
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(authManager)
                .environment(coordinator)
                .environment(progressionManager)
                .environment(dreamStoreManager)
                .onOpenURL { url in
                    GIDSignIn.sharedInstance.handle(url)
                }
        }
    }
}

/// Top-level gate — shows AuthView when signed out, MainTabView when signed in.
struct RootView: View {
    @Environment(AuthManager.self) private var authManager

    var body: some View {
        Group {
            if authManager.isAuthenticated {
                MainTabView()
            } else {
                AuthView()
            }
        }
        .preferredColorScheme(.dark)
    }
}
