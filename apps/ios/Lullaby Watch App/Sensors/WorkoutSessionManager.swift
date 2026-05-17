import HealthKit
import Foundation

/// Manages the HKWorkoutSession lifecycle for sleep tracking on Apple Watch.
///
/// An active workout session is required to keep the watch app running in the background
/// and to enable continuous heart rate monitoring. Uses `.sleep` activity type.
actor WorkoutSessionManager {
    private let healthStore = HKHealthStore()
    private var workoutSession: HKWorkoutSession?
    private var workoutBuilder: HKLiveWorkoutBuilder?

    /// Request HealthKit authorization for the data types we need.
    func requestAuthorization() async throws {
        let typesToRead: Set<HKObjectType> = [
            HKQuantityType(.heartRate),
            HKQuantityType(.heartRateVariabilitySDNN),
            HKCategoryType(.sleepAnalysis)
        ]
        let typesToWrite: Set<HKSampleType> = [
            HKQuantityType.workoutType()
        ]
        try await healthStore.requestAuthorization(toShare: typesToWrite, read: typesToRead)
    }

    /// Start a workout session configured for sleep tracking.
    func startSession() async throws {
        let configuration = HKWorkoutConfiguration()
        configuration.activityType = .other
        configuration.locationType = .indoor

        let session = try HKWorkoutSession(healthStore: healthStore, configuration: configuration)
        let builder = session.associatedWorkoutBuilder()
        builder.dataSource = HKLiveWorkoutDataSource(healthStore: healthStore, workoutConfiguration: configuration)

        self.workoutSession = session
        self.workoutBuilder = builder

        session.startActivity(with: Date())
        try await builder.beginCollection(at: Date())
    }

    /// Stop the workout session and finalize the workout.
    func stopSession() async throws {
        guard let session = workoutSession, let builder = workoutBuilder else { return }

        session.end()
        try await builder.endCollection(at: Date())
        try await builder.finishWorkout()

        self.workoutSession = nil
        self.workoutBuilder = nil
    }

    /// Whether a workout session is currently active.
    var isActive: Bool {
        workoutSession?.state == .running
    }
}
