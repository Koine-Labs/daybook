import XCTest
@testable import Lullaby

/// Tests for JSONExporter — file export and summary generation.
/// JSONExporter is an actor, so all calls must be awaited.
final class JSONExporterTests: XCTestCase {

    private var exporter: JSONExporter!

    override func setUp() {
        super.setUp()
        exporter = JSONExporter()
    }

    override func tearDown() {
        exporter = nil
        super.tearDown()
    }

    // MARK: - export()

    func testExportCreatesFile() async throws {
        let session = TestFactory.makePopulatedSession()
        let url = try await exporter.export(session)
        XCTAssertTrue(FileManager.default.fileExists(atPath: url.path))
        // Clean up
        try? FileManager.default.removeItem(at: url)
    }

    func testExportFileContainsValidJSON() async throws {
        let session = TestFactory.makePopulatedSession()
        let url = try await exporter.export(session)
        let data = try Data(contentsOf: url)
        let json = try JSONSerialization.jsonObject(with: data)
        XCTAssertTrue(json is [String: Any], "Exported JSON should be a dictionary")
        // Clean up
        try? FileManager.default.removeItem(at: url)
    }

    func testExportFilenameFormat() async throws {
        let session = TestFactory.makePopulatedSession()
        let url = try await exporter.export(session)
        let filename = url.lastPathComponent

        XCTAssertTrue(filename.hasPrefix("lullaby_session_"), "Filename should start with 'lullaby_session_'")
        XCTAssertTrue(filename.hasSuffix(".json"), "Filename should end with '.json'")
        // Clean up
        try? FileManager.default.removeItem(at: url)
    }

    func testExportDecodeRoundtrip() async throws {
        let session = TestFactory.makePopulatedSession()
        let url = try await exporter.export(session)
        let data = try Data(contentsOf: url)

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let decoded = try decoder.decode(SleepSession.self, from: data)

        XCTAssertEqual(decoded.id, session.id)
        XCTAssertEqual(decoded.watchPackets.count, session.watchPackets.count)
        XCTAssertEqual(decoded.sonarFeatures.count, session.sonarFeatures.count)
        XCTAssertEqual(decoded.audioFeatures.count, session.audioFeatures.count)
        XCTAssertEqual(decoded.sleepStages.count, session.sleepStages.count)
        // Clean up
        try? FileManager.default.removeItem(at: url)
    }

    func testExportEmptySession() async throws {
        let session = TestFactory.makeSleepSession()
        let url = try await exporter.export(session)
        XCTAssertTrue(FileManager.default.fileExists(atPath: url.path))
        // Clean up
        try? FileManager.default.removeItem(at: url)
    }

    // MARK: - summary()

    func testSummaryContainsSessionID() async {
        let session = TestFactory.makePopulatedSession()
        let text = await exporter.summary(session)
        // Summary includes first 8 chars of UUID
        let prefix = String(session.id.uuidString.prefix(8))
        XCTAssertTrue(text.contains(prefix), "Summary should contain session ID prefix")
    }

    func testSummaryContainsDuration() async {
        let session = TestFactory.makePopulatedSession()
        let text = await exporter.summary(session)
        // 8-hour session → should contain "8h"
        XCTAssertTrue(text.contains("8h"), "Summary should contain duration")
    }

    func testSummaryContainsSampleCounts() async {
        let session = TestFactory.makePopulatedSession()
        let text = await exporter.summary(session)
        XCTAssertTrue(text.contains("Watch packets: 5"), "Summary should contain watch packet count")
        XCTAssertTrue(text.contains("Sonar features: 2"), "Summary should contain sonar feature count")
        XCTAssertTrue(text.contains("Audio features: 2"), "Summary should contain audio feature count")
        XCTAssertTrue(text.contains("Sleep stages: 3"), "Summary should contain sleep stage count")
    }
}
