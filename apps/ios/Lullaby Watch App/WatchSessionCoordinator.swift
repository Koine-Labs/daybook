import Foundation
@preconcurrency import WatchConnectivity

/// Orchestrates all watch-side components during a sleep session.
///
/// Manages the lifecycle of: WorkoutSessionManager, HeartRateCollector, HRVCollector,
/// MotionCollector, WatchConnectivityManager, and the periodic batch timer.
@Observable
final class WatchSessionCoordinator {
    // Published state for UI
    private(set) var isSessionActive = false
    private(set) var lastHeartRate: Double = 0
    private(set) var packetsSent: UInt32 = 0
    private(set) var isPhoneReachable = false
    private(set) var bufferedPacketCount: Int = 0

    // Components
    private let workoutManager = WorkoutSessionManager()
    private var hrCollector: HeartRateCollector?
    private var hrvCollector: HRVCollector?
    private var motionCollector: MotionCollector?
    private let buffer: WatchDataBuffer
    private let connectivityManager: WatchConnectivityManager

    // Session state
    private var sessionID: UUID?
    private var sessionStart: Date?
    private var batchIndex: UInt32 = 0
    private var batchTask: Task<Void, Never>?

    init() {
        let buf = WatchDataBuffer()
        self.buffer = buf
        self.connectivityManager = WatchConnectivityManager(buffer: buf)
        connectivityManager.activate()
    }

    /// Start a new sleep recording session.
    func startSession() async throws {
        guard !isSessionActive else { return }

        let start = Date()
        let id = UUID()
        sessionID = id
        sessionStart = start
        batchIndex = 0
        packetsSent = 0

        // Start workout session for background sensor access
        try await workoutManager.requestAuthorization()
        try await workoutManager.startSession()

        // Initialize and start collectors
        let hr = HeartRateCollector(sessionStart: start)
        let hrv = HRVCollector(sessionStart: start)
        let motion = MotionCollector(sessionStart: start)

        hrCollector = hr
        hrvCollector = hrv
        motionCollector = motion

        await hr.start()
        await hrv.start()
        motion.start()

        // Notify phone that session started
        connectivityManager.sendCommand(.sessionStarted)

        // Start periodic batch assembly
        batchTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(SensorConstants.batchInterval))
                guard !Task.isCancelled else { break }
                await self?.assembleBatchAndSend()
            }
        }

        isSessionActive = true
    }

    /// Stop the current session.
    func stopSession() async throws {
        guard isSessionActive else { return }

        batchTask?.cancel()
        batchTask = nil

        // Final batch flush
        await assembleBatchAndSend()

        // Stop collectors
        motionCollector?.stop()
        await hrCollector?.stop()
        await hrvCollector?.stop()

        // Stop workout session
        try await workoutManager.stopSession()

        // Notify phone
        connectivityManager.sendCommand(.sessionStopped)

        // Reset state
        hrCollector = nil
        hrvCollector = nil
        motionCollector = nil
        isSessionActive = false
    }

    // MARK: - Batch Assembly

    private func assembleBatchAndSend() async {
        guard let sessionID, sessionStart != nil else { return }

        let hr = await hrCollector?.drainSamples() ?? []
        let hrv = await hrvCollector?.drainSamples() ?? []
        let accel = motionCollector?.drainSamples() ?? []
        let gyro = motionCollector?.drainGyroSamples() ?? []

        // Update UI with latest HR
        if let lastHR = hr.last {
            lastHeartRate = lastHR.bpm
        }

        let packet = SensorPacket(
            sessionID: sessionID,
            batchIndex: batchIndex,
            capturedAt: Date(),
            heartRateSamples: hr,
            hrvSamples: hrv,
            accelerometerSamples: accel,
            gyroscopeSamples: gyro
        )
        batchIndex += 1

        connectivityManager.sendPacket(packet)
        packetsSent += 1

        // Update buffer status
        bufferedPacketCount = await buffer.count
        isPhoneReachable = WCSession.default.isReachable
    }
}
