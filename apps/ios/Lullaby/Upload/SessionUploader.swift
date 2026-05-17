import Foundation

/// Uploads a SleepSession to the server (two-step: blob then metadata).
/// Mirrors JSONExporter's encoding to maintain format compatibility.
actor SessionUploader {
    private let apiClient: APIClient

    init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    /// Upload a session: serialize → PUT blob → POST metadata.
    func upload(_ session: SleepSession) async throws {
        // Step 1: Serialize using the same encoder as JSONExporter
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        encoder.outputFormatting = [.sortedKeys]
        let data = try encoder.encode(session)

        // Step 2: Upload blob to R2
        _ = try await apiClient.uploadData(
            .uploadBlob(sessionId: session.id.uuidString),
            data: data
        )

        // Step 3: Register metadata in D1
        let duration = session.endDate.map { $0.timeIntervalSince(session.startDate) }
        let metadata = SessionMetadataPayload(
            id: session.id.uuidString,
            startDate: ISO8601DateFormatter().string(from: session.startDate),
            endDate: session.endDate.map { ISO8601DateFormatter().string(from: $0) },
            durationSeconds: duration,
            watchPacketCount: session.watchPackets.count,
            sleepStageCount: session.sleepStages.count,
            notes: nil
        )

        struct CreateResponse: Decodable { let id: String }
        let _: CreateResponse = try await apiClient.request(.createSession, body: metadata)
    }
}

// MARK: - Metadata payload

private nonisolated struct SessionMetadataPayload: Encodable, Sendable {
    let id: String
    let startDate: String
    let endDate: String?
    let durationSeconds: TimeInterval?
    let watchPacketCount: Int
    let sleepStageCount: Int
    let notes: String?
}
