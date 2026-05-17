import Foundation

/// A batch of sensor data collected on the Apple Watch and sent to the iPhone.
/// Assembled every `SensorConstants.batchInterval` seconds during a sleep session.
nonisolated struct SensorPacket: Codable, Sendable, Equatable {
    /// Unique identifier for the sleep session this packet belongs to.
    let sessionID: UUID
    /// Sequential index of this packet within the session (0, 1, 2, …).
    let batchIndex: UInt32
    /// Wall-clock time when this packet was assembled.
    let capturedAt: Date

    var heartRateSamples: [HeartRateSample]
    var hrvSamples: [HRVSample]
    var accelerometerSamples: [AccelerometerSample]
    var gyroscopeSamples: [GyroscopeSample] = []
}

// MARK: - Individual Sample Types

/// A single heart rate reading from Apple Watch via HealthKit.
nonisolated struct HeartRateSample: Codable, Sendable, Equatable {
    /// Seconds since session start.
    let timestamp: TimeInterval
    /// Beats per minute.
    let bpm: Double
}

/// A single heart rate variability (SDNN) reading from HealthKit.
nonisolated struct HRVSample: Codable, Sendable, Equatable {
    /// Seconds since session start.
    let timestamp: TimeInterval
    /// Standard deviation of NN intervals, in milliseconds.
    let sdnn: Double
}

/// A single accelerometer reading from CoreMotion, after decimation.
nonisolated struct AccelerometerSample: Codable, Sendable, Equatable {
    /// Seconds since session start.
    let timestamp: TimeInterval
    /// Acceleration along X axis in G.
    let x: Float
    /// Acceleration along Y axis in G.
    let y: Float
    /// Acceleration along Z axis in G.
    let z: Float
}

/// A single gyroscope reading from CoreMotion, after decimation.
nonisolated struct GyroscopeSample: Codable, Sendable, Equatable {
    /// Seconds since session start.
    let timestamp: TimeInterval
    /// Rotation rate around X axis in radians/second.
    let x: Float
    /// Rotation rate around Y axis in radians/second.
    let y: Float
    /// Rotation rate around Z axis in radians/second.
    let z: Float
}
