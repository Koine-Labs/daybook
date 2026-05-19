import Foundation
import WatchConnectivity

// MARK: - Connection status (#14 follow-up)

/// Coarse-grained connection state for UI consumption.
/// `.connected` = watch is reachable RIGHT NOW (app open / wrist up).
/// `.paired`    = session activated + watch + app installed, but watch asleep.
/// `.notInstalled` = paired watch exists but the Daybook watch app isn't on it.
/// `.notPaired` = no Apple Watch paired with this iPhone.
/// `.unsupported` = WCSession not supported (shouldn't happen on iPhones).
/// `.unknown` = session not yet activated.
enum WatchConnectionStatus: Equatable {
    case unknown
    case unsupported
    case notPaired
    case notInstalled
    case paired
    case connected

    /// Short label rendered in the iOS ConnectionsRoom's Apple Watch row.
    var rowLabel: String {
        switch self {
        case .unknown:      return "checking…"
        case .unsupported:  return "not supported"
        case .notPaired:    return "not paired"
        case .notInstalled: return "install daybook on watch"
        case .paired:       return "paired"
        case .connected:    return "connected"
        }
    }

    /// Whether the row should render in the "active/connected" visual style.
    var isActive: Bool { self == .connected }
}

// WatchSession (iOS) — singleton WCSessionDelegate for the phone side.
//
// Wire rules:
//   - sendMessage    → foreground-to-foreground only (requires reachable).
//                      Used opportunistically + for heartbeats.
//   - transferUserInfo → queued; survives watch sleep / app suspension.
//                        Used for any payload that MUST land.
//
// The phone fires .showListen / .showSpeak / .dismissOverlay; the watch
// fires .talkPressed back. .heartbeat flows both ways and is silent-drop
// on failure (no error logs) per acceptance #4.
final class WatchSession: NSObject, WCSessionDelegate {
    static let shared = WatchSession()

    // Callbacks the host (AppState) registers to route incoming messages
    // into observable state. Optional so a session can run before bindings.
    var onTalkPressed: ((Double) -> Void)?
    var onHeartbeat: (() -> Void)?

    /// Fires whenever connection state changes (activation completed,
    /// reachability flipped, etc.). Always called on main.
    var onStatusChange: ((WatchConnectionStatus) -> Void)?

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

    /// Compute current status from the underlying WCSession.
    var currentStatus: WatchConnectionStatus {
        guard let session else { return .unsupported }
        guard session.activationState == .activated else { return .unknown }
        if !session.isPaired { return .notPaired }
        if !session.isWatchAppInstalled { return .notInstalled }
        if session.isReachable { return .connected }
        return .paired
    }

    private func emitStatus() {
        let s = currentStatus
        DispatchQueue.main.async { [weak self] in
            self?.onStatusChange?(s)
        }
    }

    // MARK: - Send

    func send(_ message: WatchMessage) {
        guard let session, let payload = try? message.encodeToUserInfo() else { return }

        switch message {
        case .heartbeat:
            // Heartbeats are best-effort live probes. Never queue them —
            // they'd pile up while the watch is asleep. Silent drop.
            guard session.isReachable else { return }
            session.sendMessage(payload, replyHandler: nil, errorHandler: { _ in })

        case .showListen, .showSpeak, .dismissOverlay, .talkPressed:
            // Foreground-to-foreground when we can (instant); fall back to
            // transferUserInfo so the message survives backgrounding.
            if session.isReachable {
                session.sendMessage(payload, replyHandler: nil, errorHandler: { [weak self] _ in
                    // Live send failed mid-flight — re-queue silently.
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

    func startHeartbeat(interval: TimeInterval = 30) {
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
        // Hop to main — UI/state updates downstream of these closures.
        DispatchQueue.main.async { [weak self] in
            switch message {
            case .talkPressed(let duration):
                self?.onTalkPressed?(duration)
            case .heartbeat:
                self?.onHeartbeat?()
            case .showListen, .showSpeak, .dismissOverlay:
                // These are phone → watch only; ignore if echoed back.
                break
            }
        }
    }

    // MARK: - WCSessionDelegate

    func session(_ session: WCSession, activationDidCompleteWith state: WCSessionActivationState, error: Error?) {
        emitStatus()
    }

    // iOS-only delegate methods. Watch deactivates after pairing changes;
    // re-activate so the channel stays alive across paired-watch swaps.
    func sessionDidBecomeInactive(_ session: WCSession) {
        emitStatus()
    }
    func sessionDidDeactivate(_ session: WCSession) {
        session.activate()
        emitStatus()
    }

    func sessionReachabilityDidChange(_ session: WCSession) {
        emitStatus()
    }

    // Pairing / install status can flip without a separate delegate hit on
    // some watchOS versions — but Apple does deliver `watchStateDidChange`.
    func sessionWatchStateDidChange(_ session: WCSession) {
        emitStatus()
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
