import Foundation

/// URLSession-based HTTP client for the Lullaby data collection server.
/// Handles auth headers, token refresh, and typed error mapping.
actor APIClient {
    static let defaultBaseURL = "https://lullaby-server.aakashjuly18.workers.dev"

    private let baseURL: String
    private let urlSession: URLSession
    private let decoder: JSONDecoder
    private var accessToken: String?
    private var refreshToken: String?
    private var onTokenRefreshed: ((String, String) async -> Void)?

    init(
        baseURL: String = APIClient.defaultBaseURL,
        urlSession: URLSession = .shared
    ) {
        self.baseURL = baseURL
        self.urlSession = urlSession
        self.decoder = JSONDecoder()
    }

    /// Set auth tokens (called by AuthManager).
    func setTokens(access: String?, refresh: String?) {
        self.accessToken = access
        self.refreshToken = refresh
    }

    /// Set callback for when tokens are refreshed.
    func setTokenRefreshHandler(_ handler: @escaping (String, String) async -> Void) {
        self.onTokenRefreshed = handler
    }

    // MARK: - Request helpers

    /// Make a JSON request and decode the response.
    func request<T: Decodable>(
        _ endpoint: APIEndpoints,
        body: (any Encodable)? = nil
    ) async throws -> T {
        let data = try await rawRequest(endpoint, body: body)
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decodingError(error)
        }
    }

    /// Make a request that returns no meaningful body.
    func requestVoid(
        _ endpoint: APIEndpoints,
        body: (any Encodable)? = nil
    ) async throws {
        _ = try await rawRequest(endpoint, body: body)
    }

    /// Stream raw data directly (for blob upload).
    func uploadData(
        _ endpoint: APIEndpoints,
        data: Data
    ) async throws -> Data {
        guard let url = URL(string: baseURL + endpoint.path) else {
            throw APIError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = endpoint.method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        if let token = accessToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        let (responseData, response) = try await urlSession.upload(for: request, from: data)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.networkError(URLError(.badServerResponse))
        }

        if httpResponse.statusCode == 401 {
            // Try refresh
            if try await attemptTokenRefresh() {
                request.setValue("Bearer \(accessToken ?? "")", forHTTPHeaderField: "Authorization")
                let (retryData, retryResponse) = try await urlSession.upload(for: request, from: data)
                guard let retryHTTP = retryResponse as? HTTPURLResponse else {
                    throw APIError.networkError(URLError(.badServerResponse))
                }
                try mapHTTPError(retryHTTP, data: retryData)
                return retryData
            }
            throw APIError.tokenExpired
        }

        try mapHTTPError(httpResponse, data: responseData)
        return responseData
    }

    /// Download raw data (for session blob download).
    func downloadData(_ endpoint: APIEndpoints) async throws -> Data {
        return try await rawRequest(endpoint, body: nil)
    }

    // MARK: - Internal

    private func rawRequest(
        _ endpoint: APIEndpoints,
        body: (any Encodable)?
    ) async throws -> Data {
        guard let url = URL(string: baseURL + endpoint.path) else {
            throw APIError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = endpoint.method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        if let token = accessToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        if let body {
            let encoder = JSONEncoder()
            request.httpBody = try encoder.encode(body)
        }

        let (data, response): (Data, URLResponse)
        do {
            (data, response) = try await urlSession.data(for: request)
        } catch {
            throw APIError.networkError(error)
        }

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.networkError(URLError(.badServerResponse))
        }

        if httpResponse.statusCode == 401 {
            if try await attemptTokenRefresh() {
                request.setValue("Bearer \(accessToken ?? "")", forHTTPHeaderField: "Authorization")
                let (retryData, retryResponse) = try await urlSession.data(for: request)
                guard let retryHTTP = retryResponse as? HTTPURLResponse else {
                    throw APIError.networkError(URLError(.badServerResponse))
                }
                try mapHTTPError(retryHTTP, data: retryData)
                return retryData
            }
            throw APIError.tokenExpired
        }

        try mapHTTPError(httpResponse, data: data)
        return data
    }

    private func attemptTokenRefresh() async throws -> Bool {
        guard let refreshToken else { return false }

        guard let url = URL(string: baseURL + APIEndpoints.refresh.path) else { return false }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        struct RefreshBody: Encodable { let refreshToken: String }
        request.httpBody = try JSONEncoder().encode(RefreshBody(refreshToken: refreshToken))

        let (data, response) = try await urlSession.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else { return false }

        struct RefreshResponse: Decodable {
            let accessToken: String
            let refreshToken: String
        }

        guard let tokens = try? decoder.decode(RefreshResponse.self, from: data) else {
            return false
        }

        self.accessToken = tokens.accessToken
        self.refreshToken = tokens.refreshToken
        await onTokenRefreshed?(tokens.accessToken, tokens.refreshToken)
        return true
    }

    private func mapHTTPError(_ response: HTTPURLResponse, data: Data) throws {
        guard !(200...299).contains(response.statusCode) else { return }

        struct ErrorBody: Decodable { let error: String? }
        let message = (try? decoder.decode(ErrorBody.self, from: data))?.error

        switch response.statusCode {
        case 401: throw APIError.unauthorized
        case 403: throw APIError.forbidden
        case 404: throw APIError.notFound
        case 409: throw APIError.conflict(message ?? "Conflict")
        case 400: throw APIError.validationError(message ?? "Bad request")
        default:  throw APIError.serverError(response.statusCode, message)
        }
    }
}
