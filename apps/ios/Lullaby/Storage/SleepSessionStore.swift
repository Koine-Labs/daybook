import Foundation
#if canImport(UIKit)
import UIKit
#endif

/// Lightweight summary of a stored session, avoiding loading the full 15-50MB JSON.
struct SessionSummary: Identifiable, Sendable, Hashable {
    let id: UUID
    let startDate: Date
    let endDate: Date?
    let duration: TimeInterval
    let watchPacketCount: Int
    let sleepStageCount: Int
    let hasSleepStages: Bool
    let fileURL: URL
    let fileSizeBytes: Int
}

/// Central data aggregator for a sleep session on the iPhone.
///
/// Receives data from WatchConnectivity, sonar engine, audio analyzer, and HealthKit.
/// Persists the active session to disk periodically for crash recovery.
actor SleepSessionStore {
    private(set) var activeSession: SleepSession?
    private let storageURL: URL

    init() {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
        storageURL = docs.appendingPathComponent("sessions", isDirectory: true)
        try? FileManager.default.createDirectory(at: storageURL, withIntermediateDirectories: true)
    }

    /// Start a new sleep session. Returns the session ID.
    func startSession() async -> UUID {
        let battery = await Self.batteryLevel()
        let session = SleepSession(
            id: UUID(),
            startDate: Date(),
            endDate: nil,
            watchPackets: [],
            sonarFeatures: [],
            audioFeatures: [],
            sleepStages: [],
            metadata: SessionMetadata(
                appVersion: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "0.1",
                watchModel: nil,
                iphoneModel: Self.deviceModel(),
                osVersionWatch: nil,
                osVersioniOS: Self.osVersion(),
                watchBatteryAtStart: nil,
                watchBatteryAtEnd: nil,
                phoneBatteryAtStart: battery,
                phoneBatteryAtEnd: nil,
                totalPacketsReceived: 0,
                totalPacketsExpected: nil,
                connectivityDropCount: 0
            )
        )
        self.activeSession = session
        persist()
        return session.id
    }

    /// Append a sensor packet received from the watch.
    func appendWatchPacket(_ packet: SensorPacket) {
        activeSession?.watchPackets.append(packet)
        activeSession?.metadata.totalPacketsReceived += 1

        // Persist periodically for crash recovery
        if (activeSession?.watchPackets.count ?? 0) % SensorConstants.persistenceInterval == 0 {
            persist()
        }
    }

    /// Append sonar-derived breathing features.
    func appendSonarFeatures(_ features: [SonarFeatureSample]) {
        activeSession?.sonarFeatures.append(contentsOf: features)
    }

    /// Append passive audio classification features.
    func appendAudioFeatures(_ features: [AudioFeatureSample]) {
        activeSession?.audioFeatures.append(contentsOf: features)
    }

    /// Set the HealthKit sleep stage labels (ground truth).
    func setSleepStages(_ stages: [SleepStageLabel]) {
        activeSession?.sleepStages = stages
        persist()
    }

    /// End the active session and finalize metadata.
    func endSession() async {
        let battery = await Self.batteryLevel()
        activeSession?.endDate = Date()
        activeSession?.metadata.phoneBatteryAtEnd = battery
        persist()
    }

    /// Get the active session snapshot (for UI display or export).
    func currentSession() -> SleepSession? {
        activeSession
    }

    /// Clear the active session reference (after export or on new session start).
    func clearActiveSession() {
        activeSession = nil
    }

    /// List all saved session files.
    func allSessionURLs() -> [URL] {
        (try? FileManager.default.contentsOfDirectory(
            at: storageURL,
            includingPropertiesForKeys: [.creationDateKey]
        ).filter { $0.pathExtension == "json" }
        .sorted { $0.lastPathComponent > $1.lastPathComponent }) ?? []
    }

    /// Load a session by its UUID.
    func loadSession(id: UUID) -> SleepSession? {
        let fileURL = storageURL.appendingPathComponent("\(id).json")
        return loadSession(from: fileURL)
    }

    /// Load a session from a file URL.
    func loadSession(from url: URL) -> SleepSession? {
        guard let data = try? Data(contentsOf: url) else { return nil }
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return try? decoder.decode(SleepSession.self, from: data)
    }

    /// Build lightweight summaries for all stored sessions, sorted newest first.
    func allSessionSummaries() -> [SessionSummary] {
        let urls = allSessionURLs()
        var summaries: [SessionSummary] = []
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601

        for url in urls {
            guard let data = try? Data(contentsOf: url) else { continue }
            let fileSize = (try? FileManager.default.attributesOfItem(atPath: url.path)[.size] as? Int) ?? data.count
            guard let session = try? decoder.decode(SleepSession.self, from: data) else { continue }
            let duration = (session.endDate ?? Date()).timeIntervalSince(session.startDate)
            summaries.append(SessionSummary(
                id: session.id,
                startDate: session.startDate,
                endDate: session.endDate,
                duration: duration,
                watchPacketCount: session.watchPackets.count,
                sleepStageCount: session.sleepStages.count,
                hasSleepStages: !session.sleepStages.isEmpty,
                fileURL: url,
                fileSizeBytes: fileSize
            ))
        }
        return summaries
    }

    // MARK: - Persistence

    private func persist() {
        guard let session = activeSession else { return }
        let fileURL = storageURL.appendingPathComponent("\(session.id).json")
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        guard let data = try? encoder.encode(session) else { return }
        try? data.write(to: fileURL, options: .atomic)
    }

    // MARK: - Device Info

    private static func deviceModel() -> String {
        var systemInfo = utsname()
        uname(&systemInfo)
        return withUnsafePointer(to: &systemInfo.machine) {
            $0.withMemoryRebound(to: CChar.self, capacity: 1) {
                String(validatingCString: $0) ?? "Unknown"
            }
        }
    }

    private static func osVersion() -> String {
        let version = ProcessInfo.processInfo.operatingSystemVersion
        return "\(version.majorVersion).\(version.minorVersion).\(version.patchVersion)"
    }

    /// Get battery level. Must be called from MainActor due to UIDevice.
    @MainActor private static func batteryLevel() -> Float? {
        #if canImport(UIKit)
        UIDevice.current.isBatteryMonitoringEnabled = true
        let level = UIDevice.current.batteryLevel
        return level >= 0 ? level : nil
        #else
        return nil
        #endif
    }
}
