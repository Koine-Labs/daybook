@preconcurrency import WatchConnectivity
import Foundation

/// Receives sensor data from the Apple Watch on the iPhone via WatchConnectivity.
///
/// Decodes `ConnectivityEnvelope` payloads and forwards `SensorPacket`s
/// to the `SleepSessionStore` via a callback.
nonisolated final class PhoneConnectivityManager: NSObject, WCSessionDelegate, @unchecked Sendable {
    /// Called on the main actor when a sensor packet is received.
    var onPacketReceived: (@Sendable (SensorPacket) -> Void)?
    /// Called when a session control command is received.
    var onCommandReceived: (@Sendable (SessionControlCommand) -> Void)?
    /// Called when watch reachability changes.
    var onReachabilityChanged: (@Sendable (Bool) -> Void)?

    private let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.dateDecodingStrategy = .iso8601
        return d
    }()

    /// Activate the WCSession. Call once at app launch.
    func activate() {
        guard WCSession.isSupported() else { return }
        WCSession.default.delegate = self
        WCSession.default.activate()
    }

    /// Whether the watch is currently reachable.
    var isWatchReachable: Bool {
        WCSession.default.isReachable
    }

    // MARK: - WCSessionDelegate

    func session(
        _ session: WCSession,
        activationDidCompleteWith activationState: WCSessionActivationState,
        error: Error?
    ) {
        // Required delegate method
    }

    func sessionDidBecomeInactive(_ session: WCSession) {
        // Required on iOS
    }

    func sessionDidDeactivate(_ session: WCSession) {
        // Re-activate for next watch connection
        session.activate()
    }

    func sessionReachabilityDidChange(_ session: WCSession) {
        onReachabilityChanged?(session.isReachable)
    }

    /// Receives `transferUserInfo` payloads from the watch.
    func session(
        _ session: WCSession,
        didReceiveUserInfo userInfo: [String: Any] = [:]
    ) {
        guard let envelope = ConnectivityEnvelope.from(dictionary: userInfo) else { return }

        switch envelope.type {
        case .sensorPacket:
            guard let packet = try? decoder.decode(SensorPacket.self, from: envelope.payload) else { return }
            onPacketReceived?(packet)

        case .sessionControl:
            guard let command = try? decoder.decode(SessionControlCommand.self, from: envelope.payload) else { return }
            onCommandReceived?(command)
        }
    }
}
