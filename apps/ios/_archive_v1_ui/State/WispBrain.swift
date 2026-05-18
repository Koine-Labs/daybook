import SwiftUI

// WispBrain — the wisp's local behavior policy.
//
// Runs every ~500ms (in the WispAgentLayer's TimelineView). Decides:
//   - Where to wander next
//   - How long to stay there
//   - When to drift to the edges (boredom)
//   - When to defer to user activity (touch, input focus, immersive screen)
//
// This is NOT the main Regis AI. This is a tiny local policy for the wisp's
// EMBODIED behavior. The main Regis AI runs in the FastAPI backend and pushes
// state events that the WispBrain reads as inputs (composing, observation,
// etc.) — but the body's decisions about where to go are made here, fast.
//
// State machine, not LLM. Tunable parameters; could later become a learned
// policy if behavior needs to adapt per-user.

@Observable
final class WispBrain {

    // MARK: - Registered targets

    /// Anchors currently visible on screen. WispBrain may visit any of these.
    var targets: [WispAnchor: TargetState] = [:]

    struct TargetState {
        var center: CGPoint
        var freshness: Double = 1.0  // 0-1; decays per visit, resets when content changes
        var lastVisit: Date?
    }

    // MARK: - Decision state

    /// The anchor the wisp is currently heading to / sitting at.
    var currentAnchor: WispAnchor?

    /// Time the wisp arrived at currentAnchor.
    var arrivedAt: Date = Date()

    /// Aggregated boredom (0-1) — higher = more likely to drift to edges.
    var boredomLevel: Double = 0

    // MARK: - Inputs (set by WispAgentLayer each tick)

    /// User is actively touching the screen → wisp defers to that.
    var userTouching: Bool = false

    /// User has focused a text input → wisp goes to it.
    var inputIsFocused: Bool = false

    /// Regis main AI is composing → wisp moves toward chat area, alert.
    var regisComposing: Bool = false

    // MARK: - Tuning

    /// How long the wisp lingers at a target before considering a new visit.
    /// Longer = more meditative, less jumpy. The wisp DRIFTS between targets
    /// (slow spring), so visit duration is the "settled hover" time.
    private let visitDuration: TimeInterval = 9.0

    /// Boredom threshold above which the wisp drifts to an edge.
    private let boredomThreshold: Double = 0.55

    /// Freshness decay per visit.
    private let freshnessDecay: Double = 0.30

    /// Freshness regen per second (boredom recovers slowly even without new content).
    private let freshnessRegenPerSecond: Double = 0.010

    // MARK: - Public API

    /// Called by WispAgentLayer each frame with the current anchors discovered
    /// via preference key. New anchors get registered fresh; existing ones
    /// update their center.
    func updateAnchors(_ entries: [WispAnchorEntry], screenSize: CGSize) {
        // Update / insert visible anchors
        var seen: Set<WispAnchor> = []
        for entry in entries where entry.anchor != .hidden {
            seen.insert(entry.anchor)
            if var existing = targets[entry.anchor] {
                existing.center = CGPoint(x: entry.frame.midX, y: entry.frame.midY)
                targets[entry.anchor] = existing
            } else {
                targets[entry.anchor] = TargetState(
                    center: CGPoint(x: entry.frame.midX, y: entry.frame.midY),
                    freshness: 1.0
                )
            }
        }

        // Add synthetic edge anchors (always available for boredom drift)
        for edge in WispAnchor.edgeAnchors where !seen.contains(edge) {
            let pad: CGFloat = 30
            let pt: CGPoint = {
                switch edge {
                case .edgeLeft:   return CGPoint(x: pad, y: screenSize.height * 0.4)
                case .edgeRight:  return CGPoint(x: screenSize.width - pad, y: screenSize.height * 0.4)
                case .edgeTop:    return CGPoint(x: screenSize.width * 0.5, y: 80)
                case .edgeBottom: return CGPoint(x: screenSize.width * 0.5, y: screenSize.height - 130)
                default:          return .zero
                }
            }()
            if var existing = targets[edge] {
                existing.center = pt
                targets[edge] = existing
            } else {
                targets[edge] = TargetState(center: pt, freshness: 1.0)
            }
        }

        // Drop anchors that disappeared (except edges)
        let alive = seen.union(WispAnchor.edgeAnchors)
        for key in targets.keys where !alive.contains(key) {
            targets[key] = nil
        }
    }

    /// Called every ~500ms by WispAgentLayer. May return a new anchor if
    /// the brain decided to move.
    func tick(now: Date) -> WispAnchor? {
        // Regenerate freshness slowly
        for (key, var state) in targets {
            state.freshness = min(1.0, state.freshness + freshnessRegenPerSecond * 0.5)
            targets[key] = state
        }

        // Priority 1: input focus → perch above input
        if inputIsFocused {
            return moveTo(.inputComposing)
        }

        // Priority 2: Regis composing → near latest message
        if regisComposing, targets[.latestMessage] != nil {
            return moveTo(.latestMessage)
        }

        // Priority 3: user touching → defer (WispAgentLayer handles follow directly)
        if userTouching {
            return nil
        }

        // Priority 4: time to move? Only after pausing at current target.
        let timeAtTarget = now.timeIntervalSince(arrivedAt)
        guard timeAtTarget >= visitDuration else { return nil }

        // Compute boredom from visible non-edge targets
        boredomLevel = computeBoredom()

        // Bored → drift to an edge
        if boredomLevel > boredomThreshold {
            let edge = pickEdge()
            return moveTo(edge)
        }

        // Otherwise → weighted random walk through interesting anchors
        let next = pickInterestingAnchor()
        return moveTo(next)
    }

    /// Reset freshness on the latest-message anchor when a new message arrives.
    func noteNewContent(at anchor: WispAnchor) {
        if var state = targets[anchor] {
            state.freshness = 1.0
            targets[anchor] = state
        }
    }

    // MARK: - Internals

    private func computeBoredom() -> Double {
        let interesting = targets.filter { entry in
            !WispAnchor.edgeAnchors.contains(entry.key) && entry.key.baseInterest > 0
        }
        guard !interesting.isEmpty else { return 1.0 }
        let avgFreshness = interesting.values.map(\.freshness).reduce(0, +) / Double(interesting.count)
        return 1.0 - avgFreshness
    }

    private func pickInterestingAnchor() -> WispAnchor {
        let candidates = targets.filter { entry in
            !WispAnchor.edgeAnchors.contains(entry.key) &&
            entry.key != currentAnchor &&
            entry.key.baseInterest > 0
        }
        guard !candidates.isEmpty else {
            // Fall back to edge wander if nothing else is around
            return pickEdge()
        }
        // Weight = baseInterest * freshness (avoiding stale stuff)
        let weighted: [(WispAnchor, Double)] = candidates.map { (key, state) in
            (key, key.baseInterest * state.freshness + 0.0001)
        }
        return weightedPick(weighted)
    }

    private func pickEdge() -> WispAnchor {
        let edges = WispAnchor.edgeAnchors.filter { $0 != currentAnchor }
        return edges.randomElement() ?? .edgeBottom
    }

    private func weightedPick(_ items: [(WispAnchor, Double)]) -> WispAnchor {
        let total = items.map(\.1).reduce(0, +)
        guard total > 0 else { return items.first?.0 ?? .headerLeft }
        let r = Double.random(in: 0..<total)
        var acc = 0.0
        for (anchor, weight) in items {
            acc += weight
            if r < acc { return anchor }
        }
        return items.last?.0 ?? .headerLeft
    }

    private func moveTo(_ anchor: WispAnchor) -> WispAnchor {
        currentAnchor = anchor
        arrivedAt = Date()
        if var state = targets[anchor] {
            state.freshness = max(0.0, state.freshness - freshnessDecay)
            state.lastVisit = Date()
            targets[anchor] = state
        }
        return anchor
    }
}
