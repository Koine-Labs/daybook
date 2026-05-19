import Foundation
import HealthKit
import Observation

// HealthKit live heart rate. Drives the HR readout on the watch face and lets
// us infer Regis's mood from HRV later.
//
// Permissions: NSHealthShareUsageDescription must be in Info.plist + the
// HealthKit entitlement enabled in Signing & Capabilities for the watch target.
// On the simulator with no Health data, this just stays at nil and the UI
// shows "—".

@MainActor
@Observable
final class HeartRateClient {
    static let shared = HeartRateClient()

    private let store = HKHealthStore()
    private var query: HKAnchoredObjectQuery?

    /// Latest heart-rate reading in BPM. nil means "not authorized or no data yet".
    private(set) var bpm: Int? = nil

    /// Whether HealthKit is available on this device.
    var isAvailable: Bool { HKHealthStore.isHealthDataAvailable() }

    private init() {}

    func start() {
        guard isAvailable else { return }
        guard let type = HKQuantityType.quantityType(forIdentifier: .heartRate) else { return }

        store.requestAuthorization(toShare: [], read: [type]) { [weak self] granted, _ in
            guard let self, granted else { return }
            Task { @MainActor in
                self.runLatestSampleQuery(type: type)
                self.startStreamingQuery(type: type)
            }
        }
    }

    // Fetch the most recent reading (covers re-open after a while).
    private func runLatestSampleQuery(type: HKQuantityType) {
        let sort = NSSortDescriptor(key: HKSampleSortIdentifierEndDate, ascending: false)
        let q = HKSampleQuery(
            sampleType: type, predicate: nil, limit: 1, sortDescriptors: [sort]
        ) { [weak self] _, samples, _ in
            guard let sample = samples?.first as? HKQuantitySample else { return }
            let unit = HKUnit.count().unitDivided(by: .minute())
            let value = sample.quantity.doubleValue(for: unit)
            Task { @MainActor in self?.bpm = Int(value.rounded()) }
        }
        store.execute(q)
    }

    // Long-running query that fires whenever a new sample lands.
    private func startStreamingQuery(type: HKQuantityType) {
        let q = HKAnchoredObjectQuery(
            type: type, predicate: nil, anchor: nil, limit: HKObjectQueryNoLimit
        ) { [weak self] _, samples, _, _, _ in
            self?.consume(samples: samples)
        }
        q.updateHandler = { [weak self] _, samples, _, _, _ in
            self?.consume(samples: samples)
        }
        store.execute(q)
        self.query = q
    }

    nonisolated private func consume(samples: [HKSample]?) {
        guard let latest = samples?.compactMap({ $0 as? HKQuantitySample }).last else { return }
        let unit = HKUnit.count().unitDivided(by: .minute())
        let value = latest.quantity.doubleValue(for: unit)
        Task { @MainActor in self.bpm = Int(value.rounded()) }
    }
}
