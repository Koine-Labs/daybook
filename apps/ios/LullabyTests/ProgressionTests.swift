import XCTest
@testable import Lullaby

final class ProgressionTests: XCTestCase {

    // MARK: - Rank boundaries

    func testRankForXP() {
        // 0 and 99 → rank 1
        XCTAssertEqual(DreamerProfile.rankFor(xp: 0),    1)
        XCTAssertEqual(DreamerProfile.rankFor(xp: 99),   1)
        // Exactly at each threshold
        XCTAssertEqual(DreamerProfile.rankFor(xp: 100),  2)
        XCTAssertEqual(DreamerProfile.rankFor(xp: 300),  3)
        XCTAssertEqual(DreamerProfile.rankFor(xp: 700),  4)
        XCTAssertEqual(DreamerProfile.rankFor(xp: 1500), 5)
        XCTAssertEqual(DreamerProfile.rankFor(xp: 3000), 6)
    }

    // MARK: - XP Progress in current rank

    func testXPProgress() {
        // Rank 2 spans 100–299 (range 200). At 200 XP we are 50% through rank 2.
        let progress = DreamerProfile.xpProgressInCurrentRank(xp: 200, rank: 2)
        XCTAssertEqual(progress, 0.5, accuracy: 0.001)

        // At the start of rank 2 (100 XP) progress is 0
        let start = DreamerProfile.xpProgressInCurrentRank(xp: 100, rank: 2)
        XCTAssertEqual(start, 0.0, accuracy: 0.001)

        // Max rank always returns 1.0
        let maxRank = DreamerProfile.xpProgressInCurrentRank(xp: 9999, rank: 6)
        XCTAssertEqual(maxRank, 1.0, accuracy: 0.001)
    }

    // MARK: - Fusion titles

    func testFusionTitles() {
        func profile(sleep: Int, dream: Int) -> DreamerProfile {
            var p = DreamerProfile.default
            p.sleepRank = sleep
            p.dreamRank = dream
            return p
        }

        XCTAssertEqual(profile(sleep: 6, dream: 6).fusionTitle, "Master Dreamer")
        XCTAssertEqual(profile(sleep: 5, dream: 5).fusionTitle, "Oneironaut")
        XCTAssertEqual(profile(sleep: 3, dream: 5).fusionTitle, "Restless Visionary")
        XCTAssertEqual(profile(sleep: 5, dream: 3).fusionTitle, "Lucid Sage")
        XCTAssertEqual(profile(sleep: 3, dream: 3).fusionTitle, "Dream Walker")
        XCTAssertEqual(profile(sleep: 3, dream: 2).fusionTitle, "Rested Wanderer")
        XCTAssertEqual(profile(sleep: 2, dream: 3).fusionTitle, "Tired Seer")
        XCTAssertEqual(profile(sleep: 1, dream: 1).fusionTitle, "Awakening Sleeper")
    }

    // MARK: - Grade letter mapping

    func testGradeLetterMapping() {
        XCTAssertEqual(SleepGrade.letterFrom(score: 100),  "A+")
        XCTAssertEqual(SleepGrade.letterFrom(score: 97),   "A+")
        XCTAssertEqual(SleepGrade.letterFrom(score: 96),   "A")
        XCTAssertEqual(SleepGrade.letterFrom(score: 93),   "A")
        XCTAssertEqual(SleepGrade.letterFrom(score: 92),   "A-")
        XCTAssertEqual(SleepGrade.letterFrom(score: 90),   "A-")
        XCTAssertEqual(SleepGrade.letterFrom(score: 89),   "B+")
        XCTAssertEqual(SleepGrade.letterFrom(score: 87),   "B+")
        XCTAssertEqual(SleepGrade.letterFrom(score: 86),   "B")
        XCTAssertEqual(SleepGrade.letterFrom(score: 83),   "B")
        XCTAssertEqual(SleepGrade.letterFrom(score: 82),   "B-")
        XCTAssertEqual(SleepGrade.letterFrom(score: 80),   "B-")
        XCTAssertEqual(SleepGrade.letterFrom(score: 79),   "C+")
        XCTAssertEqual(SleepGrade.letterFrom(score: 77),   "C+")
        XCTAssertEqual(SleepGrade.letterFrom(score: 76),   "C")
        XCTAssertEqual(SleepGrade.letterFrom(score: 73),   "C")
        XCTAssertEqual(SleepGrade.letterFrom(score: 72),   "C-")
        XCTAssertEqual(SleepGrade.letterFrom(score: 70),   "C-")
        XCTAssertEqual(SleepGrade.letterFrom(score: 69),   "D+")
        XCTAssertEqual(SleepGrade.letterFrom(score: 67),   "D+")
        XCTAssertEqual(SleepGrade.letterFrom(score: 66),   "D")
        XCTAssertEqual(SleepGrade.letterFrom(score: 63),   "D")
        XCTAssertEqual(SleepGrade.letterFrom(score: 62),   "D-")
        XCTAssertEqual(SleepGrade.letterFrom(score: 0),    "D-")
    }

    // MARK: - Grade XP bonus

    func testGradeXPBonus() {
        let makeGrade: (String) -> SleepGrade = { letter in
            SleepGrade(letter: letter, qualitativeLabel: "Test", score: 80,
                       isPartial: false,
                       components: SleepGrade.GradeComponents(
                           durationScore: 80, stageQualityScore: nil,
                           awakeTimeScore: 80, consistencyScore: 80))
        }
        XCTAssertEqual(makeGrade("A+").gradeXPBonus, 20)
        XCTAssertEqual(makeGrade("A").gradeXPBonus,  20)
        XCTAssertEqual(makeGrade("A-").gradeXPBonus, 15)
        XCTAssertEqual(makeGrade("B+").gradeXPBonus, 15)
        XCTAssertEqual(makeGrade("B").gradeXPBonus,  10)
        XCTAssertEqual(makeGrade("B-").gradeXPBonus, 10)
        XCTAssertEqual(makeGrade("C+").gradeXPBonus,  5)
        XCTAssertEqual(makeGrade("C").gradeXPBonus,   5)
        XCTAssertEqual(makeGrade("C-").gradeXPBonus,  0)
        XCTAssertEqual(makeGrade("D+").gradeXPBonus,  0)
        XCTAssertEqual(makeGrade("D").gradeXPBonus,   0)
        XCTAssertEqual(makeGrade("D-").gradeXPBonus,  0)
    }

    // MARK: - Environment rank level

    func testEnvironmentRankLevel() {
        var p = DreamerProfile.default
        p.sleepRank = 4
        p.dreamRank = 2
        XCTAssertEqual(p.environmentRankLevel, 4)

        p.sleepRank = 1
        p.dreamRank = 6
        XCTAssertEqual(p.environmentRankLevel, 6)

        p.sleepRank = 3
        p.dreamRank = 3
        XCTAssertEqual(p.environmentRankLevel, 3)
    }

    // MARK: - Dream entry richness thresholds

    func testDreamEntryRichEntry() {
        // Not rich (< 100 chars)
        let short = DreamEntry(date: Date(), narrative: "Short note")
        XCTAssertFalse(short.isRichEntry)
        XCTAssertFalse(short.hasNarrative)

        // hasNarrative but not isRichEntry (100–499 chars)
        let medium = DreamEntry(date: Date(), narrative: String(repeating: "x", count: 100))
        XCTAssertTrue(medium.hasNarrative)
        XCTAssertFalse(medium.isRichEntry)

        // isRichEntry (>= 500 chars)
        let rich = DreamEntry(date: Date(), narrative: String(repeating: "x", count: 500))
        XCTAssertTrue(rich.hasNarrative)
        XCTAssertTrue(rich.isRichEntry)

        // Nil narrative
        let noNarrative = DreamEntry(date: Date())
        XCTAssertFalse(noNarrative.hasNarrative)
        XCTAssertFalse(noNarrative.isRichEntry)
    }

    // MARK: - Sleep titles

    func testSleepTitles() {
        XCTAssertEqual(DreamerProfile.sleepTitles.count, 6)
        XCTAssertEqual(DreamerProfile.sleepTitles[0], "Novice Snoozer")
        XCTAssertEqual(DreamerProfile.sleepTitles[1], "Steady Sleeper")
        XCTAssertEqual(DreamerProfile.sleepTitles[2], "Restful Soul")
        XCTAssertEqual(DreamerProfile.sleepTitles[3], "Sleep Sage")
        XCTAssertEqual(DreamerProfile.sleepTitles[4], "Slumber Architect")
        XCTAssertEqual(DreamerProfile.sleepTitles[5], "Master of Rest")
    }

    // MARK: - Dream titles

    func testDreamTitles() {
        XCTAssertEqual(DreamerProfile.dreamTitles.count, 6)
        XCTAssertEqual(DreamerProfile.dreamTitles[0], "Dreamer Initiate")
        XCTAssertEqual(DreamerProfile.dreamTitles[1], "Dream Seeker")
        XCTAssertEqual(DreamerProfile.dreamTitles[2], "Lucid Novice")
        XCTAssertEqual(DreamerProfile.dreamTitles[3], "Lucid Voyager")
        XCTAssertEqual(DreamerProfile.dreamTitles[4], "Astral Adept")
        XCTAssertEqual(DreamerProfile.dreamTitles[5], "Dream Sovereign")
    }
}
