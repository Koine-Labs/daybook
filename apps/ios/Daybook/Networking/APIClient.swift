import Foundation

// URLSession client pointed at the FastAPI bridge (apps/api/).
// Base URL resolves from Info.plist `DaybookAPIBaseURL`, with a localhost
// fallback for simulator development. For on-device testing edit the plist
// value to your Mac's LAN IP (e.g. http://192.168.1.42:8000).
struct APIClient {
    let baseURL: URL

    static let shared = APIClient()

    init(baseURL: URL? = nil) {
        if let baseURL {
            self.baseURL = baseURL
        } else {
            self.baseURL = Self.resolveBaseURL()
        }
    }

    private static func resolveBaseURL() -> URL {
        let fallback = URL(string: "http://localhost:8000")!
        guard
            let raw = Bundle.main.object(forInfoDictionaryKey: "DaybookAPIBaseURL") as? String,
            !raw.trimmingCharacters(in: .whitespaces).isEmpty,
            let url = URL(string: raw)
        else {
            return fallback
        }
        return url
    }

    enum APIError: Error, CustomStringConvertible, Sendable {
        case invalidResponse
        case httpStatus(Int, String)
        case decoding(Error)
        case transport(Error)

        var description: String {
            switch self {
            case .invalidResponse: return "Invalid response"
            case .httpStatus(let code, let body):
                return "HTTP \(code): \(body.prefix(200))"
            case .decoding(let err): return "Decoding failed: \(err)"
            case .transport(let err): return "Transport error: \(err)"
            }
        }

        /// Short human-facing string for the chat overlay's offline banner.
        var userFacing: String {
            switch self {
            case .invalidResponse: return "couldn't reach mac (bad response)"
            case .httpStatus(let code, _): return "mac returned \(code)"
            case .decoding: return "mac replied in a shape i don't understand"
            case .transport: return "couldn't reach mac"
            }
        }
    }

    private static let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.dateDecodingStrategy = .iso8601
        return d
    }()

    private static let encoder: JSONEncoder = {
        let e = JSONEncoder()
        e.dateEncodingStrategy = .iso8601
        return e
    }()

    // MARK: - Generic helpers

    func get<T: Decodable>(_ path: String) async throws -> T {
        try await request(method: "GET", path: path, body: Optional<EmptyBody>.none)
    }

    func post<T: Decodable, B: Encodable>(_ path: String, body: B) async throws -> T {
        try await request(method: "POST", path: path, body: body)
    }

    private func request<T: Decodable, B: Encodable>(
        method: String,
        path: String,
        body: B?
    ) async throws -> T {
        let url = baseURL.appendingPathComponent(path.hasPrefix("/") ? String(path.dropFirst()) : path)
        var req = URLRequest(url: url)
        req.httpMethod = method
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        // Keep things snappy on flaky LAN — better to fail fast and show the
        // offline fallback than hang the chat overlay for 60s.
        req.timeoutInterval = 25

        if let body {
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            do {
                req.httpBody = try Self.encoder.encode(body)
            } catch {
                throw APIError.decoding(error)
            }
        }

        let (data, response): (Data, URLResponse)
        do {
            (data, response) = try await URLSession.shared.data(for: req)
        } catch {
            throw APIError.transport(error)
        }

        guard let http = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }
        guard (200..<300).contains(http.statusCode) else {
            let body = String(data: data, encoding: .utf8) ?? ""
            throw APIError.httpStatus(http.statusCode, body)
        }

        do {
            return try Self.decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decoding(error)
        }
    }

    // MARK: - Chat
    //
    // The FastAPI bridge models chat in two steps:
    //   1. POST /chat/conversations            → { id, started_at, title }
    //   2. POST /chat/conversations/{id}/messages   → { text, ... }
    //
    // We expose a single `chat(message:conversationId:)` that creates a
    // conversation lazily on first call and reuses it on subsequent calls.

    struct ChatRequest: Encodable {
        let text: String
    }

    struct ChatReply: Decodable, Sendable {
        let text: String
        let conversationId: String
        let assistantMessageId: String?
        let model: String?
        let backend: String?
        let elapsedMs: Int?
    }

    private struct CreateConversationRequest: Encodable {
        let title: String?
    }

    private struct CreateConversationResponse: Decodable {
        let id: String
    }

    private struct SendMessageResponse: Decodable {
        let user_message_id: String
        let assistant_message_id: String
        let text: String
        let model: String
        let backend: String
        let elapsed_ms: Int
    }

    /// Send a user message and return Regis's reply. If `conversationId` is
    /// nil a new conversation is created on the server first, and the new id
    /// is returned in `ChatReply.conversationId` so callers can persist it.
    func chat(message: String, conversationId: String?) async throws -> ChatReply {
        let convId: String
        if let conversationId, !conversationId.isEmpty {
            convId = conversationId
        } else {
            let body = CreateConversationRequest(title: nil)
            let created: CreateConversationResponse = try await post(
                "/chat/conversations",
                body: body
            )
            convId = created.id
        }

        let send = ChatRequest(text: message)
        let reply: SendMessageResponse = try await post(
            "/chat/conversations/\(convId)/messages",
            body: send
        )

        return ChatReply(
            text: reply.text,
            conversationId: convId,
            assistantMessageId: reply.assistant_message_id,
            model: reply.model,
            backend: reply.backend,
            elapsedMs: reply.elapsed_ms
        )
    }
}

private struct EmptyBody: Encodable {}
