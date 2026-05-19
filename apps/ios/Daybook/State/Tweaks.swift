import SwiftUI

// Tweaks — the runtime knobs that drive Regis's halo, room atmosphere, particles.
// Mirrors window.TWEAK_DEFAULTS in Daybook.html.

enum TimeOfDay: String, CaseIterable { case dawn, day, dusk, night }
enum RegisMood: String, CaseIterable { case calm, curious, concerned }
enum RegisForm: String, CaseIterable { case png, orb }

@Observable
final class Tweaks {
    var timeOfDay: TimeOfDay = .day
    var inkHue: Double = 256          // 200..300 — currently used as a "warmth bias" since we're in RGB
    var glassIntensity: Double = 1.0  // 0.4..1.6
    var particles: Bool = true
    var mood: RegisMood = .calm
    var regisForm: RegisForm = .png

    // Live HRV simulator — drifts slowly so Regis's halo modulates. 1.0 baseline.
    var hrv: Double = 1.0

    // Last proactive ping surfaced by Regis on Now.
    var proactivePing: String? = nil

    // Per-mood constants — mirrors REGIS_MOODS in regis.jsx
    var moodSpec: MoodSpec {
        switch mood {
        case .calm:      return MoodSpec(hue: 65, breathSec: 5.2, pulseSec: 3.2, satBoost: 0)
        case .curious:   return MoodSpec(hue: 55, breathSec: 4.2, pulseSec: 2.4, satBoost: 0.04)
        case .concerned: return MoodSpec(hue: 35, breathSec: 6.2, pulseSec: 4.2, satBoost: -0.02)
        }
    }

    // Time-of-day visual spec — mirrors TIME_BG in app.jsx
    var timeSpec: TimeSpec {
        switch timeOfDay {
        case .dawn:  return TimeSpec(spill: 0.40, warmHue: 40)
        case .day:   return TimeSpec(spill: 0.22, warmHue: 60)
        case .dusk:  return TimeSpec(spill: 0.50, warmHue: 30)
        case .night: return TimeSpec(spill: 0.30, warmHue: 55)
        }
    }
}

struct MoodSpec {
    var hue: Double            // not directly used for SwiftUI Color, but kept for parity
    var breathSec: Double
    var pulseSec: Double
    var satBoost: Double
}

struct TimeSpec {
    var spill: Double          // 0..1 intensity of warm bleed from where Regis sits
    var warmHue: Double        // amber direction (parity with css)
}

// Proactive pings — empty until the empath substrate has real signal.
let NOW_PINGS: [String] = []
