import HealthKit
import Foundation

/// Continuously collects heart rate samples from HealthKit during an active workout session.
///
/// Uses `HKAnchoredObjectQuery` with an `updateHandler` for real-time HR delivery.
/// Samples are buffered internally and drained by the coordinator for batching.
actor HeartRateCollector {
    private let healthStore = HKHealthStore()
    private let sessionStart: Date
    private var query: HKAnchoredObjectQuery?
    private var samples: [HeartRateSample] = []
    private var anchor: HKQueryAnchor?

    init(sessionStart: Date) {
        self.sessionStart = sessionStart
    }

    /// Begin streaming heart rate data.
    func start() {
        let hrType = HKQuantityType(.heartRate)
        let predicate = HKQuery.predicateForSamples(
            withStart: sessionStart,
            end: nil,
            options: .strictStartDate
        )

        let query = HKAnchoredObjectQuery(
            type: hrType,
            predicate: predicate,
            anchor: anchor,
            limit: HKObjectQueryNoLimit
        ) { [weak self] _, newSamples, _, newAnchor, _ in
            guard let self, let newSamples = newSamples as? [HKQuantitySample] else { return }
            Task {
                await self.process(samples: newSamples, anchor: newAnchor)
            }
        }

        query.updateHandler = { [weak self] _, newSamples, _, newAnchor, _ in
            guard let self, let newSamples = newSamples as? [HKQuantitySample] else { return }
            Task {
                await self.process(samples: newSamples, anchor: newAnchor)
            }
        }

        self.query = query
        healthStore.execute(query)
    }

    /// Stop collecting heart rate data.
    func stop() {
        if let query {
            healthStore.stop(query)
        }
        self.query = nil
    }

    /// Drain all buffered samples (called by coordinator for batch assembly).
    func drainSamples() -> [HeartRateSample] {
        let drained = samples
        samples.removeAll(keepingCapacity: true)
        return drained
    }

    /// The number of buffered samples waiting to be drained.
    var bufferedCount: Int { samples.count }

    // MARK: - Private

    private func process(samples newSamples: [HKQuantitySample], anchor newAnchor: HKQueryAnchor?) {
        if let newAnchor { self.anchor = newAnchor }

        let bpmUnit = HKUnit.count().unitDivided(by: .minute())
        for sample in newSamples {
            let bpm = sample.quantity.doubleValue(for: bpmUnit)
            let ts = TimestampUtilities.relativeTimestamp(from: sample.startDate, sessionStart: sessionStart)
            samples.append(HeartRateSample(timestamp: ts, bpm: bpm))
        }
    }
}
