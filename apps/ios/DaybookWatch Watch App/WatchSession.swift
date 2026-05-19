import Foundation
import WatchConnectivity

// WatchSession (watchOS) — companion to apps/ios/Daybook/Watch/WatchSession.swift.
//
// Receives .showListen / .showSpeak / .dismissOverlay from the phone and
// emits .talkPressed when the user long-presses the watch face. Heartbeats
// flow both ways and are silent-drop on failure.
//
// The watch can't observe `WCSessionActivationState` swaps the way iOS can
// (no inactive/deactivate delegate methods on watchOS), so this side is
// simpler: activate once at app launch and route incoming messages into
// closures the view registered.
final class WatchSession: NSObject, WCSessionDelegate {
    static let shared = WatchSession()

    // Closures the watch ContentView registers. Optional so a session
    // can run before any view appears.
    var onShowListen: ((String, Double) -> Void)?
    var onShowSpeak: (() -> Void)?
    var onDismiss: (() -> Void)?
    var onHeartbeat: (() -> Void)?

    private let session: WCSession? = WCSession.isSupported() ? WCSession.default : nil
    private var heartbeatTimer: Timer?

    private override init() {
        super.init()
    }

    // MARK: - Lifecycle

    func activate() {
        guard let session else { return }
        session.delegate = self
        if session.activationState != .activated {
            session.activate()
        }
    }

    var isReachable: Bool { session?.isReachable ?? false }

    // MARK: - Outbound

    // Single watch-originated payload today: the long-press release.
    func reportTalkPressed(durationSec: Double) {
        send(.talkPressed(durationSec: durationSec))
    }

    func send(_ message: WatchMessage) {
        guard let session, let payload = try? message.encodeToUserInfo() else { return }

        switch message {
        case .heartbeat:
            guard session.isReachable else { return }
            session.sendMessage(payload, replyHandler: nil, errorHandler: { _ in })

        case .talkPressed, .showListen, .showSpeak, .dismissOverlay:
            // Survive backgrounding via queued transfer when phone isn't reachable.
            if session.isReachable {
                session.sendMessage(payload, replyHandler: nil, errorHandler: { [weak self] _ in
                    self?.queue(payload)
                })
            } else {
                queue(payload)
            }
        }
    }

    private func queue(_ payload: [String: Any]) {
        session?.transferUserInfo(payload)
    }

    // MARK: - Heartbeat

    func startHeartbeat(interval: TimeInterval = 60) {
        heartbeatTimer?.invalidate()
        heartbeatTimer = Timer.scheduledTimer(withTimeInterval: interval, repeats: true) { [weak self] _ in
            self?.send(.heartbeat)
        }
    }

    func stopHeartbeat() {
        heartbeatTimer?.invalidate()
        heartbeatTimer = nil
    }

    // MARK: - Routing

    private func handleIncoming(_ message: WatchMessage) {
        DispatchQueue.main.async { [weak self] in
            switch message {
            case .showListen(let line, let ttl):
                self?.onShowListen?(line, ttl)
            case .showSpeak:
                self?.onShowSpeak?()
            case .dismissOverlay:
                self?.onDismiss?()
            case .heartbeat:
                self?.onHeartbeat?()
            case .talkPressed:
                // Watch-originated; ignore if echoed back.
                break
            }
        }
    }

    // MARK: - WCSessionDelegate

    func session(_ session: WCSession, activationDidCompleteWith state: WCSessionActivationState, error: Error?) {
        // No-op. State observable via `session.activationState`.
    }

    func sessionReachabilityDidChange(_ session: WCSession) {
        // No-op for now.
    }

    func session(_ session: WCSession, didReceiveMessage message: [String: Any]) {
        guard let parsed = WatchMessage.decode(from: message) else { return }
        handleIncoming(parsed)
    }

    func session(_ session: WCSession, didReceiveUserInfo userInfo: [String: Any] = [:]) {
        guard let parsed = WatchMessage.decode(from: userInfo) else { return }
        handleIncoming(parsed)
    }
}
