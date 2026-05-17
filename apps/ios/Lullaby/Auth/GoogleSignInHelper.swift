import Foundation
import GoogleSignIn
#if canImport(UIKit)
import UIKit
#endif

/// Bridge for Google Sign-In SDK (GoogleSignIn-iOS v8).
/// Presents the Google sign-in sheet and returns the ID token for server verification.
@MainActor
final class GoogleSignInHelper {

    struct GoogleSignInResult: Sendable {
        let idToken: String
        let email: String
        let displayName: String?
    }

    private static let clientID = "624473694544-qn9hu79bp2q2uvoosl4kni55hii2m5gp.apps.googleusercontent.com"

    /// Trigger Google Sign-In and return the ID token.
    func signIn() async throws -> GoogleSignInResult {
        guard let windowScene = UIApplication.shared.connectedScenes.first as? UIWindowScene,
              let rootVC = windowScene.windows.first?.rootViewController else {
            throw APIError.validationError("No root view controller available")
        }

        let config = GIDConfiguration(clientID: Self.clientID)
        GIDSignIn.sharedInstance.configuration = config

        let result = try await GIDSignIn.sharedInstance.signIn(withPresenting: rootVC)

        guard let idToken = result.user.idToken?.tokenString else {
            throw APIError.unauthorized
        }

        return GoogleSignInResult(
            idToken: idToken,
            email: result.user.profile?.email ?? "",
            displayName: result.user.profile?.name
        )
    }
}
