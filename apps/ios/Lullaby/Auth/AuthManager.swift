import Foundation
import Observation

/// Manages authentication state and token lifecycle.
/// Gates the app on sign-in and persists tokens in the Keychain.
@Observable
@MainActor
final class AuthManager {
    private(set) var isAuthenticated = false
    private(set) var currentUser: UserProfile?
    private(set) var isLoading = false
    private(set) var error: String?

    let apiClient: APIClient

    private enum Keys {
        static let accessToken = "lullaby_access_token"
        static let refreshToken = "lullaby_refresh_token"
    }

    init(apiClient: APIClient = APIClient()) {
        self.apiClient = apiClient
        Task { await restoreSession() }
    }

    // MARK: - Auth actions

    /// Register a new account with email + password.
    func register(email: String, password: String, displayName: String? = nil) async {
        isLoading = true
        error = nil
        defer { isLoading = false }

        struct RegisterBody: Encodable {
            let email: String
            let password: String
            let displayName: String?
        }

        do {
            let response: AuthResponse = try await apiClient.request(
                .register,
                body: RegisterBody(email: email, password: password, displayName: displayName)
            )
            handleAuthResponse(response)
        } catch {
            self.error = error.localizedDescription
        }
    }

    /// Sign in with email + password.
    func login(email: String, password: String) async {
        isLoading = true
        error = nil
        defer { isLoading = false }

        struct LoginBody: Encodable {
            let email: String
            let password: String
        }

        do {
            let response: AuthResponse = try await apiClient.request(
                .login,
                body: LoginBody(email: email, password: password)
            )
            handleAuthResponse(response)
        } catch {
            self.error = error.localizedDescription
        }
    }

    #if DEBUG
    /// Debug-only: bypass auth for simulator UI walk-throughs. Remove before shipping.
    func debugBypassAuth() {
        currentUser = UserProfile(id: "debug", email: "debug@local", displayName: "Debug", role: "personal")
        isAuthenticated = true
    }
    #endif

    /// Sign out and clear stored tokens.
    func logout() async {
        if let refreshToken = KeychainHelper.read(key: Keys.refreshToken) {
            struct LogoutBody: Encodable { let refreshToken: String }
            try? await apiClient.requestVoid(.logout, body: LogoutBody(refreshToken: refreshToken))
        }

        KeychainHelper.delete(key: Keys.accessToken)
        KeychainHelper.delete(key: Keys.refreshToken)
        await apiClient.setTokens(access: nil, refresh: nil)

        isAuthenticated = false
        currentUser = nil
    }

    /// Sign in with Apple.
    func signInWithApple() async {
        isLoading = true
        error = nil
        defer { isLoading = false }

        do {
            let helper = AppleSignInHelper()
            let result = try await helper.signIn()

            struct AppleAuthBody: Encodable {
                let identityToken: String
                let email: String?
                let fullName: String?
            }

            let response: AuthResponse = try await apiClient.request(
                .appleAuth,
                body: AppleAuthBody(
                    identityToken: result.identityToken,
                    email: result.email,
                    fullName: result.fullName
                )
            )
            handleAuthResponse(response)
        } catch {
            self.error = error.localizedDescription
        }
    }

    /// Sign in with Google.
    func signInWithGoogle() async {
        isLoading = true
        error = nil
        defer { isLoading = false }

        do {
            let helper = GoogleSignInHelper()
            let result = try await helper.signIn()

            struct GoogleAuthBody: Encodable { let idToken: String }

            let response: AuthResponse = try await apiClient.request(
                .googleAuth,
                body: GoogleAuthBody(idToken: result.idToken)
            )
            handleAuthResponse(response)
        } catch {
            self.error = error.localizedDescription
        }
    }

    // MARK: - Internal

    private func restoreSession() async {
        guard let accessToken = KeychainHelper.read(key: Keys.accessToken),
              let refreshToken = KeychainHelper.read(key: Keys.refreshToken) else {
            return
        }

        await apiClient.setTokens(access: accessToken, refresh: refreshToken)
        await apiClient.setTokenRefreshHandler { [weak self] newAccess, newRefresh in
            try? KeychainHelper.save(key: Keys.accessToken, value: newAccess)
            try? KeychainHelper.save(key: Keys.refreshToken, value: newRefresh)
            await self?.apiClient.setTokens(access: newAccess, refresh: newRefresh)
        }

        // Verify tokens are still valid by fetching profile
        do {
            let profile: UserProfile = try await apiClient.request(.me)
            currentUser = profile
            isAuthenticated = true
        } catch {
            // Tokens invalid — clear them
            KeychainHelper.delete(key: Keys.accessToken)
            KeychainHelper.delete(key: Keys.refreshToken)
            await apiClient.setTokens(access: nil, refresh: nil)
        }
    }

    private func handleAuthResponse(_ response: AuthResponse) {
        try? KeychainHelper.save(key: Keys.accessToken, value: response.accessToken)
        try? KeychainHelper.save(key: Keys.refreshToken, value: response.refreshToken)

        Task {
            await apiClient.setTokens(access: response.accessToken, refresh: response.refreshToken)
            await apiClient.setTokenRefreshHandler { [weak self] newAccess, newRefresh in
                try? KeychainHelper.save(key: Keys.accessToken, value: newAccess)
                try? KeychainHelper.save(key: Keys.refreshToken, value: newRefresh)
                await self?.apiClient.setTokens(access: newAccess, refresh: newRefresh)
            }
        }

        currentUser = response.user
        isAuthenticated = true
    }
}

// MARK: - Response types

struct UserProfile: Codable, Sendable {
    let id: String
    let email: String
    let displayName: String?
    let role: String
}

struct AuthResponse: Codable {
    let user: UserProfile
    let accessToken: String
    let refreshToken: String
    let expiresIn: Int
}
