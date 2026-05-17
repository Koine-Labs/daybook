import Foundation

struct DreamEntry: Codable, Identifiable, Hashable, Sendable {
    let id: UUID
    let date: Date
    var sessionId: UUID?
    var isLucid: Bool
    var vividness: Int  // 1-5
    var emotions: [EmotionTag]
    var summary: String?
    var narrative: String?
    var themes: [String]
    var realityCheckNotes: String?
    var cueAwareness: Bool?
    var xpAwarded: Bool
    let createdAt: Date
    var updatedAt: Date

    init(id: UUID = UUID(), date: Date, sessionId: UUID? = nil, isLucid: Bool = false,
         vividness: Int = 3, emotions: [EmotionTag] = [], summary: String? = nil,
         narrative: String? = nil, themes: [String] = [], realityCheckNotes: String? = nil,
         cueAwareness: Bool? = nil) {
        self.id = id; self.date = date; self.sessionId = sessionId; self.isLucid = isLucid
        self.vividness = vividness; self.emotions = emotions; self.summary = summary
        self.narrative = narrative; self.themes = themes; self.realityCheckNotes = realityCheckNotes
        self.cueAwareness = cueAwareness; self.xpAwarded = false
        self.createdAt = Date(); self.updatedAt = Date()
    }

    var isRichEntry: Bool { (narrative?.count ?? 0) >= 500 }
    var hasNarrative: Bool { (narrative?.count ?? 0) >= 100 }
}
