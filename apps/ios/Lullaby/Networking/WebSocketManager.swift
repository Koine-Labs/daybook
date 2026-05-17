import Foundation

/// Prediction received from the inference server.
struct StagePrediction: Codable, Sendable {
    let epochIndex: Int
    let stage: String
    let confidence: Double
    let probabilities: [String: Double]
}

/// Manages WebSocket connection to the inference server.
@MainActor
@Observable
final class WebSocketManager: NSObject, URLSessionWebSocketDelegate {
    private(set) var isConnected = false
    private(set) var lastPrediction: StagePrediction?
    private(set) var connectionStatus: ConnectionStatus = .disconnected

    enum ConnectionStatus: String {
        case disconnected
        case connecting
        case connected
        case reconnecting
        case failed
    }

    private var webSocketTask: URLSessionWebSocketTask?
    private var urlSession: URLSession?
    private var accessToken: String?
    private var pendingEpochs: [[String: Any]] = []
    private var retryCount = 0
    private let maxRetries = 3
    private var sessionId: String?

    func connect(accessToken: String) {
        self.accessToken = accessToken
        self.retryCount = 0
        _connect()
    }

    private func _connect() {
        connectionStatus = .connecting
        let url = InferenceConfig.websocketURL

        var request = URLRequest(url: url)
        if let token = accessToken {
            request.addValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        let config = URLSessionConfiguration.default
        let delegateQueue = OperationQueue.main
        urlSession = URLSession(configuration: config, delegate: self, delegateQueue: delegateQueue)
        webSocketTask = urlSession?.webSocketTask(with: request)
        webSocketTask?.resume()
        listenForMessages()
    }

    func sendSessionStart(sessionId: String, startedAt: Date) {
        self.sessionId = sessionId
        let formatter = ISO8601DateFormatter()
        let msg: [String: Any] = [
            "type": "session_start",
            "session_id": sessionId,
            "started_at": formatter.string(from: startedAt),
        ]
        send(msg)
    }

    func sendSensorEpoch(epochIndex: Int, timestamp: Date, data: [String: Any]) {
        let formatter = ISO8601DateFormatter()
        let msg: [String: Any] = [
            "type": "sensor_epoch",
            "epoch_index": epochIndex,
            "timestamp": formatter.string(from: timestamp),
            "data": data,
        ]

        if isConnected {
            for buffered in pendingEpochs {
                send(buffered)
            }
            pendingEpochs.removeAll()
            send(msg)
        } else {
            pendingEpochs.append(msg)
        }
    }

    func sendSessionEnd() {
        send(["type": "session_end"])
        disconnect()
    }

    func disconnect() {
        webSocketTask?.cancel(with: .normalClosure, reason: nil)
        webSocketTask = nil
        isConnected = false
        connectionStatus = .disconnected
        pendingEpochs.removeAll()
    }

    // MARK: - Private

    private func send(_ dict: [String: Any]) {
        guard let data = try? JSONSerialization.data(withJSONObject: dict),
              let string = String(data: data, encoding: .utf8) else { return }
        webSocketTask?.send(.string(string)) { [weak self] error in
            if let error {
                print("[WebSocket] Send error: \(error)")
                Task { @MainActor in self?.handleDisconnect() }
            }
        }
    }

    private func listenForMessages() {
        webSocketTask?.receive { [weak self] result in
            Task { @MainActor in
                switch result {
                case .success(let message):
                    self?.handleMessage(message)
                    self?.listenForMessages()
                case .failure(let error):
                    print("[WebSocket] Receive error: \(error)")
                    self?.handleDisconnect()
                }
            }
        }
    }

    private func handleMessage(_ message: URLSessionWebSocketTask.Message) {
        guard case .string(let text) = message,
              let data = text.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let type = json["type"] as? String else { return }

        switch type {
        case "session_ack":
            print("[WebSocket] Session acknowledged")
        case "prediction":
            if let epochIndex = json["epoch_index"] as? Int,
               let stage = json["stage"] as? String,
               let confidence = json["confidence"] as? Double,
               let probabilities = json["probabilities"] as? [String: Double] {
                lastPrediction = StagePrediction(
                    epochIndex: epochIndex,
                    stage: stage,
                    confidence: confidence,
                    probabilities: probabilities
                )
            }
        case "error":
            let errorMsg = json["message"] as? String ?? "Unknown error"
            print("[WebSocket] Server error: \(errorMsg)")
        default:
            print("[WebSocket] Unknown message type: \(type)")
        }
    }

    private func handleDisconnect() {
        isConnected = false
        guard retryCount < maxRetries else {
            connectionStatus = .failed
            print("[WebSocket] Max retries reached, giving up")
            return
        }
        connectionStatus = .reconnecting
        retryCount += 1
        let delay = pow(2.0, Double(retryCount))
        print("[WebSocket] Reconnecting in \(delay)s (attempt \(retryCount)/\(maxRetries))")
        Task {
            try? await Task.sleep(for: .seconds(delay))
            _connect()
        }
    }

    // MARK: - URLSessionWebSocketDelegate (delivered on main queue)

    nonisolated func urlSession(
        _ session: URLSession,
        webSocketTask: URLSessionWebSocketTask,
        didOpenWithProtocol protocol: String?
    ) {
        Task { @MainActor in
            self.isConnected = true
            self.connectionStatus = .connected
            self.retryCount = 0
            print("[WebSocket] Connected")
        }
    }

    nonisolated func urlSession(
        _ session: URLSession,
        webSocketTask: URLSessionWebSocketTask,
        didCloseWith closeCode: URLSessionWebSocketTask.CloseCode,
        reason: Data?
    ) {
        Task { @MainActor in
            self.isConnected = false
            if self.connectionStatus != .disconnected {
                self.handleDisconnect()
            }
        }
    }
}
