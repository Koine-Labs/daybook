import AVFoundation
import Accelerate
import Foundation

/// Emits a 19 kHz ultrasonic tone and analyzes the reflected signal to extract breathing rate.
///
/// The sonar principle: chest/abdomen movement during breathing modulates the amplitude
/// of the reflected 19 kHz signal. By tracking the 19 kHz FFT bin amplitude over time
/// and applying autocorrelation, we can extract breathing rate and regularity.
///
/// This actor owns the single AVAudioEngine mic tap and forwards raw audio buffers
/// to `PassiveAudioAnalyzer` for ambient audio classification.
actor SonarEngine {
    private var audioEngine: AVAudioEngine?
    private var playerNode: AVAudioPlayerNode?
    private let sessionStart: Date
    private let passiveAnalyzer: PassiveAudioAnalyzer

    // Amplitude history for breathing rate extraction
    private var amplitudeHistory: [Float] = []
    private var features: [SonarFeatureSample] = []
    private var lastFeatureTime: Date

    // FFT setup (reused across calls)
    private let fftSetup: vDSP_DFT_Setup?
    private let fftSize: Int

    init(sessionStart: Date, passiveAnalyzer: PassiveAudioAnalyzer) {
        self.sessionStart = sessionStart
        self.passiveAnalyzer = passiveAnalyzer
        self.lastFeatureTime = sessionStart
        self.fftSize = SensorConstants.sonarFFTSize
        self.fftSetup = vDSP_DFT_zop_CreateSetup(
            nil,
            vDSP_Length(SensorConstants.sonarFFTSize),
            .FORWARD
        )
    }

    deinit {
        if let fftSetup {
            vDSP_DFT_DestroySetup(fftSetup)
        }
    }

    /// Start the sonar engine. Configures audio session, generates tone, installs mic tap.
    func start() throws {
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.playAndRecord, mode: .measurement, options: [.defaultToSpeaker, .allowBluetoothHFP])
        try session.setPreferredSampleRate(SensorConstants.sonarSampleRate)
        try session.setActive(true)

        let engine = AVAudioEngine()
        let player = AVAudioPlayerNode()
        engine.attach(player)

        // Generate 19 kHz sine wave buffer
        let sampleRate = Float(SensorConstants.sonarSampleRate)
        let bufferDuration: Float = 1.0 // 1 second of tone, looped
        let frameCount = AVAudioFrameCount(sampleRate * bufferDuration)

        guard let format = AVAudioFormat(
            standardFormatWithSampleRate: SensorConstants.sonarSampleRate,
            channels: 1
        ) else { return }

        guard let toneBuffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: frameCount) else { return }
        toneBuffer.frameLength = frameCount

        let channelData = toneBuffer.floatChannelData![0]
        for i in 0..<Int(frameCount) {
            channelData[i] = SensorConstants.sonarAmplitude * sinf(
                2.0 * .pi * SensorConstants.sonarFrequencyHz * Float(i) / sampleRate
            )
        }

        engine.connect(player, to: engine.mainMixerNode, format: format)

        // Install mic tap for signal capture
        let inputFormat = engine.inputNode.outputFormat(forBus: 0)
        engine.inputNode.installTap(onBus: 0, bufferSize: AVAudioFrameCount(fftSize), format: inputFormat) {
            [weak self] buffer, _ in
            guard let self else { return }
            Task {
                await self.processAudioBuffer(buffer)
            }
        }

        try engine.start()
        player.play()
        player.scheduleBuffer(toneBuffer, at: nil, options: .loops)

        self.audioEngine = engine
        self.playerNode = player
    }

    /// Stop the sonar engine and release audio resources.
    func stop() {
        playerNode?.stop()
        audioEngine?.inputNode.removeTap(onBus: 0)
        audioEngine?.stop()
        audioEngine = nil
        playerNode = nil

        try? AVAudioSession.sharedInstance().setActive(false)
    }

    /// Drain collected sonar features for session storage.
    func drainFeatures() -> [SonarFeatureSample] {
        let drained = features
        features.removeAll(keepingCapacity: true)
        return drained
    }

    /// Whether the engine is currently running.
    var isRunning: Bool { audioEngine?.isRunning ?? false }

    // MARK: - Audio Processing

    private func processAudioBuffer(_ buffer: AVAudioPCMBuffer) async {
        // Forward to passive audio analyzer (shares the mic tap)
        await passiveAnalyzer.processBuffer(buffer)

        // Rate-limit sonar feature extraction
        guard Date().timeIntervalSince(lastFeatureTime) >= SensorConstants.sonarFeatureInterval else { return }
        lastFeatureTime = Date()

        guard let channelData = buffer.floatChannelData?[0] else { return }
        let frameCount = Int(buffer.frameLength)
        guard frameCount >= fftSize else { return }

        // Extract 19 kHz amplitude via FFT
        let amplitude = extract19kHzAmplitude(from: channelData, frameCount: frameCount)
        amplitudeHistory.append(amplitude)

        // Keep history bounded
        if amplitudeHistory.count > SensorConstants.sonarAmplitudeHistorySize {
            amplitudeHistory.removeFirst(amplitudeHistory.count - SensorConstants.sonarAmplitudeHistorySize)
        }

        // Need sufficient history for breathing rate estimation
        guard amplitudeHistory.count >= 60 else {
            let ts = TimestampUtilities.relativeTimestamp(from: Date(), sessionStart: sessionStart)
            features.append(SonarFeatureSample(
                timestamp: ts,
                breathingRate: nil,
                breathingRegularity: nil,
                signalStrength: 20 * log10(amplitude + Float.ulpOfOne)
            ))
            return
        }

        // Estimate breathing rate via autocorrelation
        let (breathingRate, regularity, secondPeakLag, secondPeakValue, correlationDecay) = estimateBreathingRate()
        let signalStrength = 20 * log10(amplitude + Float.ulpOfOne)

        let ts = TimestampUtilities.relativeTimestamp(from: Date(), sessionStart: sessionStart)
        features.append(SonarFeatureSample(
            timestamp: ts,
            breathingRate: breathingRate,
            breathingRegularity: regularity,
            signalStrength: signalStrength,
            secondPeakLag: secondPeakLag,
            secondPeakValue: secondPeakValue,
            correlationDecay: correlationDecay
        ))
    }

    /// Extract the magnitude of the 19 kHz FFT bin from audio samples.
    private func extract19kHzAmplitude(from samples: UnsafePointer<Float>, frameCount: Int) -> Float {
        guard let fftSetup else { return 0 }

        let n = min(frameCount, fftSize)

        // Prepare real/imaginary input for DFT
        var realInput = [Float](repeating: 0, count: fftSize)
        let imagInput = [Float](repeating: 0, count: fftSize)
        var realOutput = [Float](repeating: 0, count: fftSize)
        var imagOutput = [Float](repeating: 0, count: fftSize)

        // Copy samples (apply Hann window)
        var window = [Float](repeating: 0, count: n)
        vDSP_hann_window(&window, vDSP_Length(n), Int32(vDSP_HANN_NORM))
        vDSP_vmul(samples, 1, window, 1, &realInput, 1, vDSP_Length(n))

        vDSP_DFT_Execute(fftSetup, realInput, imagInput, &realOutput, &imagOutput)

        // Find the bin closest to 19 kHz
        let binResolution = Float(SensorConstants.sonarSampleRate) / Float(fftSize)
        let targetBin = Int(SensorConstants.sonarFrequencyHz / binResolution)

        guard targetBin < fftSize / 2 else { return 0 }

        // Magnitude of the target bin
        let real = realOutput[targetBin]
        let imag = imagOutput[targetBin]
        return sqrtf(real * real + imag * imag) / Float(fftSize)
    }

    /// Estimate breathing rate from amplitude history using autocorrelation.
    private func estimateBreathingRate() -> (rate: Float?, regularity: Float?, secondPeakLag: Float?, secondPeakValue: Float?, correlationDecay: Float?) {
        let signal = amplitudeHistory
        let count = signal.count

        // Compute autocorrelation: R[lag] = sum(signal[i] * signal[i + lag])
        var autocorr = [Float](repeating: 0, count: count)
        for lag in 0..<count {
            let n = count - lag
            var dotProduct: Float = 0
            vDSP_dotpr(signal, 1, Array(signal[lag...]), 1, &dotProduct, vDSP_Length(n))
            autocorr[lag] = dotProduct
        }

        // Breathing rate bounds → lag bounds
        // Each sample is ~sonarFeatureInterval apart
        let sampleInterval = Float(SensorConstants.sonarFeatureInterval)
        let minLag = Int(60.0 / SensorConstants.breathingRateMaxBPM / sampleInterval)
        let maxLag = Int(60.0 / SensorConstants.breathingRateMinBPM / sampleInterval)

        guard maxLag > minLag, maxLag < count else { return (nil, nil, nil, nil, nil) }

        // Find peak in valid lag range
        var maxVal: Float = 0
        var maxIdx: vDSP_Length = 0
        let searchRange = Array(autocorr[minLag...maxLag])
        vDSP_maxvi(searchRange, 1, &maxVal, &maxIdx, vDSP_Length(maxLag - minLag + 1))

        let peakLag = Int(maxIdx) + minLag
        let breathingPeriodSeconds = Float(peakLag) * sampleInterval
        let breathingRate = 60.0 / breathingPeriodSeconds

        // Regularity: autocorrelation peak height normalized by zero-lag
        let regularity = maxVal / (autocorr[0] + Float.ulpOfOne)

        // Secondary peak: scan valid lags excluding primary peak neighborhood
        let primaryLag = Int(maxIdx) + minLag
        let exclusionRadius = 1
        var secondMaxVal: Float = 0
        var secondMaxLag: Int = 0
        for i in minLag...maxLag where abs(i - primaryLag) > exclusionRadius {
            if autocorr[i] > secondMaxVal {
                secondMaxVal = autocorr[i]
                secondMaxLag = i
            }
        }

        let secondPeakLag: Float?
        let secondPeakValue: Float?
        if secondMaxVal > maxVal * 0.2 {
            secondPeakLag = Float(secondMaxLag) * sampleInterval
            secondPeakValue = secondMaxVal / (autocorr[0] + Float.ulpOfOne)
        } else {
            secondPeakLag = nil
            secondPeakValue = nil
        }

        // Correlation decay: ratio of mid-window autocorrelation to zero-lag
        let halfWindow = count / 2
        let correlationDecay: Float?
        if autocorr[0] > Float.ulpOfOne {
            correlationDecay = autocorr[halfWindow] / autocorr[0]
        } else {
            correlationDecay = nil
        }

        let validRate = breathingRate.isFinite ? breathingRate : nil
        let validRegularity = regularity.isFinite ? regularity : nil

        return (validRate, validRegularity, secondPeakLag, secondPeakValue, correlationDecay)
    }
}
