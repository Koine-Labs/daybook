import Foundation

struct DreamerProfile: Codable, Sendable {
    var sleepXP: Int
    var dreamXP: Int
    var sleepRank: Int  // 1-6
    var dreamRank: Int  // 1-6
    var currentStreak: Int
    var longestStreak: Int
    var lastTrackedDate: Date?
    var streakStartDate: Date?
    var totalNightsTracked: Int
    var totalDreamsLogged: Int
    var totalLucidNights: Int
    var targetSleepDuration: TimeInterval  // seconds, default 8h
    var targetBedtime: DateComponents?

    static let `default` = DreamerProfile(
        sleepXP: 0, dreamXP: 0, sleepRank: 1, dreamRank: 1,
        currentStreak: 0, longestStreak: 0, lastTrackedDate: nil, streakStartDate: nil,
        totalNightsTracked: 0, totalDreamsLogged: 0, totalLucidNights: 0,
        targetSleepDuration: 8 * 3600, targetBedtime: nil
    )

    static let rankThresholds = [0, 100, 300, 700, 1500, 3000]

    static func rankFor(xp: Int) -> Int {
        for (index, threshold) in rankThresholds.enumerated().reversed() {
            if xp >= threshold { return index + 1 }
        }
        return 1
    }

    static func xpForNextRank(currentRank: Int) -> Int? {
        guard currentRank < 6 else { return nil }
        return rankThresholds[currentRank]
    }

    static func xpProgressInCurrentRank(xp: Int, rank: Int) -> Double {
        guard rank < 6 else { return 1.0 }
        let currentThreshold = rankThresholds[rank - 1]
        let nextThreshold = rankThresholds[rank]
        let range = nextThreshold - currentThreshold
        guard range > 0 else { return 1.0 }
        return Double(xp - currentThreshold) / Double(range)
    }

    static let sleepTitles = ["Novice Snoozer", "Steady Sleeper", "Restful Soul", "Sleep Sage", "Slumber Architect", "Master of Rest"]
    static let dreamTitles = ["Dreamer Initiate", "Dream Seeker", "Lucid Novice", "Lucid Voyager", "Astral Adept", "Dream Sovereign"]

    var sleepTitle: String { Self.sleepTitles[sleepRank - 1] }
    var dreamTitle: String { Self.dreamTitles[dreamRank - 1] }

    var fusionTitle: String {
        if sleepRank == 6 && dreamRank == 6 { return "Master Dreamer" }
        if sleepRank >= 5 && dreamRank >= 5 { return "Oneironaut" }
        if sleepRank >= 3 && dreamRank >= 5 { return "Restless Visionary" }
        if sleepRank >= 5 && dreamRank >= 3 { return "Lucid Sage" }
        if sleepRank >= 3 && dreamRank >= 3 { return "Dream Walker" }
        if sleepRank >= 3 && dreamRank <= 2 { return "Rested Wanderer" }
        if sleepRank <= 2 && dreamRank >= 3 { return "Tired Seer" }
        return "Awakening Sleeper"
    }

    var environmentRankLevel: Int { max(sleepRank, dreamRank) }
}
