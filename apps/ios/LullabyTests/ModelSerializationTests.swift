import XCTest
@testable import Lullaby

/// Tests Codable roundtrip for all model types to ensure the JSON data contract
/// between the Swift iOS/watchOS app and the Python analysis pipeline is correct.
final class ModelSerializationTests: XCTestCase {

    private let encoder: JSONEncoder = {
        let e = JSONEncoder()
        e.dateEncodingStrategy = .iso8601
        e.outputFormatting = [.sortedKeys]
        return e
    }()

    private let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.dateDecodingStrategy = .iso8601
        return d
    }()

    // MARK: - HeartRateSample

    func testHeartRateSampleRoundtrip() throws {
        let sample = TestFactory.makeHeartRateSample(timestamp: 123.456, bpm: 72.5)
        let data = try encoder.encode(sample)
        let decoded = try decoder.decode(HeartRateSample.self, from: data)
        XCTAssertEqual(sample, decoded)
    }

    // MARK: - HRVSample

    func testHRVSampleRoundtrip() throws {
        let sample = TestFactory.makeHRVSample(timestamp: 300, sdnn: 45.2)
        let data = try encoder.encode(sample)
        let decoded = try decoder.decode(HRVSample.self, from: data)
        XCTAssertEqual(sample, decoded)
    }

    // MARK: - AccelerometerSample

    func testAccelerometerSampleRoundtrip() throws {
        let sample = TestFactory.makeAccelerometerSample(timestamp: 60, x: 0.01, y: -0.02, z: -0.98)
        let data = try encoder.encode(sample)
        let decoded = try decoder.decode(AccelerometerSample.self, from: data)
        XCTAssertEqual(sample, decoded)
    }

    // MARK: - SensorPacket

    func testSensorPacketFullRoundtrip() throws {
        let packet = TestFactory.makeSensorPacket(
            batchIndex: 7,
            heartRateSamples: [TestFactory.makeHeartRateSample(timestamp: 0, bpm: 65)],
            hrvSamples: [TestFactory.makeHRVSample(timestamp: 0, sdnn: 50)],
            accelerometerSamples: [TestFactory.makeAccelerometerSample()]
        )
        let data = try encoder.encode(packet)
        let decoded = try decoder.decode(SensorPacket.self, from: data)
        XCTAssertEqual(packet, decoded)
    }

    func testSensorPacketEmptyArraysRoundtrip() throws {
        let packet = TestFactory.makeSensorPacket()
        let data = try encoder.encode(packet)
        let decoded = try decoder.decode(SensorPacket.self, from: data)
        XCTAssertEqual(packet, decoded)
        XCTAssertTrue(decoded.heartRateSamples.isEmpty)
        XCTAssertTrue(decoded.hrvSamples.isEmpty)
        XCTAssertTrue(decoded.accelerometerSamples.isEmpty)
    }

    // MARK: - SonarFeatureSample

    func testSonarFeatureSampleRoundtrip() throws {
        let sample = TestFactory.makeSonarFeatureSample(
            timestamp: 120, breathingRate: 16.5, breathingRegularity: 0.92, signalStrength: -15
        )
        let data = try encoder.encode(sample)
        let decoded = try decoder.decode(SonarFeatureSample.self, from: data)
        XCTAssertEqual(sample, decoded)
    }

    func testSonarFeatureSampleNilBreathingRoundtrip() throws {
        let sample = TestFactory.makeSonarFeatureSample(
            breathingRate: nil, breathingRegularity: nil, signalStrength: -45
        )
        let data = try encoder.encode(sample)
        let decoded = try decoder.decode(SonarFeatureSample.self, from: data)
        XCTAssertEqual(sample, decoded)
        XCTAssertNil(decoded.breathingRate)
        XCTAssertNil(decoded.breathingRegularity)
    }

    // MARK: - AudioFeatureSample

    func testAudioFeatureSampleRoundtrip() throws {
        let sample = TestFactory.makeAudioFeatureSample(classification: .snoring)
        let data = try encoder.encode(sample)
        let decoded = try decoder.decode(AudioFeatureSample.self, from: data)
        XCTAssertEqual(sample, decoded)
    }

    // MARK: - AudioEventClass

    func testAudioEventClassAllCasesRoundtrip() throws {
        for eventClass in [AudioEventClass.silence, .breathing, .snoring, .movement, .ambientNoise] {
            let data = try encoder.encode(eventClass)
            let decoded = try decoder.decode(AudioEventClass.self, from: data)
            XCTAssertEqual(eventClass, decoded, "Failed roundtrip for \(eventClass)")
        }
    }

    // MARK: - SleepStageLabel

    func testSleepStageLabelRoundtrip() throws {
        let label = TestFactory.makeSleepStageLabel(
            startTimestamp: 3600, endTimestamp: 7200, stage: .remSleep
        )
        let data = try encoder.encode(label)
        let decoded = try decoder.decode(SleepStageLabel.self, from: data)
        XCTAssertEqual(label, decoded)
    }

    // MARK: - SessionMetadata

    func testSessionMetadataFullRoundtrip() throws {
        let meta = TestFactory.makeSessionMetadata()
        let data = try encoder.encode(meta)
        let decoded = try decoder.decode(SessionMetadata.self, from: data)
        XCTAssertEqual(meta, decoded)
    }

    func testSessionMetadataAllNilsRoundtrip() throws {
        let meta = TestFactory.makeSessionMetadata(
            watchModel: nil,
            osVersionWatch: nil,
            watchBatteryAtStart: nil,
            watchBatteryAtEnd: nil,
            phoneBatteryAtStart: nil,
            phoneBatteryAtEnd: nil,
            totalPacketsExpected: nil
        )
        let data = try encoder.encode(meta)
        let decoded = try decoder.decode(SessionMetadata.self, from: data)
        XCTAssertEqual(meta, decoded)
        XCTAssertNil(decoded.watchModel)
        XCTAssertNil(decoded.watchBatteryAtStart)
    }

    // MARK: - SleepSession

    func testSleepSessionFullRoundtrip() throws {
        let session = TestFactory.makePopulatedSession()
        let data = try encoder.encode(session)
        let decoded = try decoder.decode(SleepSession.self, from: data)

        XCTAssertEqual(session.id, decoded.id)
        XCTAssertEqual(session.watchPackets.count, decoded.watchPackets.count)
        XCTAssertEqual(session.sonarFeatures.count, decoded.sonarFeatures.count)
        XCTAssertEqual(session.audioFeatures.count, decoded.audioFeatures.count)
        XCTAssertEqual(session.sleepStages.count, decoded.sleepStages.count)
    }

    func testSleepSessionEmptyCollectionsRoundtrip() throws {
        let session = TestFactory.makeSleepSession()
        let data = try encoder.encode(session)
        let decoded = try decoder.decode(SleepSession.self, from: data)

        XCTAssertEqual(session.id, decoded.id)
        XCTAssertTrue(decoded.watchPackets.isEmpty)
        XCTAssertTrue(decoded.sonarFeatures.isEmpty)
        XCTAssertTrue(decoded.audioFeatures.isEmpty)
        XCTAssertTrue(decoded.sleepStages.isEmpty)
    }

    // MARK: - JSON Format Verification

    func testJSONUsesISO8601Dates() throws {
        let session = TestFactory.makeSleepSession()
        let data = try encoder.encode(session)
        let jsonString = String(data: data, encoding: .utf8)!
        // ISO8601 dates contain "T" and "Z" or timezone offset
        XCTAssertTrue(jsonString.contains("T"), "Date should be ISO8601 formatted")
    }

    func testJSONUsesSortedKeys() throws {
        let sample = TestFactory.makeHeartRateSample(timestamp: 10, bpm: 70)
        let data = try encoder.encode(sample)
        let jsonString = String(data: data, encoding: .utf8)!
        // With sorted keys, "bpm" should come before "timestamp"
        let bpmRange = jsonString.range(of: "bpm")!
        let tsRange = jsonString.range(of: "timestamp")!
        XCTAssertTrue(bpmRange.lowerBound < tsRange.lowerBound, "Keys should be sorted")
    }
}
