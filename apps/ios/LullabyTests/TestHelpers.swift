import Foundation
@testable import Lullaby

/// Factory methods for constructing test data throughout the test suite.
nonisolated enum TestFactory {

    // MARK: - Sensor Packet

    static func makeSensorPacket(
        sessionID: UUID = UUID(),
        batchIndex: UInt32 = 0,
        capturedAt: Date = Date(timeIntervalSinceReferenceDate: 700_000_000),
        heartRateSamples: [HeartRateSample] = [],
        hrvSamples: [HRVSample] = [],
        accelerometerSamples: [AccelerometerSample] = [],
        gyroscopeSamples: [GyroscopeSample] = []
    ) -> SensorPacket {
        SensorPacket(
            sessionID: sessionID,
            batchIndex: batchIndex,
            capturedAt: capturedAt,
            heartRateSamples: heartRateSamples,
            hrvSamples: hrvSamples,
            accelerometerSamples: accelerometerSamples,
            gyroscopeSamples: gyroscopeSamples
        )
    }

    // MARK: - Sleep Session

    static func makeSleepSession(
        id: UUID = UUID(),
        startDate: Date = Date(),
        endDate: Date? = nil,
        watchPackets: [SensorPacket] = [],
        sonarFeatures: [SonarFeatureSample] = [],
        audioFeatures: [AudioFeatureSample] = [],
        sleepStages: [SleepStageLabel] = [],
        metadata: SessionMetadata? = nil
    ) -> SleepSession {
        SleepSession(
            id: id,
            startDate: startDate,
            endDate: endDate,
            watchPackets: watchPackets,
            sonarFeatures: sonarFeatures,
            audioFeatures: audioFeatures,
            sleepStages: sleepStages,
            metadata: metadata ?? makeSessionMetadata()
        )
    }

    // MARK: - Session Metadata

    static func makeSessionMetadata(
        appVersion: String = "1.0.0",
        watchModel: String? = "Apple Watch Series 9",
        iphoneModel: String = "iPhone 15 Pro",
        osVersionWatch: String? = "watchOS 10.2",
        osVersioniOS: String = "iOS 17.2",
        watchBatteryAtStart: Float? = 85.0,
        watchBatteryAtEnd: Float? = 42.0,
        phoneBatteryAtStart: Float? = 90.0,
        phoneBatteryAtEnd: Float? = 65.0,
        totalPacketsReceived: UInt32 = 960,
        totalPacketsExpected: UInt32? = 960,
        connectivityDropCount: UInt32 = 0
    ) -> SessionMetadata {
        SessionMetadata(
            appVersion: appVersion,
            watchModel: watchModel,
            iphoneModel: iphoneModel,
            osVersionWatch: osVersionWatch,
            osVersioniOS: osVersioniOS,
            watchBatteryAtStart: watchBatteryAtStart,
            watchBatteryAtEnd: watchBatteryAtEnd,
            phoneBatteryAtStart: phoneBatteryAtStart,
            phoneBatteryAtEnd: phoneBatteryAtEnd,
            totalPacketsReceived: totalPacketsReceived,
            totalPacketsExpected: totalPacketsExpected,
            connectivityDropCount: connectivityDropCount
        )
    }

    // MARK: - Individual Samples

    static func makeHeartRateSample(
        timestamp: TimeInterval = 0,
        bpm: Double = 65
    ) -> HeartRateSample {
        HeartRateSample(timestamp: timestamp, bpm: bpm)
    }

    static func makeHRVSample(
        timestamp: TimeInterval = 0,
        sdnn: Double = 50
    ) -> HRVSample {
        HRVSample(timestamp: timestamp, sdnn: sdnn)
    }

    static func makeAccelerometerSample(
        timestamp: TimeInterval = 0,
        x: Float = 0, y: Float = 0, z: Float = -1
    ) -> AccelerometerSample {
        AccelerometerSample(timestamp: timestamp, x: x, y: y, z: z)
    }

    static func makeGyroscopeSample(
        timestamp: TimeInterval = 0,
        x: Float = 0, y: Float = 0, z: Float = 0
    ) -> GyroscopeSample {
        GyroscopeSample(timestamp: timestamp, x: x, y: y, z: z)
    }

    static func makeSonarFeatureSample(
        timestamp: TimeInterval = 0,
        breathingRate: Float? = 15.0,
        breathingRegularity: Float? = 0.85,
        signalStrength: Float = -20.0,
        secondPeakLag: Float? = nil,
        secondPeakValue: Float? = nil,
        correlationDecay: Float? = nil
    ) -> SonarFeatureSample {
        SonarFeatureSample(
            timestamp: timestamp,
            breathingRate: breathingRate,
            breathingRegularity: breathingRegularity,
            signalStrength: signalStrength,
            secondPeakLag: secondPeakLag,
            secondPeakValue: secondPeakValue,
            correlationDecay: correlationDecay
        )
    }

    static func makeAudioFeatureSample(
        timestamp: TimeInterval = 0,
        dominantFrequency: Float = 200,
        spectralCentroid: Float = 500,
        rmsEnergy: Float = -40,
        zeroCrossingRate: Float = 0.05,
        classification: AudioEventClass = .silence,
        spectralBandwidth: Float = 0,
        spectralFlatness: Float = 0,
        spectralRolloff: Float = 0,
        spectralFlux: Float = 0,
        subbandEnergy: [Float] = []
    ) -> AudioFeatureSample {
        AudioFeatureSample(
            timestamp: timestamp,
            dominantFrequency: dominantFrequency,
            spectralCentroid: spectralCentroid,
            rmsEnergy: rmsEnergy,
            zeroCrossingRate: zeroCrossingRate,
            classification: classification,
            spectralBandwidth: spectralBandwidth,
            spectralFlatness: spectralFlatness,
            spectralRolloff: spectralRolloff,
            spectralFlux: spectralFlux,
            subbandEnergy: subbandEnergy
        )
    }

    static func makeSleepStageLabel(
        startTimestamp: TimeInterval = 0,
        endTimestamp: TimeInterval = 1800,
        stage: SleepStage = .coreLight
    ) -> SleepStageLabel {
        SleepStageLabel(
            startTimestamp: startTimestamp,
            endTimestamp: endTimestamp,
            stage: stage
        )
    }

    // MARK: - Full Session with Data

    static func makePopulatedSession() -> SleepSession {
        let sessionID = UUID()
        let start = Date(timeIntervalSinceReferenceDate: 700_000_000)
        let end = start.addingTimeInterval(8 * 3600)

        let packets = (0..<5).map { i -> SensorPacket in
            let ts = TimeInterval(i) * 30.0
            return SensorPacket(
                sessionID: sessionID,
                batchIndex: UInt32(i),
                capturedAt: start.addingTimeInterval(ts),
                heartRateSamples: [HeartRateSample(timestamp: ts, bpm: 60 + Double(i))],
                hrvSamples: [HRVSample(timestamp: ts, sdnn: 40 + Double(i) * 5)],
                accelerometerSamples: [AccelerometerSample(timestamp: ts, x: 0, y: 0, z: -1)]
            )
        }

        let sonar = [
            SonarFeatureSample(timestamp: 0, breathingRate: 14, breathingRegularity: 0.9, signalStrength: -18),
            SonarFeatureSample(timestamp: 60, breathingRate: 15, breathingRegularity: 0.85, signalStrength: -20),
        ]

        let audio = [
            AudioFeatureSample(timestamp: 0, dominantFrequency: 200, spectralCentroid: 400, rmsEnergy: -55, zeroCrossingRate: 0.03, classification: .silence),
            AudioFeatureSample(timestamp: 60, dominantFrequency: 150, spectralCentroid: 300, rmsEnergy: -35, zeroCrossingRate: 0.05, classification: .breathing),
        ]

        let stages = [
            SleepStageLabel(startTimestamp: 0, endTimestamp: 3600, stage: .coreLight),
            SleepStageLabel(startTimestamp: 3600, endTimestamp: 7200, stage: .deepSleep),
            SleepStageLabel(startTimestamp: 7200, endTimestamp: 10800, stage: .remSleep),
        ]

        return SleepSession(
            id: sessionID,
            startDate: start,
            endDate: end,
            watchPackets: packets,
            sonarFeatures: sonar,
            audioFeatures: audio,
            sleepStages: stages,
            metadata: makeSessionMetadata(totalPacketsReceived: 5, totalPacketsExpected: 5)
        )
    }
}
