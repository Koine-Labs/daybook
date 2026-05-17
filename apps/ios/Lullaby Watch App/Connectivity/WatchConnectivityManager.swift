@preconcurrency import WatchConnectivity
import Foundation

/// Manages Watch → iPhone data transfer via WatchConnectivity.
///
/// Uses `transferUserInfo` for reliable, queued delivery that survives app restarts
/// and connectivity drops. Maintains a local buffer for packets that haven't been
/// handed off to WCSession yet.
nonisolated final class WatchConnectivityManager: NSObject, WCSessionDelegate {
    private let buffer: WatchDataBuffer
    private let sequenceCounter = SequenceCounter()

    init(buffer: WatchDataBuffer) {
        self.buffer = buffer
        super.init()
    }

    /// Activate the WCSession. Call once at app launch.
    func activate() {
        guard WCSession.isSupported() else { return }
        WCSession.default.delegate = self
        WCSession.default.activate()
    }

    /// Send a sensor packet to the iPhone.
    func sendPacket(_ packet: SensorPacket) {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        guard let payloadData = try? encoder.encode(packet) else { return }

        let envelope = ConnectivityEnvelope(
            type: .sensorPacket,
            payload: payloadData,
            sequenceNumber: sequenceCounter.next(),
            sentAt: Date()
        )

        if WCSession.default.isReachable {
            WCSession.default.transferUserInfo(envelope.toDictionary())
        } else {
            Task { await buffer.enqueue(envelope) }
        }
    }

    /// Send a session control command.
    func sendCommand(_ command: SessionControlCommand) {
        let encoder = JSONEncoder()
        guard let payloadData = try? encoder.encode(command) else { return }

        let envelope = ConnectivityEnvelope(
            type: .sessionControl,
            payload: payloadData,
            sequenceNumber: sequenceCounter.next(),
            sentAt: Date()
        )

        WCSession.default.transferUserInfo(envelope.toDictionary())
    }

    /// Flush any buffered packets that were stored while phone was unreachable.
    func flushBuffer() {
        Task {
            let pending = await buffer.drainAll()
            for envelope in pending {
                WCSession.default.transferUserInfo(envelope.toDictionary())
            }
        }
    }

    // MARK: - WCSessionDelegate

    func session(
        _ session: WCSession,
        activationDidCompleteWith activationState: WCSessionActivationState,
        error: Error?
    ) {
        if activationState == .activated {
            Task { await buffer.restoreFromDisk() }
        }
    }

    func sessionReachabilityDidChange(_ session: WCSession) {
        if session.isReachable {
            flushBuffer()
        }
    }

    #if os(iOS)
    func sessionDidBecomeInactive(_ session: WCSession) {}
    func sessionDidDeactivate(_ session: WCSession) {
        session.activate()
    }
    #endif
}

// MARK: - Thread-safe sequence counter

nonisolated private final class SequenceCounter: @unchecked Sendable {
    private let lock = NSLock()
    private var _value: UInt64 = 0

    func next() -> UInt64 {
        lock.lock()
        defer { lock.unlock() }
        _value += 1
        return _value
    }
}
