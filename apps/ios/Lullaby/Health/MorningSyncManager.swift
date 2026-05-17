import HealthKit
import Foundation

/// Queries Apple's sleep stage labels from HealthKit after the user wakes up.
///
/// These labels serve as ground truth for offline analysis, allowing us to compare
/// our sensor features against Apple's sleep stage classifications.
actor MorningSyncManager {
    private let healthStore = HKHealthStore()

    /// Request HealthKit authorization for sleep analysis data.
    func requestAuthorization() async throws {
        let typesToRead: Set<HKObjectType> = [
            HKCategoryType(.sleepAnalysis),
            HKQuantityType(.heartRate),
            HKQuantityType(.heartRateVariabilitySDNN),
            HKQuantityType(.respiratoryRate),
            HKQuantityType(.oxygenSaturation),
            HKQuantityType(.appleSleepingWristTemperature)
        ]
        try await healthStore.requestAuthorization(toShare: [], read: typesToRead)
    }

    /// Fetch Apple sleep stage labels for the given session time range.
    ///
    /// Returns labels with timestamps relative to `sessionStart`.
    /// Should be called after the user wakes up (data is typically available
    /// 30–60 minutes after waking).
    func fetchSleepStages(
        sessionStart: Date,
        sessionEnd: Date
    ) async throws -> [SleepStageLabel] {
        let sleepType = HKCategoryType(.sleepAnalysis)
        let timePredicate = HKQuery.predicateForSamples(
            withStart: sessionStart,
            end: sessionEnd,
            options: .strictStartDate
        )

        let descriptor = HKSampleQueryDescriptor(
            predicates: [.categorySample(type: sleepType, predicate: timePredicate)],
            sortDescriptors: [SortDescriptor(\.startDate, order: .forward)]
        )

        let samples = try await descriptor.result(for: healthStore)

        // Filter to Apple Watch-sourced samples (not third-party apps)
        let watchSamples = samples.filter { sample in
            sample.sourceRevision.productType?.contains("Watch") ?? false
        }

        // Use all samples if no watch-specific ones found (fallback)
        let relevantSamples = watchSamples.isEmpty ? samples : watchSamples

        return relevantSamples.map { sample in
            SleepStageLabel(
                startTimestamp: TimestampUtilities.relativeTimestamp(
                    from: sample.startDate, sessionStart: sessionStart
                ),
                endTimestamp: TimestampUtilities.relativeTimestamp(
                    from: sample.endDate, sessionStart: sessionStart
                ),
                stage: SleepStage(from: sample.value)
            )
        }
    }

    // MARK: - Quantity Sample Queries

    func fetchRespiratoryRate(sessionStart: Date, sessionEnd: Date) async throws -> [TimestampedSample] {
        try await fetchQuantitySamples(.respiratoryRate, unit: HKUnit(from: "count/min"), sessionStart: sessionStart, sessionEnd: sessionEnd)
    }

    func fetchSpO2(sessionStart: Date, sessionEnd: Date) async throws -> [TimestampedSample] {
        try await fetchQuantitySamples(.oxygenSaturation, unit: HKUnit.percent(), sessionStart: sessionStart, sessionEnd: sessionEnd)
    }

    func fetchWristTemperature(sessionStart: Date, sessionEnd: Date) async throws -> [TimestampedSample] {
        try await fetchQuantitySamples(.appleSleepingWristTemperature, unit: HKUnit.degreeCelsius(), sessionStart: sessionStart, sessionEnd: sessionEnd)
    }

    // MARK: - Private Helpers

    private func fetchQuantitySamples(
        _ typeIdentifier: HKQuantityTypeIdentifier,
        unit: HKUnit,
        sessionStart: Date,
        sessionEnd: Date
    ) async throws -> [TimestampedSample] {
        let quantityType = HKQuantityType(typeIdentifier)
        let predicate = HKQuery.predicateForSamples(
            withStart: sessionStart,
            end: sessionEnd,
            options: .strictStartDate
        )

        let descriptor = HKSampleQueryDescriptor(
            predicates: [.quantitySample(type: quantityType, predicate: predicate)],
            sortDescriptors: [SortDescriptor(\.startDate)]
        )

        let samples: [HKQuantitySample]
        do {
            samples = try await descriptor.result(for: healthStore)
        } catch {
            // Type may not be available on older hardware — return empty
            return []
        }

        // Filter to Apple Watch sources
        let watchSamples = samples.filter { $0.sourceRevision.productType?.contains("Watch") ?? false }
        let relevantSamples = watchSamples.isEmpty ? samples : watchSamples

        return relevantSamples.map { sample in
            TimestampedSample(
                timestamp: TimestampUtilities.relativeTimestamp(
                    from: sample.startDate,
                    sessionStart: sessionStart
                ),
                value: sample.quantity.doubleValue(for: unit)
            )
        }
    }
}
