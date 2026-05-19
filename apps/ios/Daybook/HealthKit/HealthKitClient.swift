import Foundation
import HealthKit
import Observation

// HealthKitClient — iOS side of #13.
//
// Reads HRV (SDNN), heart rate, and sleep stages from HealthKit (which itself
// is fed by the user's Apple Watch + iPhone). Batches the new samples into
// the format the FastAPI /state/sensor_readings endpoint expects and hands
// them off to APIClient for upload.
//
// Mirrors the watch's HeartRateClient pattern: HKAnchoredObjectQuery per
// sample type, anchors persisted in UserDefaults so subsequent calls only
// pull NEW samples since last sync. Authorization is requested once on
// first start(); on permission denial the client stays silent (no fake
// data, no spam logs) and the UI falls back to its empty-state copy.
//
// Permissions required (wired separately):
//   - Info.plist  NSHealthShareUsageDescription
//   - Daybook target entitlement: com.apple.developer.healthkit (true)
//
// Simulator behavior: HealthKit returns no samples → fetchAndUpload is a
// no-op and the UI stays in empty state. That's correct.

@MainActor
@Observable
final class HealthKitClient {
    static let shared = HealthKitClient()

    private let store = HKHealthStore()

    /// Server-side cap is also 200; we batch to stay safely under.
    private let maxBatch = 200

    /// Per-type anchors persisted across launches so we only fetch deltas.
    private let anchorDefaultsPrefix = "daybook.healthkit.anchor."

    /// Public state — observable so views can react.
    private(set) var authorized: Bool = false
    private(set) var lastUploadAt: Date? = nil
    private(set) var lastError: String? = nil

    var isAvailable: Bool { HKHealthStore.isHealthDataAvailable() }

    private init() {}

    // MARK: - Sample types we care about

    private var readTypes: Set<HKObjectType> {
        var set: Set<HKObjectType> = []
        if let t = HKQuantityType.quantityType(forIdentifier: .heartRate) { set.insert(t) }
        if let t = HKQuantityType.quantityType(forIdentifier: .heartRateVariabilitySDNN) { set.insert(t) }
        if let t = HKCategoryType.categoryType(forIdentifier: .sleepAnalysis) { set.insert(t) }
        return set
    }

    // MARK: - Public API

    /// Request authorization (once) and remember the result.
    func requestAuthorizationIfNeeded() async {
        guard isAvailable else { return }
        do {
            try await store.requestAuthorization(toShare: [], read: readTypes)
            authorized = true
        } catch {
            authorized = false
            lastError = error.localizedDescription
        }
    }

    /// Pull new samples for each tracked type and POST them to the bridge.
    /// Safe to call repeatedly — anchors ensure each sample is uploaded once.
    func fetchAndUpload(api: APIClient) async {
        guard isAvailable, authorized else { return }

        var pending: [APIClient.SensorReadingIn] = []
        var latestRecordedAt: Date? = nil

        if let t = HKQuantityType.quantityType(forIdentifier: .heartRate) {
            let (readings, latest) = await fetchNew(type: t, kind: "heart_rate") { sample in
                guard let q = sample as? HKQuantitySample else { return nil }
                let unit = HKUnit.count().unitDivided(by: .minute())
                let bpm = q.quantity.doubleValue(for: unit)
                return ["bpm": .double(bpm)]
            }
            pending.append(contentsOf: readings)
            latestRecordedAt = laterOf(latestRecordedAt, latest)
        }

        if let t = HKQuantityType.quantityType(forIdentifier: .heartRateVariabilitySDNN) {
            let (readings, latest) = await fetchNew(type: t, kind: "hrv") { sample in
                guard let q = sample as? HKQuantitySample else { return nil }
                let ms = q.quantity.doubleValue(for: .secondUnit(with: .milli))
                // Preserve historical key name from parse_apple_health.py so
                // the server's /state/body queries (which read rmssdMs/ms/value)
                // pick this up immediately.
                return ["rmssdMs": .double(ms)]
            }
            pending.append(contentsOf: readings)
            latestRecordedAt = laterOf(latestRecordedAt, latest)
        }

        if let t = HKCategoryType.categoryType(forIdentifier: .sleepAnalysis) {
            let (readings, latest) = await fetchNew(type: t, kind: "sleep_stage") { sample in
                guard let c = sample as? HKCategorySample else { return nil }
                let stage = Self.sleepStageString(for: c.value)
                return [
                    "stage": .string(stage),
                    "startAt": .string(Self.iso(c.startDate)),
                    "endAt": .string(Self.iso(c.endDate)),
                ]
            }
            pending.append(contentsOf: readings)
            latestRecordedAt = laterOf(latestRecordedAt, latest)
        }

        guard !pending.isEmpty else { return }

        // Server caps at 200/request — chunk and upload sequentially.
        for chunk in pending.chunked(into: maxBatch) {
            do {
                _ = try await api.sendSensorReadings(chunk)
            } catch {
                lastError = "upload failed: \(error)"
                return  // keep anchors as-is so we retry next sweep
            }
        }

        lastUploadAt = Date()
        lastError = nil
    }

    // MARK: - Internals

    /// Fetch new samples since the persisted anchor; return readings + the
    /// most-recent recorded_at, and persist the new anchor on success.
    private func fetchNew(
        type: HKSampleType,
        kind: String,
        convert: @escaping @Sendable (HKSample) -> [String: APIClient.AnyPayloadValue]?
    ) async -> ([APIClient.SensorReadingIn], Date?) {
        let oldAnchor = loadAnchor(for: type)

        return await withCheckedContinuation { (cont: CheckedContinuation<([APIClient.SensorReadingIn], Date?), Never>) in
            let q = HKAnchoredObjectQuery(
                type: type,
                predicate: nil,
                anchor: oldAnchor,
                limit: HKObjectQueryNoLimit
            ) { [weak self] _, samples, _, newAnchor, _ in
                guard let self else {
                    cont.resume(returning: ([], nil))
                    return
                }
                var out: [APIClient.SensorReadingIn] = []
                var latest: Date? = nil
                for s in samples ?? [] {
                    guard let payload = convert(s) else { continue }
                    out.append(.init(
                        recorded_at: s.startDate,
                        source: "IPHONE",
                        kind: kind,
                        payload: payload
                    ))
                    if latest == nil || s.startDate > latest! {
                        latest = s.startDate
                    }
                }
                if let newAnchor {
                    Task { @MainActor in self.saveAnchor(newAnchor, for: type) }
                }
                cont.resume(returning: (out, latest))
            }
            store.execute(q)
        }
    }

    private func anchorKey(_ type: HKSampleType) -> String {
        anchorDefaultsPrefix + type.identifier
    }

    private func loadAnchor(for type: HKSampleType) -> HKQueryAnchor? {
        guard let data = UserDefaults.standard.data(forKey: anchorKey(type)) else { return nil }
        return try? NSKeyedUnarchiver.unarchivedObject(ofClass: HKQueryAnchor.self, from: data)
    }

    private func saveAnchor(_ anchor: HKQueryAnchor, for type: HKSampleType) {
        guard let data = try? NSKeyedArchiver.archivedData(
            withRootObject: anchor,
            requiringSecureCoding: true
        ) else { return }
        UserDefaults.standard.set(data, forKey: anchorKey(type))
    }

    private func laterOf(_ a: Date?, _ b: Date?) -> Date? {
        switch (a, b) {
        case (nil, nil): return nil
        case (let x?, nil): return x
        case (nil, let y?): return y
        case (let x?, let y?): return x > y ? x : y
        }
    }

    // HKCategoryValueSleepAnalysis → short string for sensor_readings payload.
    nonisolated private static func sleepStageString(for value: Int) -> String {
        switch HKCategoryValueSleepAnalysis(rawValue: value) {
        case .inBed:           return "IN_BED"
        case .awake:           return "AWAKE"
        case .asleepCore:      return "CORE"
        case .asleepDeep:      return "DEEP"
        case .asleepREM:       return "REM"
        case .asleepUnspecified: return "ASLEEP"
        default:               return "UNKNOWN"
        }
    }

    nonisolated private static func iso(_ date: Date) -> String {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f.string(from: date)
    }
}

private extension Array {
    func chunked(into size: Int) -> [[Element]] {
        guard size > 0 else { return [self] }
        return stride(from: 0, to: count, by: size).map {
            Array(self[$0..<Swift.min($0 + size, count)])
        }
    }
}
