import XCTest
@testable import Lullaby

/// Tests for SensorConstants — validate that all constants are within sensible ranges.
final class SensorConstantsTests: XCTestCase {

    func testAccelerometerOutputIs10Hz() {
        XCTAssertEqual(SensorConstants.accelerometerOutputHz, 10.0, accuracy: 0.001)
    }

    func testSonarFrequencyIsUltrasonic() {
        // 18 kHz is the threshold for ultrasonic (above most adult hearing)
        XCTAssertGreaterThanOrEqual(SensorConstants.sonarFrequencyHz, 18_000)
    }

    func testSonarFFTSizeIsPowerOfTwo() {
        let fft = SensorConstants.sonarFFTSize
        XCTAssertTrue(fft > 0 && (fft & (fft - 1)) == 0, "FFT size \(fft) is not a power of 2")
    }

    func testAudioFFTSizeIsPowerOfTwo() {
        let fft = SensorConstants.audioFFTSize
        XCTAssertTrue(fft > 0 && (fft & (fft - 1)) == 0, "FFT size \(fft) is not a power of 2")
    }

    func testBreathingRateMinLessThanMax() {
        XCTAssertLessThan(SensorConstants.breathingRateMinBPM, SensorConstants.breathingRateMaxBPM)
    }

    func testSonarAmplitudeInRange() {
        XCTAssertGreaterThan(SensorConstants.sonarAmplitude, 0)
        XCTAssertLessThanOrEqual(SensorConstants.sonarAmplitude, 1.0)
    }

    func testBatchIntervalPositive() {
        XCTAssertGreaterThan(SensorConstants.batchInterval, 0)
    }

    func testSampleRateIs48kHz() {
        XCTAssertEqual(SensorConstants.sonarSampleRate, 48_000, accuracy: 0.001)
    }
}
