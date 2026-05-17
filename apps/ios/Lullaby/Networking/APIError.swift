import Foundation

/// Typed errors for Lullaby API operations.
enum APIError: LocalizedError {
    case invalidURL
    case unauthorized
    case forbidden
    case notFound
    case conflict(String)
    case validationError(String)
    case serverError(Int, String?)
    case networkError(Error)
    case decodingError(Error)
    case noData
    case tokenExpired

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid URL"
        case .unauthorized:
            return "Authentication required"
        case .forbidden:
            return "Access denied"
        case .notFound:
            return "Resource not found"
        case .conflict(let message):
            return message
        case .validationError(let message):
            return message
        case .serverError(let code, let message):
            return message ?? "Server error (\(code))"
        case .networkError(let error):
            return "Network error: \(error.localizedDescription)"
        case .decodingError(let error):
            return "Failed to parse response: \(error.localizedDescription)"
        case .noData:
            return "No data received"
        case .tokenExpired:
            return "Session expired — please sign in again"
        }
    }
}
