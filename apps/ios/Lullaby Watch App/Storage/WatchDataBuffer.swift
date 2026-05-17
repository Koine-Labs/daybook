import Foundation

/// File-backed buffer for sensor packets on the Apple Watch.
///
/// When the iPhone is unreachable, packets are persisted to disk so they
/// survive app termination and can be flushed when connectivity resumes.
actor WatchDataBuffer {
    private let bufferDirectory: URL
    private var pendingPackets: [ConnectivityEnvelope] = []

    init() {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
        bufferDirectory = docs.appendingPathComponent("packet_buffer", isDirectory: true)
        try? FileManager.default.createDirectory(at: bufferDirectory, withIntermediateDirectories: true)
    }

    /// Add a packet to the buffer and persist to disk.
    func enqueue(_ envelope: ConnectivityEnvelope) {
        pendingPackets.append(envelope)

        // Enforce max buffer size
        if pendingPackets.count > SensorConstants.watchBufferMaxPackets {
            let removed = pendingPackets.removeFirst()
            removeFile(for: removed)
        }

        persistToDisk(envelope)
    }

    /// Drain all buffered packets for transmission. Clears the buffer.
    func drainAll() -> [ConnectivityEnvelope] {
        let drained = pendingPackets
        pendingPackets.removeAll()
        clearDiskBuffer()
        return drained
    }

    /// Number of packets currently buffered.
    var count: Int { pendingPackets.count }

    /// Whether there are packets waiting to be sent.
    var hasPending: Bool { !pendingPackets.isEmpty }

    /// Restore any packets persisted from a previous app launch.
    func restoreFromDisk() {
        guard let files = try? FileManager.default.contentsOfDirectory(
            at: bufferDirectory,
            includingPropertiesForKeys: [.creationDateKey],
            options: .skipsHiddenFiles
        ) else { return }

        let sortedFiles = files
            .filter { $0.pathExtension == "json" }
            .sorted { ($0.lastPathComponent) < ($1.lastPathComponent) }

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .deferredToDate

        for file in sortedFiles {
            guard
                let data = try? Data(contentsOf: file),
                let envelope = try? decoder.decode(ConnectivityEnvelope.self, from: data)
            else { continue }
            pendingPackets.append(envelope)
        }
    }

    // MARK: - Private

    private func persistToDisk(_ envelope: ConnectivityEnvelope) {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .deferredToDate
        guard let data = try? encoder.encode(envelope) else { return }

        let fileName = String(format: "%010llu.json", envelope.sequenceNumber)
        let fileURL = bufferDirectory.appendingPathComponent(fileName)
        try? data.write(to: fileURL, options: .atomic)
    }

    private func removeFile(for envelope: ConnectivityEnvelope) {
        let fileName = String(format: "%010llu.json", envelope.sequenceNumber)
        let fileURL = bufferDirectory.appendingPathComponent(fileName)
        try? FileManager.default.removeItem(at: fileURL)
    }

    private func clearDiskBuffer() {
        guard let files = try? FileManager.default.contentsOfDirectory(
            at: bufferDirectory,
            includingPropertiesForKeys: nil
        ) else { return }
        for file in files {
            try? FileManager.default.removeItem(at: file)
        }
    }
}
