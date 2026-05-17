import Foundation
import Observation

/// Errors thrown by PhoneSessionCoordinator when required state is missing.
enum CoordinatorError: LocalizedError {
    case noActiveSession(String)

    var errorDescription: String? {
        switch self {
        case .noActiveSession(let msg): return msg
        }
    }
}

/// Orchestrates all iPhone-side components during a sleep session.
///
/// Manages: SonarEngine, PassiveAudioAnalyzer, PhoneConnectivityManager,
/// SleepSessionStore, MorningSyncManager, JSONExporter.
/// Exposes observable state for the SwiftUI dashboard.
@Observable
final class PhoneSessionCoordinator {
    // Published state for UI
    private(set) var isSessionActive = false
    private(set) var isWatchConnected = false
    private(set) var isSonarRunning = false
    private(set) var packetsReceived: UInt32 = 0
    private(set) var lastHeartRate: Double = 0
    private(set) var lastBreathingRate: Float = 0
    private(set) var sleepStagesSynced = false
    private(set) var sessionDuration: TimeInterval = 0

    // Upload state
    private(set) var isUploading = false
    private(set) var uploadError: String?

    // Inference server
    private(set) var currentPrediction: StagePrediction?
    private let webSocketManager = WebSocketManager()
    private var epochIndex: Int = 0

    // Epoch buffer: accumulates raw sensor data between drains
    private var bufferedHRSamples: [Double] = []
    private var bufferedHRVSamples: [Double] = []
    private var bufferedAccelX: [Float] = []
    private var bufferedAccelY: [Float] = []
    private var bufferedAccelZ: [Float] = []

    /// Progression manager injected from the app entry point.
    /// Used to update streaks and award XP after sessions.
    var progressionManager: ProgressionManager?

    // Components
    private let store = SleepSessionStore()
    private let connectivityManager = PhoneConnectivityManager()
    private let morningSyncManager = MorningSyncManager()
    private let exporter = JSONExporter()
    private var sessionUploader: SessionUploader?

    private var sonarEngine: SonarEngine?
    private var passiveAnalyzer: PassiveAudioAnalyzer?
    private var featureDrainTask: Task<Void, Never>?
    private var durationTask: Task<Void, Never>?
    private var sessionStart: Date?

    init() {
        setupConnectivityCallbacks()
        connectivityManager.activate()
    }

    /// Start a sleep data collection session on the phone.
    func startSession() async throws {
        guard !isSessionActive else { return }

        let start = Date()
        sessionStart = start
        sleepStagesSynced = false
        packetsReceived = 0

        // Start data store
        _ = await store.startSession()

        // Initialize audio pipeline
        let analyzer = PassiveAudioAnalyzer(sessionStart: start)
        let sonar = SonarEngine(sessionStart: start, passiveAnalyzer: analyzer)
        passiveAnalyzer = analyzer
        sonarEngine = sonar

        try await sonar.start()
        isSonarRunning = await sonar.isRunning

        // Start periodic feature drain (sonar + audio → store)
        featureDrainTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(SensorConstants.batchInterval))
                guard !Task.isCancelled else { break }
                await self?.drainFeatures()
            }
        }

        // Start duration timer
        durationTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(1))
                guard let self, let start = self.sessionStart else { continue }
                self.sessionDuration = Date().timeIntervalSince(start)
            }
        }

        isSessionActive = true

        // Connect to inference server
        if let token = KeychainHelper.read(key: "accessToken") {
            webSocketManager.connect(accessToken: token)
        }
        epochIndex = 0
        bufferedHRSamples.removeAll()
        bufferedHRVSamples.removeAll()
        bufferedAccelX.removeAll()
        bufferedAccelY.removeAll()
        bufferedAccelZ.removeAll()

        if let sessionId = await store.currentSession()?.id {
            webSocketManager.sendSessionStart(
                sessionId: sessionId.uuidString,
                startedAt: Date()
            )
        }
    }

    /// Stop the current session.
    func stopSession() async {
        guard isSessionActive else { return }

        featureDrainTask?.cancel()
        featureDrainTask = nil
        durationTask?.cancel()
        durationTask = nil

        // Final feature drain
        await drainFeatures()

        // Stop audio
        await sonarEngine?.stop()
        isSonarRunning = false
        sonarEngine = nil
        passiveAnalyzer = nil

        // End session in store
        await store.endSession()

        // Update streak on session completion
        await progressionManager?.updateStreak(sessionDate: Date())

        webSocketManager.sendSessionEnd()

        isSessionActive = false
    }

    /// Sync HealthKit sleep stages for a specific or the current session.
    func syncSleepStages(for session: SleepSession? = nil) async throws {
        let start: Date
        let end: Date
        if let session {
            start = session.startDate
            end = session.endDate ?? Date()
        } else {
            guard let s = sessionStart else {
                throw CoordinatorError.noActiveSession("No session available for sleep stage sync.")
            }
            start = s
            end = Date()
        }

        try await morningSyncManager.requestAuthorization()
        let stages = try await morningSyncManager.fetchSleepStages(
            sessionStart: start,
            sessionEnd: end
        )
        await store.setSleepStages(stages)
        sleepStagesSynced = true
    }

    /// Export a specific or the current session to JSON and return the file URL.
    func exportSession(_ session: SleepSession? = nil) async throws -> URL {
        let target: SleepSession
        if let session {
            target = session
        } else if let current = await store.currentSession() {
            target = current
        } else {
            throw CoordinatorError.noActiveSession("No session available to export.")
        }
        return try await exporter.export(target)
    }

    /// Get a summary string for the current session.
    func sessionSummary() async -> String? {
        guard let session = await store.currentSession() else { return nil }
        return await exporter.summary(session)
    }

    /// Upload a specific or the current session to the server.
    func uploadSession(apiClient: APIClient, session: SleepSession? = nil) async throws {
        let target: SleepSession
        if let session {
            target = session
        } else if let current = await store.currentSession() {
            target = current
        } else {
            throw CoordinatorError.noActiveSession("No session available to upload.")
        }

        isUploading = true
        uploadError = nil
        defer { isUploading = false }

        let uploader = SessionUploader(apiClient: apiClient)
        do {
            try await uploader.upload(target)
        } catch {
            uploadError = error.localizedDescription
            throw error
        }
    }

    /// Whether there is a completed (non-active) session available.
    var hasCompletedSession: Bool {
        sessionStart != nil && !isSessionActive
    }

    /// Get lightweight summaries of all stored sessions.
    func allSessionSummaries() async -> [SessionSummary] {
        await store.allSessionSummaries()
    }

    /// Load a full session from a file URL.
    func loadSession(from url: URL) async -> SleepSession? {
        await store.loadSession(from: url)
    }

    /// List URLs of all past session files.
    func pastSessionURLs() async -> [URL] {
        await store.allSessionURLs()
    }

    /// Formatted session duration string.
    var formattedDuration: String {
        let hours = Int(sessionDuration) / 3600
        let minutes = (Int(sessionDuration) % 3600) / 60
        let seconds = Int(sessionDuration) % 60
        return String(format: "%dh %02dm %02ds", hours, minutes, seconds)
    }

    // MARK: - Private

    private func setupConnectivityCallbacks() {
        connectivityManager.onPacketReceived = { [weak self] packet in
            guard let self else { return }
            Task {
                await self.store.appendWatchPacket(packet)
                await MainActor.run {
                    self.packetsReceived += 1
                    if let lastHR = packet.heartRateSamples.last {
                        self.lastHeartRate = lastHR.bpm
                    }
                    // Buffer raw sensor data for next epoch payload
                    self.bufferedHRSamples.append(contentsOf: packet.heartRateSamples.map(\.bpm))
                    self.bufferedHRVSamples.append(contentsOf: packet.hrvSamples.map(\.sdnn))
                    self.bufferedAccelX.append(contentsOf: packet.accelerometerSamples.map(\.x))
                    self.bufferedAccelY.append(contentsOf: packet.accelerometerSamples.map(\.y))
                    self.bufferedAccelZ.append(contentsOf: packet.accelerometerSamples.map(\.z))
                }
            }
        }

        connectivityManager.onReachabilityChanged = { [weak self] reachable in
            guard let coordinator = self else { return }
            Task { @MainActor in
                coordinator.isWatchConnected = reachable
            }
        }
    }

    private func drainFeatures() async {
        let sonarFeatures = await sonarEngine?.drainFeatures()
        if let sonarFeatures, !sonarFeatures.isEmpty {
            await store.appendSonarFeatures(sonarFeatures)
            if let lastBreathing = sonarFeatures.last?.breathingRate {
                lastBreathingRate = lastBreathing
            }
        }

        let audioFeatures = await passiveAnalyzer?.drainFeatures()
        if let audioFeatures, !audioFeatures.isEmpty {
            await store.appendAudioFeatures(audioFeatures)
        }

        // Stream epoch to inference server
        let epochData: [String: Any] = [
            "hr_samples": bufferedHRSamples,
            "hrv_samples": bufferedHRVSamples,
            "accel_x": bufferedAccelX.map { Double($0) },
            "accel_y": bufferedAccelY.map { Double($0) },
            "accel_z": bufferedAccelZ.map { Double($0) },
            "sonar_breathing_rate": sonarFeatures?.last?.breathingRate as Any,
            "sonar_amplitude": sonarFeatures?.last?.signalStrength as Any,
            "audio_rms": audioFeatures?.last?.rmsEnergy as Any,
            "audio_zcr": audioFeatures?.last?.zeroCrossingRate as Any,
            "audio_spectral_centroid": audioFeatures?.last?.spectralCentroid as Any,
            "audio_class": audioFeatures?.last?.classification.rawValue as Any,
        ]

        webSocketManager.sendSensorEpoch(
            epochIndex: epochIndex,
            timestamp: Date(),
            data: epochData
        )
        epochIndex += 1

        // Clear buffers for next epoch
        bufferedHRSamples.removeAll()
        bufferedHRVSamples.removeAll()
        bufferedAccelX.removeAll()
        bufferedAccelY.removeAll()
        bufferedAccelZ.removeAll()

        // Update current prediction from WebSocket
        if let prediction = webSocketManager.lastPrediction {
            currentPrediction = prediction
        }
    }
}
