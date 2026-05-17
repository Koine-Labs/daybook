import HealthKit

/// App-level representation of Apple's sleep stage categories.
/// Maps from `HKCategoryValueSleepAnalysis` raw values.
nonisolated enum SleepStage: String, Codable, Sendable {
    case awake
    case remSleep
    case coreLight
    case deepSleep
    case inBed
    case unknown

    /// Initialize from an `HKCategoryValueSleepAnalysis` raw integer value.
    init(from hkValue: Int) {
        switch hkValue {
        case HKCategoryValueSleepAnalysis.awake.rawValue:
            self = .awake
        case HKCategoryValueSleepAnalysis.asleepREM.rawValue:
            self = .remSleep
        case HKCategoryValueSleepAnalysis.asleepCore.rawValue:
            self = .coreLight
        case HKCategoryValueSleepAnalysis.asleepDeep.rawValue:
            self = .deepSleep
        case HKCategoryValueSleepAnalysis.inBed.rawValue:
            self = .inBed
        default:
            self = .unknown
        }
    }
}
