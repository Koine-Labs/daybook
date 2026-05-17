import Foundation
import Observation

/// MainActor-bound progression/XP manager. Persists a `DreamerProfile` to
/// `Documents/dreamer_profile.json` and grade sidecars to
/// `Documents/sessions/{uuid}_grade.json`.
@Observable
@MainActor
final class ProgressionManager {

    // MARK: Published state

    private(set) var profile: DreamerProfile

    // MARK: Private

    private let profileURL: URL
    private let sessionsURL: URL

    // MARK: Init

    init() {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
        profileURL = docs.appendingPathComponent("dreamer_profile.json")
        sessionsURL = docs.appendingPathComponent("sessions", isDirectory: true)
        try? FileManager.default.createDirectory(at: sessionsURL, withIntermediateDirectories: true)

        // Load existing profile, or create default
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        if let data = try? Data(contentsOf: docs.appendingPathComponent("dreamer_profile.json")),
           let loaded = try? decoder.decode(DreamerProfile.self, from: data) {
            profile = loaded
        } else {
            profile = .default
        }
    }

    // MARK: - Sleep XP

    /// Awards XP for a tracked night based on grade, duration, and streak.
    func awardSleepXP(grade: SleepGrade,
                      duration: TimeInterval,
                      bedtimeDeviation: TimeInterval?) {
        // Base + grade bonus
        var xp = 10 + grade.gradeXPBonus

        // Duration bonus: +1 per 30 min of sleep, up to +10
        let durationBonus = min(10, Int(duration / 1800))
        xp += durationBonus

        // Consistency bonus (bedtime within 30 min of target)
        if let deviation = bedtimeDeviation, abs(deviation) <= 1800 {
            xp += 5
        }

        // Streak multiplier
        let multiplier = streakMultiplier()
        xp = Int(Double(xp) * multiplier)

        profile.sleepXP += xp
        profile.sleepRank = DreamerProfile.rankFor(xp: profile.sleepXP)
        profile.totalNightsTracked += 1
        save()
    }

    // MARK: - Dream XP

    /// Awards XP for a logged dream entry.
    func awardDreamXP(for entry: DreamEntry) {
        var xp = 15  // base

        if entry.isLucid { xp += 30 }
        if entry.vividness >= 4 { xp += 10 }
        if entry.isRichEntry {
            xp += 15  // 500+ chars
        } else if entry.hasNarrative {
            xp += 10  // 100+ chars
        }
        if entry.emotions.count >= 2 { xp += 5 }

        // Streak multiplier
        let multiplier = streakMultiplier()
        xp = Int(Double(xp) * multiplier)

        profile.dreamXP += xp
        profile.dreamRank = DreamerProfile.rankFor(xp: profile.dreamXP)
        profile.totalDreamsLogged += 1
        if entry.isLucid { profile.totalLucidNights += 1 }
        save()
    }

    // MARK: - Grade Computation

    /// Computes a `SleepGrade` from raw sleep metrics.
    ///
    /// When stage data is available (deep/REM), uses a 30/30/20/20 weighting
    /// (duration / stageQuality / awakeTime / consistency). Without stage data,
    /// falls back to 40/30/30 (duration / awakeTime / consistency).
    func computeGrade(
        duration: TimeInterval,
        targetDuration: TimeInterval,
        awakeTime: TimeInterval,
        totalSleepTime: TimeInterval,
        deepSleepPct: Double?,
        remSleepPct: Double?,
        bedtimeDeviation: TimeInterval?
    ) -> SleepGrade {

        // --- Component scores (0-100) ---

        // Duration score: penalise proportionally below target, cap at 100
        let durationRatio = totalSleepTime / max(targetDuration, 1)
        let durationScore = min(100.0, durationRatio * 100.0)

        // Awake time score: awake fraction of total time in bed
        let totalInBed = max(duration, 1)
        let awakeFraction = awakeTime / totalInBed
        let awakeScore = max(0.0, 100.0 - awakeFraction * 200.0)  // ≥50% awake → 0

        // Stage quality score (nil when no HealthKit data)
        let stageQualityScore: Double?
        if let deep = deepSleepPct, let rem = remSleepPct {
            // Targets: deep 20%, REM 25%
            let deepScore = min(100.0, (deep / 0.20) * 100.0)
            let remScore  = min(100.0, (rem  / 0.25) * 100.0)
            stageQualityScore = (deepScore + remScore) / 2.0
        } else {
            stageQualityScore = nil
        }

        // Consistency score from bedtime deviation
        let consistencyScore: Double
        if let dev = bedtimeDeviation {
            // Full credit within 15 min, zero at 2 h+
            let deviationMinutes = abs(dev) / 60.0
            consistencyScore = max(0.0, 100.0 - (deviationMinutes / 120.0) * 100.0)
        } else {
            consistencyScore = 70.0  // neutral when unknown
        }

        // --- Weighted composite ---
        let composite: Double
        if let sqScore = stageQualityScore {
            // 30 / 30 / 20 / 20
            composite = durationScore    * 0.30
                      + sqScore          * 0.30
                      + awakeScore       * 0.20
                      + consistencyScore * 0.20
        } else {
            // 40 / 30 / 30
            composite = durationScore    * 0.40
                      + awakeScore       * 0.30
                      + consistencyScore * 0.30
        }

        let letter = SleepGrade.letterFrom(score: composite)
        let isPartial = (stageQualityScore == nil)

        // --- Qualitative label ---
        let label = qualitativeLabel(
            score: composite,
            durationScore: durationScore,
            stageQualityScore: stageQualityScore,
            awakeScore: awakeScore,
            consistencyScore: consistencyScore,
            isPartial: isPartial
        )

        return SleepGrade(
            letter: letter,
            qualitativeLabel: label,
            score: composite,
            isPartial: isPartial,
            components: SleepGrade.GradeComponents(
                durationScore: durationScore,
                stageQualityScore: stageQualityScore,
                awakeTimeScore: awakeScore,
                consistencyScore: consistencyScore
            )
        )
    }

    // MARK: - Preferences

    /// Updates the target sleep duration (in seconds) and persists the change.
    func setTargetSleepDuration(_ duration: TimeInterval) {
        profile.targetSleepDuration = duration
        save()
    }

    // MARK: - Streak

    /// Updates the consecutive-day streak based on a session date.
    func updateStreak(sessionDate: Date) {
        let cal = Calendar.current
        let today = cal.startOfDay(for: sessionDate)

        if let last = profile.lastTrackedDate {
            let lastDay = cal.startOfDay(for: last)
            let diff = cal.dateComponents([.day], from: lastDay, to: today).day ?? 0
            if diff == 1 {
                profile.currentStreak += 1
            } else if diff > 1 {
                profile.currentStreak = 1
                profile.streakStartDate = today
            }
            // diff == 0: same day, no change
        } else {
            profile.currentStreak = 1
            profile.streakStartDate = today
        }

        if profile.currentStreak > profile.longestStreak {
            profile.longestStreak = profile.currentStreak
        }
        profile.lastTrackedDate = sessionDate
        save()
    }

    // MARK: - Persistence

    /// Persists the current profile to disk.
    func save() {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        guard let data = try? encoder.encode(profile) else { return }
        try? data.write(to: profileURL, options: .atomic)
    }

    /// Saves a sleep grade sidecar file at `Documents/sessions/{uuid}_grade.json`.
    func saveGrade(_ grade: SleepGrade, forSessionId id: UUID) {
        let url = sessionsURL.appendingPathComponent("\(id)_grade.json")
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        guard let data = try? encoder.encode(grade) else { return }
        try? data.write(to: url, options: .atomic)
    }

    /// Loads a sleep grade sidecar file, returning nil if not found.
    func loadGrade(forSessionId id: UUID) -> SleepGrade? {
        let url = sessionsURL.appendingPathComponent("\(id)_grade.json")
        guard let data = try? Data(contentsOf: url) else { return nil }
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return try? decoder.decode(SleepGrade.self, from: data)
    }

    // MARK: - Private Helpers

    private func streakMultiplier() -> Double {
        switch profile.currentStreak {
        case 30...: return 2.5
        case 14...: return 2.0
        case 7...:  return 1.5
        default:    return 1.0
        }
    }

    private func qualitativeLabel(
        score: Double,
        durationScore: Double,
        stageQualityScore: Double?,
        awakeScore: Double,
        consistencyScore: Double,
        isPartial: Bool
    ) -> String {

        // Collect all component scores
        var components: [(name: String, value: Double)] = [
            ("duration", durationScore),
            ("awake", awakeScore),
            ("consistency", consistencyScore),
        ]
        if let sq = stageQualityScore {
            components.append(("stageQuality", sq))
        }

        let mean = components.map(\.value).reduce(0, +) / Double(components.count)

        // Find dominant component by highest deviation from mean
        var maxDev = 0.0
        var dominantName = ""
        var dominantPositive = true
        for comp in components {
            let dev = comp.value - mean
            if abs(dev) > abs(maxDev) {
                maxDev = dev
                dominantName = comp.name
                dominantPositive = dev > 0
            }
        }

        var label: String
        if abs(maxDev) < 5.0 {
            // All roughly balanced
            if score >= 85 {
                label = "Well Rested"
            } else if score < 70 {
                label = "Fragmented"
            } else {
                label = "Balanced"
            }
        } else if dominantPositive {
            switch dominantName {
            case "stageQuality": label = score >= 85 ? "Deep Recovery" : "REM Rich"
            case "duration":     label = "Restorative"
            case "awake":        label = "Restful"
            case "consistency":  label = "Consistent"
            default:             label = "Balanced"
            }
        } else {
            switch dominantName {
            case "stageQuality": label = score >= 70 ? "REM Sparse" : "Light Sleep"
            case "duration":     label = "Short"
            case "awake":        label = "Restless"
            case "consistency":  label = "Late Shift"
            default:             label = "Fragmented"
            }
        }

        if isPartial { label += " (partial)" }
        return label
    }
}
