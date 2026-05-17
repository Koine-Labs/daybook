import XCTest
@testable import Lullaby

/// Tests for PassiveAudioAnalyzer.classify() — verifies exact threshold boundaries.
/// PassiveAudioAnalyzer is an actor, so all classify calls must be awaited.
final class AudioClassificationTests: XCTestCase {

    private var analyzer: PassiveAudioAnalyzer!

    override func setUp() {
        super.setUp()
        analyzer = PassiveAudioAnalyzer(sessionStart: Date())
    }

    override func tearDown() {
        analyzer = nil
        super.tearDown()
    }

    // MARK: - Silence: rmsDB < -50

    func testSilenceClassification() async {
        let result = await analyzer.classify(rmsDB: -55, zcr: 0.05, dominantFreq: 200)
        XCTAssertEqual(result, .silence)
    }

    func testSilenceBoundaryJustBelow() async {
        // rmsDB = -50.1 should be silence
        let result = await analyzer.classify(rmsDB: -50.1, zcr: 0.05, dominantFreq: 200)
        XCTAssertEqual(result, .silence)
    }

    func testSilenceBoundaryAtThreshold() async {
        // rmsDB = -50 is NOT < -50, so should NOT be silence
        let result = await analyzer.classify(rmsDB: -50, zcr: 0.05, dominantFreq: 200)
        XCTAssertNotEqual(result, .silence)
    }

    // MARK: - Breathing: dominantFreq < 500 && zcr < 0.1

    func testBreathingClassification() async {
        let result = await analyzer.classify(rmsDB: -40, zcr: 0.05, dominantFreq: 200)
        XCTAssertEqual(result, .breathing)
    }

    func testBreathingBoundaryZCR() async {
        // zcr = 0.1 is NOT < 0.1, so should not be breathing
        let result = await analyzer.classify(rmsDB: -40, zcr: 0.1, dominantFreq: 200)
        XCTAssertNotEqual(result, .breathing)
    }

    // MARK: - Snoring: dominantFreq < 300 && rmsDB > -30

    func testSnoringClassification() async {
        let result = await analyzer.classify(rmsDB: -25, zcr: 0.15, dominantFreq: 200)
        XCTAssertEqual(result, .snoring)
    }

    // MARK: - Movement: zcr > 0.3

    func testMovementClassification() async {
        let result = await analyzer.classify(rmsDB: -35, zcr: 0.4, dominantFreq: 600)
        XCTAssertEqual(result, .movement)
    }

    func testMovementBoundaryAtThreshold() async {
        // zcr = 0.3 is NOT > 0.3, should not be movement
        let result = await analyzer.classify(rmsDB: -35, zcr: 0.3, dominantFreq: 600)
        XCTAssertNotEqual(result, .movement)
    }

    // MARK: - Ambient Noise: fallthrough

    func testAmbientNoiseClassification() async {
        // Does not match any other rule
        let result = await analyzer.classify(rmsDB: -35, zcr: 0.2, dominantFreq: 600)
        XCTAssertEqual(result, .ambientNoise)
    }

    // MARK: - Rule Priority

    func testSilenceSupersedesOtherRules() async {
        // Even with breathing-like freq and zcr, silence wins because rmsDB < -50
        let result = await analyzer.classify(rmsDB: -55, zcr: 0.05, dominantFreq: 200)
        XCTAssertEqual(result, .silence)
    }
}
