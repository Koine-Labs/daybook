import Foundation
import Observation

// MARK: - DreamStore (actor)

/// Thread-safe dream journal persistence.
/// Stores entries as individual JSON files in `Documents/dreams/{uuid}.json`.
actor DreamStore {

    // MARK: State

    private let storageURL: URL
    private var cache: [UUID: DreamEntry]?  // nil = not yet loaded

    // MARK: Init

    init() {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
        storageURL = docs.appendingPathComponent("dreams", isDirectory: true)
        try? FileManager.default.createDirectory(at: storageURL, withIntermediateDirectories: true)
    }

    // MARK: Private Helpers

    private func ensureLoaded() {
        guard cache == nil else { return }
        var loaded: [UUID: DreamEntry] = [:]
        let urls = (try? FileManager.default.contentsOfDirectory(
            at: storageURL,
            includingPropertiesForKeys: nil
        ).filter { $0.pathExtension == "json" }) ?? []
        for url in urls {
            guard let data = try? Data(contentsOf: url),
                  let entry = try? Self.decode(data) else { continue }
            loaded[entry.id] = entry
        }
        cache = loaded
    }

    // nonisolated helpers avoid Swift 6 actor-isolation warnings when calling
    // Codable conformances that were synthesised outside the actor.
    private nonisolated static func decode(_ data: Data) throws -> DreamEntry {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return try decoder.decode(DreamEntry.self, from: data)
    }

    private nonisolated static func encode(_ entry: DreamEntry) throws -> Data {
        let enc = JSONEncoder()
        enc.dateEncodingStrategy = .iso8601
        enc.outputFormatting = [.prettyPrinted, .sortedKeys]
        return try enc.encode(entry)
    }

    private func fileURL(for id: UUID) -> URL {
        storageURL.appendingPathComponent("\(id).json")
    }

    // MARK: Public API

    func save(_ entry: DreamEntry) throws {
        ensureLoaded()
        let data = try Self.encode(entry)
        try data.write(to: fileURL(for: entry.id), options: .atomic)
        cache?[entry.id] = entry
    }

    func delete(_ id: UUID) throws {
        ensureLoaded()
        let url = fileURL(for: id)
        if FileManager.default.fileExists(atPath: url.path) {
            try FileManager.default.removeItem(at: url)
        }
        cache?[id] = nil
    }

    func entry(for id: UUID) -> DreamEntry? {
        ensureLoaded()
        return cache?[id]
    }

    func allEntries() -> [DreamEntry] {
        ensureLoaded()
        return (cache?.values).map { Array($0) } ?? []
    }

    func entry(forSessionId sessionId: UUID) -> DreamEntry? {
        ensureLoaded()
        return cache?.values.first { $0.sessionId == sessionId }
    }

    func sessionIdsWithDreams() -> Set<UUID> {
        ensureLoaded()
        let ids = cache?.values.compactMap { $0.sessionId } ?? []
        return Set(ids)
    }

    func totalCount() -> Int {
        ensureLoaded()
        return cache?.count ?? 0
    }

    func lucidCount() -> Int {
        ensureLoaded()
        return cache?.values.filter { $0.isLucid }.count ?? 0
    }
}

// MARK: - DreamStoreManager (@Observable wrapper)

/// MainActor-bound wrapper around `DreamStore` for SwiftUI environment injection.
@Observable
@MainActor
final class DreamStoreManager {

    // MARK: Published state

    private(set) var entries: [DreamEntry] = []
    private(set) var isLoaded: Bool = false

    // MARK: Private

    private let store = DreamStore()

    // MARK: API

    func load() async {
        let all = await store.allEntries()
        entries = all.sorted { $0.date > $1.date }
        isLoaded = true
    }

    func save(_ entry: DreamEntry) async throws {
        try await store.save(entry)
        // Refresh list
        let all = await store.allEntries()
        entries = all.sorted { $0.date > $1.date }
    }

    func delete(_ id: UUID) async throws {
        try await store.delete(id)
        entries.removeAll { $0.id == id }
    }

    func entry(forSessionId sessionId: UUID) async -> DreamEntry? {
        await store.entry(forSessionId: sessionId)
    }

    func sessionIdsWithDreams() async -> Set<UUID> {
        await store.sessionIdsWithDreams()
    }
}
