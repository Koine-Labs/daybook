import Foundation

enum EmotionTag: String, Codable, CaseIterable, Identifiable, Sendable {
    case peaceful, exciting, frightening, surreal, nostalgic, confusing, joyful, bizarre
    var id: String { rawValue }
    var displayName: String { rawValue.capitalized }
    var sfSymbol: String {
        switch self {
        case .peaceful: return "leaf.fill"
        case .exciting: return "bolt.fill"
        case .frightening: return "exclamationmark.triangle.fill"
        case .surreal: return "sparkles"
        case .nostalgic: return "clock.fill"
        case .confusing: return "questionmark.circle.fill"
        case .joyful: return "face.smiling.fill"
        case .bizarre: return "eye.trianglebadge.exclamationmark.fill"
        }
    }
}
