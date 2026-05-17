import Foundation

/// All sensor configuration constants for the Lullaby data collection pipeline.
/// Centralized here so both iOS and watchOS targets share identical values.
nonisolated enum SensorConstants {

    // MARK: - Accelerometer (watchOS)

    /// Native CMMotionManager update interval in Hz.
    static let accelerometerNativeHz: Double = 100
    /// CMMotionManager update interval in seconds.
    static let accelerometerUpdateInterval: TimeInterval = 1.0 / accelerometerNativeHz
    /// Decimation factor applied before batching (100 Hz → 10 Hz).
    static let accelerometerDecimationFactor: Int = 10
    /// Effective output rate after decimation.
    static let accelerometerOutputHz: Double = accelerometerNativeHz / Double(accelerometerDecimationFactor)

    // MARK: - Heart Rate (watchOS)

    /// Minimum expected HR sample interval from HKAnchoredObjectQuery during workout.
    /// Apple Watch typically delivers HR every ~5 seconds during an active workout session.
    static let expectedHRIntervalSeconds: TimeInterval = 5

    // MARK: - HRV (watchOS)

    /// HRV (SDNN) samples arrive much less frequently — roughly every 5 minutes.
    static let expectedHRVIntervalSeconds: TimeInterval = 300

    // MARK: - Batch & Transfer (watchOS → iOS)

    /// Seconds between sensor packet assembly on the watch.
    static let batchInterval: TimeInterval = 30
    /// Maximum packets to buffer on watch before oldest is dropped.
    static let watchBufferMaxPackets: Int = 1000

    // MARK: - Sonar (iOS)

    /// Ultrasonic tone frequency in Hz. Above most adults' hearing threshold.
    static let sonarFrequencyHz: Float = 19_000
    /// Sample rate for AVAudioEngine (standard high-quality rate).
    static let sonarSampleRate: Double = 48_000
    /// Amplitude of the sonar tone (0.0–1.0). Low to minimize audibility.
    static let sonarAmplitude: Float = 0.3
    /// FFT size for sonar analysis. 4096 at 48 kHz → ~11.7 Hz bin resolution.
    static let sonarFFTSize: Int = 4096
    /// Number of recent amplitude samples to keep for autocorrelation-based breathing detection.
    static let sonarAmplitudeHistorySize: Int = 256
    /// Interval between sonar feature extraction (seconds).
    static let sonarFeatureInterval: TimeInterval = 2.0

    // MARK: - Audio Analysis (iOS)

    /// FFT size for passive audio spectral analysis.
    static let audioFFTSize: Int = 2048
    /// Interval between audio feature extraction (seconds).
    static let audioFeatureInterval: TimeInterval = 5.0

    // MARK: - Breathing Rate Bounds

    /// Normal adult breathing rate range (breaths per minute).
    static let breathingRateMinBPM: Float = 8
    static let breathingRateMaxBPM: Float = 30

    // MARK: - Persistence

    /// Persist the active session to disk every N watch packets received.
    static let persistenceInterval: Int = 10

    // MARK: - App Groups

    /// Shared App Group identifier for iOS ↔ watchOS data sharing.
    static let appGroupIdentifier = "group.Neovasky.Lullaby"
}
