import Foundation

/// API endpoint definitions for the Lullaby data collection server.
nonisolated enum APIEndpoints {
    // Auth
    case register
    case login
    case refresh
    case logout
    case googleAuth
    case appleAuth

    // Sessions
    case uploadBlob(sessionId: String)
    case createSession
    case listSessions
    case downloadSession(sessionId: String)
    case deleteSession(sessionId: String)

    // Users
    case me
    case updateMe

    var path: String {
        switch self {
        case .register:       return "/auth/register"
        case .login:          return "/auth/login"
        case .refresh:        return "/auth/refresh"
        case .logout:         return "/auth/logout"
        case .googleAuth:     return "/auth/google"
        case .appleAuth:      return "/auth/apple"

        case .uploadBlob(let id):      return "/sessions/\(id)/blob"
        case .createSession:           return "/sessions"
        case .listSessions:            return "/sessions"
        case .downloadSession(let id): return "/sessions/\(id)/download"
        case .deleteSession(let id):   return "/sessions/\(id)"

        case .me:         return "/users/me"
        case .updateMe:   return "/users/me"
        }
    }

    var method: String {
        switch self {
        case .register, .login, .refresh, .logout,
             .googleAuth, .appleAuth, .createSession:
            return "POST"
        case .uploadBlob:
            return "PUT"
        case .listSessions, .downloadSession, .me:
            return "GET"
        case .deleteSession:
            return "DELETE"
        case .updateMe:
            return "PATCH"
        }
    }
}
