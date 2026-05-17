import Foundation

/// Exports sleep session data to JSON files for offline analysis.
actor JSONExporter {

    /// Export a session to a JSON file and return its URL for sharing.
    func export(_ session: SleepSession) throws -> URL {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]

        let data = try encoder.encode(session)

        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd_HH-mm"
        let dateString = formatter.string(from: session.startDate)
        let fileName = "lullaby_session_\(dateString).json"

        let exportDir = FileManager.default.temporaryDirectory
        let fileURL = exportDir.appendingPathComponent(fileName)
        try data.write(to: fileURL, options: .atomic)

        return fileURL
    }

    /// Generate a human-readable summary of session data for quick verification.
    func summary(_ session: SleepSession) -> String {
        let duration = (session.endDate ?? Date()).timeIntervalSince(session.startDate)
        let hours = Int(duration) / 3600
        let minutes = (Int(duration) % 3600) / 60

        let totalHR = session.watchPackets.reduce(0) { $0 + $1.heartRateSamples.count }
        let totalHRV = session.watchPackets.reduce(0) { $0 + $1.hrvSamples.count }
        let totalAccel = session.watchPackets.reduce(0) { $0 + $1.accelerometerSamples.count }

        return """
        Session: \(session.id.uuidString.prefix(8))
        Duration: \(hours)h \(minutes)m
        Watch packets: \(session.watchPackets.count)
        HR samples: \(totalHR)
        HRV samples: \(totalHRV)
        Accel samples: \(totalAccel)
        Sonar features: \(session.sonarFeatures.count)
        Audio features: \(session.audioFeatures.count)
        Sleep stages: \(session.sleepStages.count)
        """
    }
}
