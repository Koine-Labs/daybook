import Foundation
import Observation

/// Persistent retry queue for session uploads.
/// Stores pending upload IDs on disk and retries with exponential backoff.
@Observable
@MainActor
final class UploadQueue {
    private(set) var pendingCount = 0
    private(set) var isUploading = false
    private(set) var lastError: String?

    private let uploader: SessionUploader
    private let store: SleepSessionStore
    private var retryTask: Task<Void, Never>?

    private static let pendingKey = "lullaby_pending_uploads"
    private static let maxRetries = 5

    init(uploader: SessionUploader, store: SleepSessionStore) {
        self.uploader = uploader
        self.store = store
        self.pendingCount = Self.loadPendingIDs().count
    }

    /// Enqueue a session for upload.
    func enqueue(sessionId: UUID) {
        var pending = Self.loadPendingIDs()
        let entry = PendingUpload(sessionId: sessionId.uuidString, retryCount: 0)
        if !pending.contains(where: { $0.sessionId == entry.sessionId }) {
            pending.append(entry)
            Self.savePendingIDs(pending)
            pendingCount = pending.count
        }
        startProcessing()
    }

    /// Process the queue (called on app launch and after enqueue).
    func startProcessing() {
        guard retryTask == nil else { return }

        retryTask = Task { [weak self] in
            await self?.processQueue()
            await MainActor.run { self?.retryTask = nil }
        }
    }

    // MARK: - Internal

    private func processQueue() async {
        let pending = Self.loadPendingIDs()
        guard !pending.isEmpty else { return }

        await MainActor.run { isUploading = true }

        var remaining: [PendingUpload] = []

        for entry in pending {
            guard !Task.isCancelled else { break }

            guard let session = await loadSession(id: entry.sessionId) else {
                // Session file gone — skip
                continue
            }

            do {
                try await uploader.upload(session)
                await MainActor.run {
                    lastError = nil
                    pendingCount = max(0, pendingCount - 1)
                }
            } catch {
                let next = PendingUpload(
                    sessionId: entry.sessionId,
                    retryCount: entry.retryCount + 1
                )
                if next.retryCount < Self.maxRetries {
                    remaining.append(next)
                    // Exponential backoff: 2^retry seconds (2, 4, 8, 16, 32)
                    let delay = UInt64(pow(2.0, Double(next.retryCount))) * 1_000_000_000
                    try? await Task.sleep(nanoseconds: delay)
                }
                await MainActor.run {
                    lastError = error.localizedDescription
                }
            }
        }

        Self.savePendingIDs(remaining)
        await MainActor.run {
            pendingCount = remaining.count
            isUploading = false
        }
    }

    private func loadSession(id: String) async -> SleepSession? {
        guard let uuid = UUID(uuidString: id) else { return nil }
        return await store.loadSession(id: uuid)
    }

    // MARK: - Persistence

    private struct PendingUpload: Codable {
        let sessionId: String
        var retryCount: Int
    }

    private static func loadPendingIDs() -> [PendingUpload] {
        guard let data = UserDefaults.standard.data(forKey: pendingKey),
              let ids = try? JSONDecoder().decode([PendingUpload].self, from: data) else {
            return []
        }
        return ids
    }

    private static func savePendingIDs(_ ids: [PendingUpload]) {
        if let data = try? JSONEncoder().encode(ids) {
            UserDefaults.standard.set(data, forKey: pendingKey)
        }
    }
}
