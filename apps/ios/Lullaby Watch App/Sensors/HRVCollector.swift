import HealthKit
import Foundation

/// Continuously collects heart rate variability (SDNN) samples from HealthKit.
///
/// HRV samples arrive much less frequently than HR (~every 5 minutes),
/// but are valuable for sleep stage discrimination.
actor HRVCollector {
    private let healthStore = HKHealthStore()
    private let sessionStart: Date
    private var query: HKAnchoredObjectQuery?
    private var samples: [HRVSample] = []
    private var anchor: HKQueryAnchor?

    init(sessionStart: Date) {
        self.sessionStart = sessionStart
    }

    /// Begin streaming HRV data.
    func start() {
        let hrvType = HKQuantityType(.heartRateVariabilitySDNN)
        let predicate = HKQuery.predicateForSamples(
            withStart: sessionStart,
            end: nil,
            options: .strictStartDate
        )

        let query = HKAnchoredObjectQuery(
            type: hrvType,
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

    /// Stop collecting HRV data.
    func stop() {
        if let query {
            healthStore.stop(query)
        }
        self.query = nil
    }

    /// Drain all buffered samples for batch assembly.
    func drainSamples() -> [HRVSample] {
        let drained = samples
        samples.removeAll(keepingCapacity: true)
        return drained
    }

    // MARK: - Private

    private func process(samples newSamples: [HKQuantitySample], anchor newAnchor: HKQueryAnchor?) {
        if let newAnchor { self.anchor = newAnchor }

        let msUnit = HKUnit.secondUnit(with: .milli)
        for sample in newSamples {
            let sdnn = sample.quantity.doubleValue(for: msUnit)
            let ts = TimestampUtilities.relativeTimestamp(from: sample.startDate, sessionStart: sessionStart)
            samples.append(HRVSample(timestamp: ts, sdnn: sdnn))
        }
    }
}
