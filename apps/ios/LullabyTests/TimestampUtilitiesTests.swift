import XCTest
@testable import Lullaby

/// Tests for TimestampUtilities — date arithmetic and precision.
final class TimestampUtilitiesTests: XCTestCase {

    // MARK: - relativeTimestamp

    func testRelativeTimestampAtZero() {
        let start = Date(timeIntervalSinceReferenceDate: 700_000_000)
        let ts = TimestampUtilities.relativeTimestamp(from: start, sessionStart: start)
        XCTAssertEqual(ts, 0, accuracy: 0.0001)
    }

    func testRelativeTimestampPositive() {
        let start = Date(timeIntervalSinceReferenceDate: 700_000_000)
        let later = start.addingTimeInterval(60)
        let ts = TimestampUtilities.relativeTimestamp(from: later, sessionStart: start)
        XCTAssertEqual(ts, 60, accuracy: 0.0001)
    }

    func testRelativeTimestampNegative() {
        let start = Date(timeIntervalSinceReferenceDate: 700_000_000)
        let earlier = start.addingTimeInterval(-30)
        let ts = TimestampUtilities.relativeTimestamp(from: earlier, sessionStart: start)
        XCTAssertEqual(ts, -30, accuracy: 0.0001)
    }

    // MARK: - absoluteDate

    func testAbsoluteDateRoundtrip() {
        let start = Date(timeIntervalSinceReferenceDate: 700_000_000)
        let originalDate = start.addingTimeInterval(3600)
        let relative = TimestampUtilities.relativeTimestamp(from: originalDate, sessionStart: start)
        let reconstructed = TimestampUtilities.absoluteDate(from: relative, sessionStart: start)
        XCTAssertEqual(
            originalDate.timeIntervalSinceReferenceDate,
            reconstructed.timeIntervalSinceReferenceDate,
            accuracy: 0.0001
        )
    }

    func testAbsoluteDateZeroOffset() {
        let start = Date(timeIntervalSinceReferenceDate: 700_000_000)
        let result = TimestampUtilities.absoluteDate(from: 0, sessionStart: start)
        XCTAssertEqual(
            start.timeIntervalSinceReferenceDate,
            result.timeIntervalSinceReferenceDate,
            accuracy: 0.0001
        )
    }

    func testAbsoluteDateLargeOffset() {
        let start = Date(timeIntervalSinceReferenceDate: 700_000_000)
        let eightHours: TimeInterval = 8 * 3600
        let result = TimestampUtilities.absoluteDate(from: eightHours, sessionStart: start)
        XCTAssertEqual(
            result.timeIntervalSinceReferenceDate,
            start.timeIntervalSinceReferenceDate + eightHours,
            accuracy: 0.0001
        )
    }

    // MARK: - bootTimeOffset

    func testBootTimeOffsetCalculation() {
        let bootTimestamp: TimeInterval = 12345.678
        let wallClock = Date(timeIntervalSinceReferenceDate: 700_000_000)
        let offset = TimestampUtilities.bootTimeOffset(bootTimestamp: bootTimestamp, wallClock: wallClock)

        // offset = wallClock.timeIntervalSinceReferenceDate - bootTimestamp
        let expected = 700_000_000 - 12345.678
        XCTAssertEqual(offset, expected, accuracy: 0.0001)
    }

    // MARK: - absoluteDate(fromBootTimestamp:offset:)

    func testAbsoluteDateFromBootTimestamp() {
        let bootTimestamp: TimeInterval = 12345.678
        let wallClock = Date(timeIntervalSinceReferenceDate: 700_000_000)
        let offset = TimestampUtilities.bootTimeOffset(bootTimestamp: bootTimestamp, wallClock: wallClock)

        let result = TimestampUtilities.absoluteDate(fromBootTimestamp: bootTimestamp, offset: offset)
        XCTAssertEqual(
            result.timeIntervalSinceReferenceDate,
            wallClock.timeIntervalSinceReferenceDate,
            accuracy: 0.0001
        )
    }

    // MARK: - Precision

    func testSubMillisecondPrecision() {
        let start = Date(timeIntervalSinceReferenceDate: 700_000_000)
        let preciseOffset: TimeInterval = 123.456789
        let date = TimestampUtilities.absoluteDate(from: preciseOffset, sessionStart: start)
        let backToRelative = TimestampUtilities.relativeTimestamp(from: date, sessionStart: start)
        // Should preserve sub-millisecond precision (microsecond-level given Double arithmetic on large dates)
        XCTAssertEqual(backToRelative, preciseOffset, accuracy: 1e-6)
    }
}
