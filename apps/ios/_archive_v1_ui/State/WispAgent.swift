import SwiftUI

// WispAgent — the wisp as an embodied agent in the app.
//
// Holds persistent state that survives tab switches, view re-renders, and
// transitions. The WispAgentLayer reads from this to render the wisp at the
// right place, in the right posture, doing the right thing.
//
// Architecture: screens declare WHERE the wisp should anchor for their
// context via the `.wispAnchor(.headerLeft)` view modifier. The anchor flows
// up via SwiftUI PreferenceKey to ContentView, which updates the agent.
// The wisp then animates smoothly to the new anchor.

@Observable
final class WispAgent {

    // MARK: - Position

    /// Where the wisp lives by default (current anchor center).
    var anchorPosition: CGPoint = CGPoint(x: 200, y: 200)

    /// Target rendering size.
    var targetSize: CGFloat = 28

    /// User's current finger position (set by DragGesture). When non-nil,
    /// the wisp follows the finger with a slight lag.
    var touchPosition: CGPoint? = nil

    /// Brief attention target — e.g., where a recent tap happened.
    /// Wisp pounces toward it for ~400ms, then returns to anchor.
    var attentionTarget: CGPoint? = nil
    var attentionExpires: Date = Date()

    /// Whether the wisp is hidden (e.g., during immersive screens that
    /// render their own wisp internally).
    var isHidden: Bool = false

    /// Last anchor change time (for tracking but no longer drives wander —
    /// wander is dead, intent is alive).
    var lastAnchorChange: Date = Date()

    /// Where the wisp APPEARS to be RIGHT NOW (smoothed each frame).
    /// The layer updates this; readers can use it for debugging or for
    /// other UI to react to wisp position.
    var livePosition: CGPoint = CGPoint(x: 200, y: 200)

    // MARK: - State (animation)

    /// Animation state — controls breath / ripple / eye behavior.
    var animationState: WispState = .dormant

    // MARK: - Posture (what the wisp is "doing")

    enum Posture: String, Sendable {
        case drifting     // ambient idle, gentle drift
        case alert        // attentive, eyes tracking
        case curious      // glancing toward something specific
        case approaching  // moving toward user (e.g., typing)
        case witnessing   // sleep cue / immersive
        case held         // post-receipt rest
    }

    var posture: Posture = .alert

    // MARK: - Gaze

    /// Optional gaze target — where the eyes look. nil = forward / centered.
    var gazeTarget: CGPoint? = nil

    // MARK: - Public moves

    /// Move the wisp's anchor — the default home it returns to when nothing
    /// else is grabbing its attention.
    func setAnchor(_ point: CGPoint, size: CGFloat? = nil, state: WispState? = nil, posture: Posture? = nil) {
        let movedFar = hypot(point.x - anchorPosition.x, point.y - anchorPosition.y) > 8
        anchorPosition = point
        if let size { targetSize = size }
        if let state { animationState = state }
        if let posture { self.posture = posture }
        if movedFar { lastAnchorChange = Date() }
    }

    func setHidden(_ hidden: Bool) {
        isHidden = hidden
    }

    /// Touch happened — wisp will follow finger while down, then return on release.
    func touchBegan(at point: CGPoint) {
        touchPosition = point
    }

    func touchMoved(to point: CGPoint) {
        touchPosition = point
    }

    func touchEnded() {
        // Convert end into a brief pounce-glance toward the release point,
        // then let it decay back to anchor.
        if let last = touchPosition {
            attentionTarget = last
            attentionExpires = Date().addingTimeInterval(0.5)
        }
        touchPosition = nil
    }

    /// Quick orient toward a UI moment (new message, observation, etc.) for
    /// ~500ms, then back to anchor.
    func pounce(at point: CGPoint, duration: TimeInterval = 0.5) {
        attentionTarget = point
        attentionExpires = Date().addingTimeInterval(duration)
    }

    /// Where the wisp wants to be RIGHT NOW given all the things competing
    /// for its attention. Priority: touch > attention pounce > anchor.
    func desiredPosition(now: Date) -> CGPoint {
        if let touch = touchPosition {
            // Sit a bit ABOVE the finger so user can see what they're touching.
            return CGPoint(x: touch.x, y: touch.y - 36)
        }
        if let attention = attentionTarget, now < attentionExpires {
            return attention
        }
        return anchorPosition
    }

    /// Where the wisp's EYES want to look. Eyes track ahead of the body.
    func gazeDirection(now: Date) -> CGPoint? {
        if let touch = touchPosition { return touch }
        if let attention = attentionTarget, now < attentionExpires { return attention }
        return nil
    }

    /// Transition into composing — the wisp's body indicates Regis thinking.
    func startComposing() {
        animationState = .composing
        posture = .alert
    }

    /// Return to dormant after composing.
    func endComposing() {
        animationState = .dormant
        posture = .drifting
    }
}
