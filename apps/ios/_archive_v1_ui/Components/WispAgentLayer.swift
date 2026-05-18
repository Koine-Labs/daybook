import SwiftUI

// WispAgentLayer — the wisp as a living creature in the app.
//
// Responsibilities:
//   • Collect ALL anchor declarations from the screen via PreferenceKey
//   • Feed them to WispBrain (the local behavior policy)
//   • Let WispBrain decide where to wander
//   • Render the wisp at the chosen position with snappy spring motion
//   • Capture touches non-destructively so the brain can react
//   • Continuous TimelineView so wisp is animated AND brain ticks regularly

struct WispAgentLayer<Content: View>: View {
    @ViewBuilder let content: () -> Content

    @Environment(WispAgent.self) private var agent
    @Environment(WispBrain.self) private var brain
    @Environment(Theme.self) private var theme

    @State private var lastBrainTick: Date = .distantPast

    var body: some View {
        GeometryReader { geo in
            content()
                .onPreferenceChange(WispAnchorKey.self) { entries in
                    // Defer state mutations to next runloop — SwiftUI doesn't
                    // allow @Observable updates during view update phase.
                    Task { @MainActor in
                        brain.updateAnchors(entries, screenSize: geo.size)
                        if brain.currentAnchor == nil, let first = entries.first(where: { $0.anchor != .hidden }) {
                            let pt = CGPoint(x: first.frame.midX, y: first.frame.midY)
                            agent.anchorPosition = pt
                        }
                        let anyHidden = entries.contains { $0.anchor == .hidden }
                        agent.setHidden(anyHidden)
                    }
                }
                // Global drag tracking — only fires on REAL drags (10+ pt).
                // Pure taps pass through to underlying buttons unchanged.
                // Touch-following the wisp on every tap was consuming button
                // taps despite `.simultaneousGesture`; raising the minimum
                // distance preserves clickability.
                .simultaneousGesture(
                    DragGesture(minimumDistance: 10)
                        .onChanged { value in
                            if agent.touchPosition == nil {
                                agent.touchBegan(at: value.location)
                            } else {
                                agent.touchMoved(to: value.location)
                            }
                            brain.userTouching = true
                        }
                        .onEnded { _ in
                            agent.touchEnded()
                            brain.userTouching = false
                        }
                )
                .overlay(alignment: .topLeading) {
                    if !agent.isHidden {
                        wispLayer(screenSize: geo.size)
                    }
                }
        }
    }

    @ViewBuilder
    private func wispLayer(screenSize: CGSize) -> some View {
        TimelineView(.animation(minimumInterval: 1.0 / 60.0)) { context in
            // Tick the brain every ~500ms (decisions are sparse — pick new anchor occasionally)
            let _ = tickBrainIfDue(now: context.date)

            // Continuous breath offset — wisp is ALWAYS gently drifting, even
            // when "at rest." Two overlapping sine waves so it never feels
            // mechanical. ±5pt amplitude reads as floating, not jitter.
            let t = context.date.timeIntervalSinceReferenceDate
            let breathX = sin(t * 0.55) * 4.5 + sin(t * 0.31) * 2.0
            let breathY = cos(t * 0.42) * 3.5 + sin(t * 0.27) * 1.8

            // Touch follow uses snappy physics; wandering uses very slow drift.
            // The .animation modifier picks based on what's driving liveTarget.
            let isFollowingTouch = agent.touchPosition != nil
            let baseTarget = liveTargetPosition()
            let liveTarget = CGPoint(
                x: baseTarget.x + breathX,
                y: baseTarget.y + breathY
            )
            let gaze = computeGazeOffset(now: context.date, body: liveTarget)

            WispView(
                size: anchorSize(),
                state: anchorState(),
                mode: theme.mode,
                gazeOffset: gaze
            )
            .position(liveTarget)
            .allowsHitTesting(false)
            // Slow critically-damped spring for wandering → floats between
            // anchors over ~2-3 seconds. Snappier spring for touch follow.
            .animation(
                isFollowingTouch
                    ? .spring(response: 0.35, dampingFraction: 0.85)
                    : .spring(response: 2.2, dampingFraction: 1.0),
                value: baseTarget
            )
            .animation(.easeInOut(duration: 0.6), value: agent.targetSize)
            .onAppear { agent.livePosition = liveTarget }
            .onChange(of: liveTarget) { _, newValue in
                agent.livePosition = newValue
            }
        }
    }

    @discardableResult
    private func tickBrainIfDue(now: Date) -> Int {
        guard now.timeIntervalSince(lastBrainTick) > 0.5 else { return 0 }
        lastBrainTick = now

        // Defer state mutations off the view-update phase. The TimelineView
        // is RENDERING; brain decisions and agent state changes must happen
        // on the next runloop or SwiftUI raises "modifying state during view
        // update" warnings (and may behave erratically at launch).
        Task { @MainActor in
            if let next = brain.tick(now: now), let state = brain.targets[next] {
                agent.setAnchor(
                    state.center,
                    size: next.defaultSize,
                    state: next.defaultAnimationState
                )
            }
        }
        return 1
    }

    private func liveTargetPosition() -> CGPoint {
        if let touch = agent.touchPosition {
            return CGPoint(x: touch.x, y: touch.y - 38)
        }
        return agent.anchorPosition
    }

    private func anchorSize() -> CGFloat {
        // Wisp is slightly bigger when following touch — feels engaged
        if agent.touchPosition != nil { return agent.targetSize + 4 }
        return agent.targetSize
    }

    private func anchorState() -> WispState {
        agent.animationState
    }

    private func computeGazeOffset(now: Date, body: CGPoint) -> CGSize {
        if let touch = agent.touchPosition {
            return offsetTowards(target: touch, from: body)
        }
        // Eye wander when idle so eyes never feel dead
        let t = now.timeIntervalSinceReferenceDate
        return CGSize(
            width: sin(t * 0.22) * 0.7,
            height: cos(t * 0.18 + 0.7) * 0.45
        )
    }

    private func offsetTowards(target: CGPoint, from body: CGPoint) -> CGSize {
        let dx = target.x - body.x
        let dy = target.y - body.y
        let dist = sqrt(dx*dx + dy*dy)
        guard dist > 0.001 else { return .zero }
        let max: CGFloat = 1.8
        let scale = min(max, dist * 0.04) / dist
        return CGSize(width: dx * scale, height: dy * scale)
    }
}
