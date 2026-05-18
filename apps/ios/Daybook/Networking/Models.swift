import Foundation

// Codable shapes matching what the FastAPI bridge at apps/api/ will return.
// Names track the Postgres entities; concrete column types may shift as the
// bridge is built — adjust here when the contract is locked.

struct ChatMessage: Codable, Hashable, Identifiable, Sendable {
    let id: UUID
    let role: Role
    let content: String
    let createdAt: Date

    enum Role: String, Codable, Sendable {
        case user
        case assistant
        case system
    }

    enum CodingKeys: String, CodingKey {
        case id
        case role
        case content
        case createdAt = "created_at"
    }
}

struct DreamRecall: Codable, Hashable, Identifiable, Sendable {
    let id: UUID
    let userId: UUID
    let text: String
    let recordedAt: Date
    let sleepSessionId: UUID?

    enum CodingKeys: String, CodingKey {
        case id
        case userId = "user_id"
        case text
        case recordedAt = "recorded_at"
        case sleepSessionId = "sleep_session_id"
    }
}

struct SleepSession: Codable, Hashable, Identifiable, Sendable {
    let id: UUID
    let userId: UUID
    let startedAt: Date
    let endedAt: Date?
    let totalMinutes: Int?
    let remMinutes: Int?
    let deepMinutes: Int?
    let lightMinutes: Int?
    let awakeMinutes: Int?

    enum CodingKeys: String, CodingKey {
        case id
        case userId = "user_id"
        case startedAt = "started_at"
        case endedAt = "ended_at"
        case totalMinutes = "total_minutes"
        case remMinutes = "rem_minutes"
        case deepMinutes = "deep_minutes"
        case lightMinutes = "light_minutes"
        case awakeMinutes = "awake_minutes"
    }
}

struct RegisMoment: Codable, Hashable, Identifiable, Sendable {
    let id: UUID
    let userId: UUID
    let kind: String
    let payload: [String: AnyCodableValue]?
    let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id
        case userId = "user_id"
        case kind
        case payload
        case createdAt = "created_at"
    }
}

struct Intent: Codable, Hashable, Identifiable, Sendable {
    let id: UUID
    let userId: UUID
    let text: String
    let setAt: Date

    enum CodingKeys: String, CodingKey {
        case id
        case userId = "user_id"
        case text
        case setAt = "set_at"
    }
}

// Minimal AnyCodable for opaque JSONB payloads. Decode-only; we round-trip
// to Any without losing nesting structure.
enum AnyCodableValue: Codable, Hashable, Sendable {
    case string(String)
    case int(Int)
    case double(Double)
    case bool(Bool)
    case array([AnyCodableValue])
    case object([String: AnyCodableValue])
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let v = try? container.decode(Bool.self) {
            self = .bool(v)
        } else if let v = try? container.decode(Int.self) {
            self = .int(v)
        } else if let v = try? container.decode(Double.self) {
            self = .double(v)
        } else if let v = try? container.decode(String.self) {
            self = .string(v)
        } else if let v = try? container.decode([AnyCodableValue].self) {
            self = .array(v)
        } else if let v = try? container.decode([String: AnyCodableValue].self) {
            self = .object(v)
        } else {
            throw DecodingError.dataCorruptedError(
                in: container,
                debugDescription: "Unsupported JSON value"
            )
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .null: try container.encodeNil()
        case .bool(let v): try container.encode(v)
        case .int(let v): try container.encode(v)
        case .double(let v): try container.encode(v)
        case .string(let v): try container.encode(v)
        case .array(let v): try container.encode(v)
        case .object(let v): try container.encode(v)
        }
    }
}
