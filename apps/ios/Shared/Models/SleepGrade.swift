import Foundation

struct SleepGrade: Codable, Sendable {
    let letter: String
    let qualitativeLabel: String
    let score: Double  // 0-100
    let isPartial: Bool
    let components: GradeComponents

    struct GradeComponents: Codable, Sendable {
        let durationScore: Double
        let stageQualityScore: Double?
        let awakeTimeScore: Double
        let consistencyScore: Double
    }

    static func letterFrom(score: Double) -> String {
        switch score {
        case 97...100: return "A+"
        case 93..<97: return "A"
        case 90..<93: return "A-"
        case 87..<90: return "B+"
        case 83..<87: return "B"
        case 80..<83: return "B-"
        case 77..<80: return "C+"
        case 73..<77: return "C"
        case 70..<73: return "C-"
        case 67..<70: return "D+"
        case 63..<67: return "D"
        default: return "D-"
        }
    }

    var gradeXPBonus: Int {
        switch letter {
        case "A+", "A": return 20
        case "A-", "B+": return 15
        case "B", "B-": return 10
        case "C+", "C": return 5
        default: return 0
        }
    }
}
