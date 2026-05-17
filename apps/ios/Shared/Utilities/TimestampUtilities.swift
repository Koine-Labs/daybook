import Foundation

/// Helpers for converting between absolute `Date` values and session-relative `TimeInterval`.
///
/// All sensor samples store timestamps as seconds relative to the session start date.
/// This avoids floating-point precision loss that occurs when encoding large `Date.timeIntervalSinceReferenceDate`
/// values to JSON, and makes data alignment trivial (all streams share the same zero point).
nonisolated enum TimestampUtilities {

    /// Convert an absolute date to a session-relative timestamp.
    static func relativeTimestamp(from date: Date, sessionStart: Date) -> TimeInterval {
        date.timeIntervalSince(sessionStart)
    }

    /// Convert a session-relative timestamp back to an absolute date.
    static func absoluteDate(from relativeTimestamp: TimeInterval, sessionStart: Date) -> Date {
        sessionStart.addingTimeInterval(relativeTimestamp)
    }

    /// Calibrate CMAccelerometerData boot-relative timestamps to absolute dates.
    ///
    /// CoreMotion's `CMAccelerometerData.timestamp` is relative to system boot, not Unix epoch.
    /// Call this once at session start to compute the offset, then apply it to every sample.
    ///
    /// - Parameters:
    ///   - bootTimestamp: A `CMAccelerometerData.timestamp` captured at calibration time.
    ///   - wallClock: The `Date()` captured at the same instant as `bootTimestamp`.
    /// - Returns: Offset to add to any boot-relative timestamp to get `Date.timeIntervalSinceReferenceDate`.
    static func bootTimeOffset(bootTimestamp: TimeInterval, wallClock: Date) -> TimeInterval {
        wallClock.timeIntervalSinceReferenceDate - bootTimestamp
    }

    /// Convert a boot-relative CoreMotion timestamp to an absolute Date.
    static func absoluteDate(fromBootTimestamp bootTimestamp: TimeInterval, offset: TimeInterval) -> Date {
        Date(timeIntervalSinceReferenceDate: bootTimestamp + offset)
    }
}
