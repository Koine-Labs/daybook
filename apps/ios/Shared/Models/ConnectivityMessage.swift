import Foundation

/// Types of messages exchanged between Watch and iPhone via WatchConnectivity.
nonisolated enum ConnectivityMessageType: String, Codable, Sendable {
    /// A batch of sensor data from the watch.
    case sensorPacket
    /// Session lifecycle control command.
    case sessionControl
}

/// Wrapper envelope for all WatchConnectivity transfers.
/// Encodes the payload as opaque `Data` to allow type-erased transport via `transferUserInfo`.
nonisolated struct ConnectivityEnvelope: Codable, Sendable {
    let type: ConnectivityMessageType
    /// JSON-encoded payload (SensorPacket or SessionControlCommand).
    let payload: Data
    /// Monotonically increasing sequence number for ordering and gap detection.
    let sequenceNumber: UInt64
    /// Wall-clock time when this envelope was created on the sender.
    let sentAt: Date

    // MARK: - Dictionary Conversion for WatchConnectivity

    /// Keys used in the `[String: Any]` dictionary for `transferUserInfo`.
    private enum DictKey {
        static let type = "type"
        static let payload = "payload"
        static let seq = "seq"
        static let sentAt = "sentAt"
    }

    /// Convert to a `[String: Any]` dictionary for `WCSession.transferUserInfo(_:)`.
    func toDictionary() -> [String: Any] {
        [
            DictKey.type: type.rawValue,
            DictKey.payload: payload,
            DictKey.seq: sequenceNumber,
            DictKey.sentAt: sentAt.timeIntervalSinceReferenceDate
        ]
    }

    /// Reconstruct from a `[String: Any]` dictionary received via WatchConnectivity.
    static func from(dictionary dict: [String: Any]) -> ConnectivityEnvelope? {
        guard
            let typeRaw = dict[DictKey.type] as? String,
            let type = ConnectivityMessageType(rawValue: typeRaw),
            let payload = dict[DictKey.payload] as? Data,
            let seq = dict[DictKey.seq] as? UInt64,
            let sentAtInterval = dict[DictKey.sentAt] as? TimeInterval
        else {
            return nil
        }
        return ConnectivityEnvelope(
            type: type,
            payload: payload,
            sequenceNumber: seq,
            sentAt: Date(timeIntervalSinceReferenceDate: sentAtInterval)
        )
    }
}

/// Commands for controlling the sleep session lifecycle across devices.
nonisolated enum SessionControlCommand: String, Codable, Sendable {
    /// Watch is starting a new sleep session.
    case sessionStarted
    /// Watch is stopping the current session.
    case sessionStopped
    /// Phone acknowledges receipt of session start.
    case phoneReady
}
