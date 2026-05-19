import Foundation

// WatchMessage (watchOS copy) — see iOS counterpart at
// apps/ios/Daybook/Watch/WatchMessage.swift for full notes.
// Targets don't share a framework today, so this file is duplicated
// verbatim. Keep the two in sync — they're the wire contract.
enum WatchMessage: Codable, Equatable {
    case showListen(line: String, ttlSeconds: Double)
    case showSpeak
    case dismissOverlay
    case talkPressed(durationSec: Double)
    case heartbeat

    static let payloadKey = "p"

    func encodeToUserInfo() throws -> [String: Any] {
        let data = try JSONEncoder().encode(self)
        return [Self.payloadKey: data]
    }

    static func decode(from userInfo: [String: Any]) -> WatchMessage? {
        guard let data = userInfo[payloadKey] as? Data else { return nil }
        return try? JSONDecoder().decode(WatchMessage.self, from: data)
    }

    #if DEBUG
    static func runRoundTripSmoke() -> Bool {
        let cases: [WatchMessage] = [
            .showListen(line: "test line", ttlSeconds: 6),
            .showSpeak,
            .dismissOverlay,
            .talkPressed(durationSec: 1.23),
            .heartbeat,
        ]
        for c in cases {
            guard
                let wire = try? c.encodeToUserInfo(),
                let back = WatchMessage.decode(from: wire),
                back == c
            else {
                return false
            }
        }
        return true
    }
    #endif
}
