import Foundation

// WatchMessage — the typed protocol that flows over WatchConnectivity in
// both directions. Same definition is duplicated in the watch target at
// "DaybookWatch Watch App/WatchMessage.swift" because iOS + watchOS don't
// share a framework yet. If/when we add one, collapse to a single file.
//
// Wire format: JSON-encoded Data tucked under a single "p" key in the
// WCSession message dictionary. Single key keeps the surface area small
// and the decoder rejects anything malformed silently (acceptance #4).
enum WatchMessage: Codable, Equatable {
    case showListen(line: String, ttlSeconds: Double)
    case showSpeak
    case dismissOverlay
    case talkPressed(durationSec: Double)
    case heartbeat

    // MARK: - Wire transport

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
    // Round-trip smoke — one call exercises every case through the wire
    // format. Returns true if every case survives encode → decode equal.
    // Invoked from a DEBUG print on app launch.
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
