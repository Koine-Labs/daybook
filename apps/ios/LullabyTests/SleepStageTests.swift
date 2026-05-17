import XCTest
import HealthKit
@testable import Lullaby

/// Tests for the SleepStage enum — raw value mapping and HealthKit conversion.
final class SleepStageTests: XCTestCase {

    // MARK: - Raw Values

    func testRawValueAwake() {
        XCTAssertEqual(SleepStage.awake.rawValue, "awake")
    }

    func testRawValueRemSleep() {
        XCTAssertEqual(SleepStage.remSleep.rawValue, "remSleep")
    }

    func testRawValueCoreLight() {
        XCTAssertEqual(SleepStage.coreLight.rawValue, "coreLight")
    }

    func testRawValueDeepSleep() {
        XCTAssertEqual(SleepStage.deepSleep.rawValue, "deepSleep")
    }

    func testRawValueInBed() {
        XCTAssertEqual(SleepStage.inBed.rawValue, "inBed")
    }

    func testRawValueUnknown() {
        XCTAssertEqual(SleepStage.unknown.rawValue, "unknown")
    }

    // MARK: - Codable Roundtrip

    func testCodableRoundtripAllCases() throws {
        let encoder = JSONEncoder()
        let decoder = JSONDecoder()

        let allCases: [SleepStage] = [.awake, .remSleep, .coreLight, .deepSleep, .inBed, .unknown]
        for stage in allCases {
            let data = try encoder.encode(stage)
            let decoded = try decoder.decode(SleepStage.self, from: data)
            XCTAssertEqual(stage, decoded, "Codable roundtrip failed for \(stage)")
        }
    }

    // MARK: - HealthKit Mapping

    func testInitFromHKAwake() {
        let stage = SleepStage(from: HKCategoryValueSleepAnalysis.awake.rawValue)
        XCTAssertEqual(stage, .awake)
    }

    func testInitFromHKREM() {
        let stage = SleepStage(from: HKCategoryValueSleepAnalysis.asleepREM.rawValue)
        XCTAssertEqual(stage, .remSleep)
    }

    func testInitFromHKCore() {
        let stage = SleepStage(from: HKCategoryValueSleepAnalysis.asleepCore.rawValue)
        XCTAssertEqual(stage, .coreLight)
    }

    func testInitFromHKDeep() {
        let stage = SleepStage(from: HKCategoryValueSleepAnalysis.asleepDeep.rawValue)
        XCTAssertEqual(stage, .deepSleep)
    }

    func testInitFromHKInBed() {
        let stage = SleepStage(from: HKCategoryValueSleepAnalysis.inBed.rawValue)
        XCTAssertEqual(stage, .inBed)
    }

    func testInitFromHKUnknownValue() {
        let stage = SleepStage(from: 999)
        XCTAssertEqual(stage, .unknown)
    }
}
