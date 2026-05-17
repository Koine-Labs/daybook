import CoreMotion
import Foundation

/// Collects accelerometer and gyroscope data from CoreMotion at 100 Hz using device motion.
///
/// Uses `startDeviceMotionUpdates()` instead of raw accelerometer to get both acceleration
/// and rotation rate in a single callback. Accelerometer data is box-filtered (averaged)
/// down to 10 Hz for anti-aliasing. Gyroscope data is averaged down to 1 Hz.
///
/// CMMotionManager must be started/stopped from the same thread. This class uses
/// `OperationQueue.main` for callbacks (watchOS requirement) but is itself not an actor
/// because CMMotionManager is not Sendable. Instead, it's accessed only from the
/// WatchSessionCoordinator actor via `@MainActor`-isolated methods.
///
/// **Important:** `CMDeviceMotion.timestamp` is boot-relative, not Unix epoch.
/// We calibrate at start to convert to absolute timestamps.
final class MotionCollector: @unchecked Sendable {
    private let motionManager = CMMotionManager()
    private let sessionStart: Date
    private var bootTimeOffset: TimeInterval = 0
    private let lock = NSLock()
    private var _samples: [AccelerometerSample] = []

    // Box filter accumulators for accelerometer (100 Hz -> 10 Hz)
    private var accelSumX: Float = 0
    private var accelSumY: Float = 0
    private var accelSumZ: Float = 0
    private var accelCount: Int = 0

    // Box filter accumulators for gyroscope (100 Hz -> 1 Hz)
    private var gyroSumX: Float = 0
    private var gyroSumY: Float = 0
    private var gyroSumZ: Float = 0
    private var gyroCount: Int = 0
    private var _gyroSamples: [GyroscopeSample] = []

    init(sessionStart: Date) {
        self.sessionStart = sessionStart
    }

    /// Start collecting device motion data (accelerometer + gyroscope).
    /// Must be called from main thread on watchOS.
    func start() {
        guard motionManager.isDeviceMotionAvailable else { return }

        motionManager.deviceMotionUpdateInterval = SensorConstants.accelerometerUpdateInterval

        // Calibrate boot-time offset on first sample
        var calibrated = false

        motionManager.startDeviceMotionUpdates(to: .main) { [weak self] motion, _ in
            guard let self, let motion else { return }

            if !calibrated {
                self.bootTimeOffset = TimestampUtilities.bootTimeOffset(
                    bootTimestamp: motion.timestamp,
                    wallClock: Date()
                )
                calibrated = true
            }

            let absoluteDate = TimestampUtilities.absoluteDate(
                fromBootTimestamp: motion.timestamp,
                offset: self.bootTimeOffset
            )
            let relativeTimestamp = TimestampUtilities.relativeTimestamp(
                from: absoluteDate,
                sessionStart: self.sessionStart
            )

            // Reconstruct raw acceleration (gravity + user acceleration)
            let ax = Float(motion.gravity.x + motion.userAcceleration.x)
            let ay = Float(motion.gravity.y + motion.userAcceleration.y)
            let az = Float(motion.gravity.z + motion.userAcceleration.z)

            // Box filter for accelerometer: average over decimation window (100 Hz -> 10 Hz)
            self.accelSumX += ax
            self.accelSumY += ay
            self.accelSumZ += az
            self.accelCount += 1

            if self.accelCount >= SensorConstants.accelerometerDecimationFactor {
                let sample = AccelerometerSample(
                    timestamp: relativeTimestamp,
                    x: self.accelSumX / Float(self.accelCount),
                    y: self.accelSumY / Float(self.accelCount),
                    z: self.accelSumZ / Float(self.accelCount)
                )
                self.lock.lock()
                self._samples.append(sample)
                self.lock.unlock()
                self.accelSumX = 0; self.accelSumY = 0; self.accelSumZ = 0; self.accelCount = 0
            }

            // Box filter for gyroscope: average over 100 samples (100 Hz -> 1 Hz)
            self.gyroSumX += Float(motion.rotationRate.x)
            self.gyroSumY += Float(motion.rotationRate.y)
            self.gyroSumZ += Float(motion.rotationRate.z)
            self.gyroCount += 1

            if self.gyroCount >= 100 {
                let gyroSample = GyroscopeSample(
                    timestamp: relativeTimestamp,
                    x: self.gyroSumX / Float(self.gyroCount),
                    y: self.gyroSumY / Float(self.gyroCount),
                    z: self.gyroSumZ / Float(self.gyroCount)
                )
                self.lock.lock()
                self._gyroSamples.append(gyroSample)
                self.lock.unlock()
                self.gyroSumX = 0; self.gyroSumY = 0; self.gyroSumZ = 0; self.gyroCount = 0
            }
        }
    }

    /// Stop collecting device motion data.
    func stop() {
        motionManager.stopDeviceMotionUpdates()
    }

    /// Drain all buffered accelerometer samples for batch assembly. Thread-safe.
    func drainSamples() -> [AccelerometerSample] {
        lock.lock()
        let drained = _samples
        _samples.removeAll(keepingCapacity: true)
        lock.unlock()
        return drained
    }

    /// Drain all buffered gyroscope samples for batch assembly. Thread-safe.
    func drainGyroSamples() -> [GyroscopeSample] {
        lock.lock()
        let drained = _gyroSamples
        _gyroSamples = []
        lock.unlock()
        return drained
    }
}
