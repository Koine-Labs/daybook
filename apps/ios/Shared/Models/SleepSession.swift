import Foundation

/// A single timestamped numeric measurement (e.g., respiratory rate, SpO2, wrist temperature).
nonisolated struct TimestampedSample: Codable, Sendable, Equatable {
    let timestamp: TimeInterval
    let value: Double
}

/// Top-level container for an entire sleep session's collected data.
/// This is the object that gets serialized to JSON for export and offline analysis.
nonisolated struct SleepSession: Codable, Sendable {
    let id: UUID
    let startDate: Date
    var endDate: Date?

    /// All sensor packets received from the watch, in order.
    var watchPackets: [SensorPacket]
    /// Sonar-derived breathing features from the iPhone.
    var sonarFeatures: [SonarFeatureSample]
    /// Passive audio classification features from the iPhone.
    var audioFeatures: [AudioFeatureSample]
    /// Apple HealthKit sleep stage labels (ground truth for offline analysis).
    var sleepStages: [SleepStageLabel]
    /// Respiratory rate samples from HealthKit (breaths per minute).
    var respiratoryRateSamples: [TimestampedSample] = []
    /// Blood oxygen saturation samples from HealthKit (0–1 fraction).
    var spo2Samples: [TimestampedSample] = []
    /// Wrist temperature deviation samples from HealthKit (degrees Celsius).
    var wristTemperatureSamples: [TimestampedSample] = []
    /// Session metadata for data quality tracking.
    var metadata: SessionMetadata
}

// MARK: - Sonar Features

/// A single sonar-derived breathing measurement.
nonisolated struct SonarFeatureSample: Codable, Sendable, Equatable {
    /// Seconds since session start.
    let timestamp: TimeInterval
    /// Estimated breathing rate in breaths per minute, or nil if signal too weak.
    let breathingRate: Float?
    /// Breathing regularity (0–1), derived from autocorrelation peak strength.
    let breathingRegularity: Float?
    /// Signal strength in dB of the 19 kHz reflection.
    let signalStrength: Float
    /// Lag (in samples) of the second autocorrelation peak, if detected.
    let secondPeakLag: Float?
    /// Amplitude of the second autocorrelation peak (0–1), if detected.
    let secondPeakValue: Float?
    /// Rate of autocorrelation decay from the primary peak — higher means noisier signal.
    let correlationDecay: Float?

    init(timestamp: TimeInterval, breathingRate: Float?, breathingRegularity: Float?, signalStrength: Float,
         secondPeakLag: Float? = nil, secondPeakValue: Float? = nil, correlationDecay: Float? = nil) {
        self.timestamp = timestamp
        self.breathingRate = breathingRate
        self.breathingRegularity = breathingRegularity
        self.signalStrength = signalStrength
        self.secondPeakLag = secondPeakLag
        self.secondPeakValue = secondPeakValue
        self.correlationDecay = correlationDecay
    }

    private enum CodingKeys: String, CodingKey {
        case timestamp, breathingRate, breathingRegularity, signalStrength
        case secondPeakLag, secondPeakValue, correlationDecay
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        timestamp = try container.decode(TimeInterval.self, forKey: .timestamp)
        breathingRate = try container.decodeIfPresent(Float.self, forKey: .breathingRate)
        breathingRegularity = try container.decodeIfPresent(Float.self, forKey: .breathingRegularity)
        signalStrength = try container.decode(Float.self, forKey: .signalStrength)
        secondPeakLag = try container.decodeIfPresent(Float.self, forKey: .secondPeakLag)
        secondPeakValue = try container.decodeIfPresent(Float.self, forKey: .secondPeakValue)
        correlationDecay = try container.decodeIfPresent(Float.self, forKey: .correlationDecay)
    }
}

// MARK: - Audio Features

/// A single ambient audio analysis result.
nonisolated struct AudioFeatureSample: Codable, Sendable, Equatable {
    /// Seconds since session start.
    let timestamp: TimeInterval
    /// Dominant frequency in Hz.
    let dominantFrequency: Float
    /// Spectral centroid in Hz.
    let spectralCentroid: Float
    /// RMS energy in dB.
    let rmsEnergy: Float
    /// Zero crossing rate (0–1).
    let zeroCrossingRate: Float
    /// Rule-based classification of the audio environment.
    let classification: AudioEventClass
    /// Width of the spectral peak in Hz.
    let spectralBandwidth: Float
    /// Flatness of the spectrum (0 = tonal, 1 = noise-like).
    let spectralFlatness: Float
    /// Frequency below which a fixed percentage of spectral energy lies (Hz).
    let spectralRolloff: Float
    /// Frame-to-frame spectral change magnitude.
    let spectralFlux: Float
    /// Energy in frequency sub-bands (e.g., low / mid / high).
    let subbandEnergy: [Float]

    init(timestamp: TimeInterval, dominantFrequency: Float, spectralCentroid: Float, rmsEnergy: Float,
         zeroCrossingRate: Float, classification: AudioEventClass,
         spectralBandwidth: Float = 0, spectralFlatness: Float = 0, spectralRolloff: Float = 0,
         spectralFlux: Float = 0, subbandEnergy: [Float] = []) {
        self.timestamp = timestamp
        self.dominantFrequency = dominantFrequency
        self.spectralCentroid = spectralCentroid
        self.rmsEnergy = rmsEnergy
        self.zeroCrossingRate = zeroCrossingRate
        self.classification = classification
        self.spectralBandwidth = spectralBandwidth
        self.spectralFlatness = spectralFlatness
        self.spectralRolloff = spectralRolloff
        self.spectralFlux = spectralFlux
        self.subbandEnergy = subbandEnergy
    }

    private enum CodingKeys: String, CodingKey {
        case timestamp, dominantFrequency, spectralCentroid, rmsEnergy
        case zeroCrossingRate, classification
        case spectralBandwidth, spectralFlatness, spectralRolloff, spectralFlux, subbandEnergy
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        timestamp = try container.decode(TimeInterval.self, forKey: .timestamp)
        dominantFrequency = try container.decode(Float.self, forKey: .dominantFrequency)
        spectralCentroid = try container.decode(Float.self, forKey: .spectralCentroid)
        rmsEnergy = try container.decode(Float.self, forKey: .rmsEnergy)
        zeroCrossingRate = try container.decode(Float.self, forKey: .zeroCrossingRate)
        classification = try container.decode(AudioEventClass.self, forKey: .classification)
        spectralBandwidth = try container.decodeIfPresent(Float.self, forKey: .spectralBandwidth) ?? 0
        spectralFlatness = try container.decodeIfPresent(Float.self, forKey: .spectralFlatness) ?? 0
        spectralRolloff = try container.decodeIfPresent(Float.self, forKey: .spectralRolloff) ?? 0
        spectralFlux = try container.decodeIfPresent(Float.self, forKey: .spectralFlux) ?? 0
        subbandEnergy = try container.decodeIfPresent([Float].self, forKey: .subbandEnergy) ?? []
    }
}

/// Coarse audio event classification for Phase 1.
nonisolated enum AudioEventClass: String, Codable, Sendable {
    case silence
    case breathing
    case snoring
    case movement
    case ambientNoise
}

// MARK: - Sleep Stage Labels

/// A time-ranged sleep stage label from Apple HealthKit.
nonisolated struct SleepStageLabel: Codable, Sendable, Equatable {
    /// Start of this stage, seconds since session start.
    let startTimestamp: TimeInterval
    /// End of this stage, seconds since session start.
    let endTimestamp: TimeInterval
    /// The sleep stage classification.
    let stage: SleepStage
}

// MARK: - Session Metadata

/// Metadata captured at session start/end for data quality assessment.
nonisolated struct SessionMetadata: Codable, Sendable, Equatable {
    let appVersion: String
    var watchModel: String?
    let iphoneModel: String
    var osVersionWatch: String?
    let osVersioniOS: String

    var watchBatteryAtStart: Float?
    var watchBatteryAtEnd: Float?
    var phoneBatteryAtStart: Float?
    var phoneBatteryAtEnd: Float?

    var totalPacketsReceived: UInt32
    var totalPacketsExpected: UInt32?
    var connectivityDropCount: UInt32
}
