import AuthenticationServices
import Foundation

/// Handles Sign in with Apple via ASAuthorizationController.
@MainActor
final class AppleSignInHelper: NSObject, ASAuthorizationControllerDelegate {
    private var continuation: CheckedContinuation<AppleSignInResult, Error>?

    struct AppleSignInResult {
        let identityToken: String
        let email: String?
        let fullName: String?
    }

    /// Trigger Sign in with Apple and return the credential.
    func signIn() async throws -> AppleSignInResult {
        return try await withCheckedThrowingContinuation { continuation in
            self.continuation = continuation

            let provider = ASAuthorizationAppleIDProvider()
            let request = provider.createRequest()
            request.requestedScopes = [.email, .fullName]

            let controller = ASAuthorizationController(authorizationRequests: [request])
            controller.delegate = self
            controller.performRequests()
        }
    }

    // MARK: - ASAuthorizationControllerDelegate

    nonisolated func authorizationController(
        controller: ASAuthorizationController,
        didCompleteWithAuthorization authorization: ASAuthorization
    ) {
        Task { @MainActor in
            guard let credential = authorization.credential as? ASAuthorizationAppleIDCredential,
                  let tokenData = credential.identityToken,
                  let identityToken = String(data: tokenData, encoding: .utf8) else {
                continuation?.resume(throwing: APIError.unauthorized)
                continuation = nil
                return
            }

            let fullName = [credential.fullName?.givenName, credential.fullName?.familyName]
                .compactMap { $0 }
                .joined(separator: " ")

            let result = AppleSignInResult(
                identityToken: identityToken,
                email: credential.email,
                fullName: fullName.isEmpty ? nil : fullName
            )

            continuation?.resume(returning: result)
            continuation = nil
        }
    }

    nonisolated func authorizationController(
        controller: ASAuthorizationController,
        didCompleteWithError error: Error
    ) {
        Task { @MainActor in
            continuation?.resume(throwing: error)
            continuation = nil
        }
    }
}
