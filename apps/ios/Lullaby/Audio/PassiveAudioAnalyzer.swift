import AVFoundation
import Accelerate
import Foundation

/// Analyzes ambient audio for breathing, snoring, and movement classification.
///
/// Receives audio buffers forwarded from `SonarEngine` (since only one mic tap is
/// allowed per AVAudioEngine bus). Extracts spectral features and applies a
/// simple rule-based classifier for Phase 1 data collection.
actor PassiveAudioAnalyzer {
    private let sessionStart: Date
    private var features: [AudioFeatureSample] = []
    private var lastFeatureTime: Date
    private var previousMagnitudes: [Float]?

    init(sessionStart: Date) {
        self.sessionStart = sessionStart
        self.lastFeatureTime = sessionStart
    }

    /// Process an audio buffer forwarded from SonarEngine.
    func processBuffer(_ buffer: AVAudioPCMBuffer) {
        // Rate-limit feature extraction
        guard Date().timeIntervalSince(lastFeatureTime) >= SensorConstants.audioFeatureInterval else { return }
        lastFeatureTime = Date()

        guard let channelData = buffer.floatChannelData?[0] else { return }
        let count = Int(buffer.frameLength)
        guard count > 0 else { return }

        // Feature 1: RMS Energy (loudness)
        var rms: Float = 0
        vDSP_rmsqv(channelData, 1, &rms, vDSP_Length(count))
        let rmsDB = 20 * log10(rms + Float.ulpOfOne)

        // Feature 2: Zero Crossing Rate
        var zcr: Float = 0
        for i in 1..<count {
            if (channelData[i] >= 0) != (channelData[i - 1] >= 0) {
                zcr += 1
            }
        }
        zcr /= Float(count)

        // Feature 3+: Spectral analysis via FFT
        let (spectralCentroid, dominantFreq, spectralBandwidth, spectralFlatness,
             spectralRolloff, spectralFlux, subbandEnergy) = computeSpectralFeatures(
            channelData: channelData,
            count: count
        )

        // Rule-based classification for Phase 1
        let classification = classify(
            rmsDB: rmsDB,
            zcr: zcr,
            dominantFreq: dominantFreq
        )

        let ts = TimestampUtilities.relativeTimestamp(from: Date(), sessionStart: sessionStart)
        features.append(AudioFeatureSample(
            timestamp: ts,
            dominantFrequency: dominantFreq,
            spectralCentroid: spectralCentroid,
            rmsEnergy: rmsDB,
            zeroCrossingRate: zcr,
            classification: classification,
            spectralBandwidth: spectralBandwidth,
            spectralFlatness: spectralFlatness,
            spectralRolloff: spectralRolloff,
            spectralFlux: spectralFlux,
            subbandEnergy: subbandEnergy
        ))
    }

    /// Drain collected features for session storage.
    func drainFeatures() -> [AudioFeatureSample] {
        let drained = features
        features.removeAll(keepingCapacity: true)
        return drained
    }

    // MARK: - Spectral Analysis

    private func computeSpectralFeatures(
        channelData: UnsafePointer<Float>,
        count: Int
    ) -> (spectralCentroid: Float, dominantFreq: Float, spectralBandwidth: Float, spectralFlatness: Float, spectralRolloff: Float, spectralFlux: Float, subbandEnergy: [Float]) {
        let fftSize = min(count, SensorConstants.audioFFTSize)
        let halfSize = fftSize / 2

        // Apply window and compute FFT using vDSP
        var windowed = [Float](repeating: 0, count: fftSize)
        var window = [Float](repeating: 0, count: fftSize)
        vDSP_hann_window(&window, vDSP_Length(fftSize), Int32(vDSP_HANN_NORM))
        vDSP_vmul(channelData, 1, window, 1, &windowed, 1, vDSP_Length(fftSize))

        // Use vDSP real FFT
        let log2n = vDSP_Length(log2(Float(fftSize)))
        guard let fftSetup = vDSP_create_fftsetup(log2n, FFTRadix(kFFTRadix2)) else {
            return (0, 0, 0, 0, 0, 0, [])
        }
        defer { vDSP_destroy_fftsetup(fftSetup) }

        var realp = [Float](repeating: 0, count: halfSize)
        var imagp = [Float](repeating: 0, count: halfSize)

        windowed.withUnsafeMutableBufferPointer { windowedPtr in
            realp.withUnsafeMutableBufferPointer { realpPtr in
                imagp.withUnsafeMutableBufferPointer { imagpPtr in
                    var splitComplex = DSPSplitComplex(
                        realp: realpPtr.baseAddress!,
                        imagp: imagpPtr.baseAddress!
                    )
                    windowedPtr.baseAddress!.withMemoryRebound(to: DSPComplex.self, capacity: halfSize) { complexPtr in
                        vDSP_ctoz(complexPtr, 2, &splitComplex, 1, vDSP_Length(halfSize))
                    }
                    vDSP_fft_zrip(fftSetup, &splitComplex, 1, log2n, FFTDirection(kFFTDirection_Forward))
                }
            }
        }

        // Compute magnitudes
        var magnitudes = [Float](repeating: 0, count: halfSize)
        realp.withUnsafeMutableBufferPointer { rp in
            imagp.withUnsafeMutableBufferPointer { ip in
                var sc = DSPSplitComplex(realp: rp.baseAddress!, imagp: ip.baseAddress!)
                vDSP_zvmags(&sc, 1, &magnitudes, 1, vDSP_Length(halfSize))
            }
        }

        // Spectral centroid
        let sampleRate = Float(SensorConstants.sonarSampleRate)
        let binResolution = sampleRate / Float(fftSize)
        var weightedSum: Float = 0
        var totalMag: Float = 0
        for i in 0..<halfSize {
            let freq = Float(i) * binResolution
            weightedSum += freq * magnitudes[i]
            totalMag += magnitudes[i]
        }
        let spectralCentroid = totalMag > 0 ? weightedSum / totalMag : 0

        // Dominant frequency
        var maxMag: Float = 0
        var maxIdx: vDSP_Length = 0
        vDSP_maxvi(magnitudes, 1, &maxMag, &maxIdx, vDSP_Length(halfSize))
        let dominantFreq = Float(maxIdx) * binResolution

        // Spectral bandwidth (std dev of frequency weighted by magnitude)
        var bandwidthSum: Float = 0
        for i in 0..<halfSize {
            let freq = Float(i) * binResolution
            let diff = freq - spectralCentroid
            bandwidthSum += magnitudes[i] * diff * diff
        }
        let spectralBandwidth = sqrt(bandwidthSum / (totalMag + Float.ulpOfOne))

        // Spectral flatness (geometric / arithmetic mean of magnitude)
        var logSum: Float = 0
        for i in 0..<halfSize {
            logSum += log(magnitudes[i] + Float.ulpOfOne)
        }
        let geometricMean = exp(logSum / Float(halfSize))
        let arithmeticMean = totalMag / Float(halfSize)
        let spectralFlatness = geometricMean / (arithmeticMean + Float.ulpOfOne)

        // Spectral rolloff (frequency below which 85% of spectral energy lies)
        let threshold = totalMag * 0.85
        var cumSum: Float = 0
        var rolloffBin = halfSize - 1
        for i in 0..<halfSize {
            cumSum += magnitudes[i]
            if cumSum >= threshold { rolloffBin = i; break }
        }
        let spectralRolloff = Float(rolloffBin) * binResolution

        // Spectral flux (L2 difference vs previous window)
        var flux: Float = 0
        if let prev = previousMagnitudes, prev.count == halfSize {
            for i in 0..<halfSize {
                let diff = magnitudes[i] - prev[i]
                flux += diff * diff
            }
            flux = sqrt(flux)
        }
        previousMagnitudes = magnitudes

        // Sub-band energy (5 bands for 48kHz/2048-FFT at ~23.4 Hz/bin)
        let bands: [(Int, Int)] = [(0, 10), (11, 21), (22, 42), (43, 85), (86, 170)]
        var subbandEnergy: [Float] = []
        for (lo, hi) in bands {
            var energy: Float = 0
            let upper = min(hi, halfSize - 1)
            for i in lo...upper { energy += magnitudes[i] * magnitudes[i] }
            subbandEnergy.append(10 * log10(energy + Float.ulpOfOne))
        }

        return (spectralCentroid, dominantFreq, spectralBandwidth, spectralFlatness, spectralRolloff, flux, subbandEnergy)
    }

    // MARK: - Classification

    func classify(rmsDB: Float, zcr: Float, dominantFreq: Float) -> AudioEventClass {
        if rmsDB < -50 {
            return .silence
        } else if dominantFreq < 500 && zcr < 0.1 {
            return .breathing
        } else if dominantFreq < 300 && rmsDB > -30 {
            return .snoring
        } else if zcr > 0.3 {
            return .movement
        } else {
            return .ambientNoise
        }
    }
}
