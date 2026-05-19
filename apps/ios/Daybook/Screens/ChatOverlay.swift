import SwiftUI

// ChatOverlay — "Talking to Regis" modal sheet. Voice orb + live waveform OR text input.

enum ChatMode { case voice, text }

struct ChatTurn: Identifiable, Equatable {
    enum Speaker { case regis, you }
    let id = UUID()
    var from: Speaker
    var text: String
}

struct ChatOverlay: View {
    var tweaks: Tweaks
    var onClose: () -> Void

    @Environment(AppState.self) private var appState

    @State private var mode: ChatMode = .voice
    @State private var draft: String = ""
    @State private var transcript: [ChatTurn] = [ChatTurn(from: .regis, text: "i'm here. what's on you?")]
    @State private var thinking: Bool = false
    @State private var inflight: Task<Void, Never>? = nil
    @FocusState private var textFocused: Bool

    private let suggestionsEarly = ["why am i tired?", "plan my day", "what's iris's birthday again?"]
    private let suggestionsLate = ["tell me more", "remind me later", "nevermind"]

    private var suggestions: [String] {
        transcript.count <= 1 ? suggestionsEarly : suggestionsLate
    }

    var body: some View {
        ZStack {
            backdrop
            VStack(spacing: 0) {
                topBar
                orbHeader
                transcriptArea
                suggestionStrip
                inputArea
            }
        }
        .transition(.opacity)
    }

    // MARK: - Layout pieces (split out so the type checker can keep up)

    private var backdrop: some View {
        Rectangle()
            .fill(.ultraThinMaterial)
            .ignoresSafeArea()
            .overlay(Color(red: 6/255.0, green: 8/255.0, blue: 16/255.0).opacity(0.55))
    }

    private var topBar: some View {
        HStack {
            Button(action: onClose) {
                Text("← back").font(Fonts.body(13)).foregroundStyle(Theme.pearlFaint)
            }
            .buttonStyle(.plain)
            Spacer()
            Text("listening").labelMono()
            Spacer()
            Button(action: { mode = (mode == .voice ? .text : .voice) }) {
                Text(mode == .voice ? "type" : "talk")
                    .font(Fonts.body(13))
                    .foregroundStyle(Theme.pearlFaint)
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 22)
        .padding(.top, 14)
        .frame(height: 60)
    }

    private var orbHeader: some View {
        VStack {
            VoiceOrb(listening: mode == .voice, mood: tweaks.mood, hrv: tweaks.hrv)
        }
        .padding(.top, 14)
        .padding(.bottom, 18)
    }

    private var transcriptArea: some View {
        ScrollViewReader { proxy in
            ScrollView(showsIndicators: false) {
                LazyVStack(alignment: .leading, spacing: 0) {
                    ForEach(transcript) { t in
                        TurnView(turn: t).id(t.id)
                    }
                    if thinking {
                        ThinkingDots().id("thinking")
                    }
                }
                .padding(.horizontal, 28)
                .padding(.bottom, 14)
            }
            .onChange(of: transcript) { _, _ in
                if let last = transcript.last {
                    withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                }
            }
            .onChange(of: thinking) { _, isThinking in
                if isThinking { withAnimation { proxy.scrollTo("thinking", anchor: .bottom) } }
            }
        }
    }

    private var suggestionStrip: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(suggestions, id: \.self) { s in
                    SuggestionChip(text: s) { send(s) }
                }
            }
            .padding(.horizontal, 22)
        }
        .padding(.bottom, 12)
    }

    private var inputArea: some View {
        Group {
            if mode == .voice { voiceInput } else { textInput }
        }
        .padding(.horizontal, 22)
        .padding(.vertical, 14)
        .overlay(alignment: .top) {
            Rectangle().fill(Theme.pearl.opacity(0.06)).frame(height: 0.5)
        }
        .padding(.bottom, 14)
    }

    private var voiceInput: some View {
        HStack(spacing: 14) {
            Circle()
                .fill(Theme.amber)
                .frame(width: 10, height: 10)
                .shadow(color: Theme.amberGlow, radius: 6, x: 0, y: 0)
            LiveWaveform(active: true)
                .frame(maxWidth: .infinity)
            Button(action: { send("i'm a bit tired honestly") }) {
                Text("send sample")
                    .font(Fonts.body(12))
                    .foregroundStyle(Theme.pearlDim)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(Capsule().fill(Theme.pearl.opacity(0.06)))
                    .overlay(Capsule().strokeBorder(Theme.pearl.opacity(0.1), lineWidth: 0.5))
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 12)
        .background(
            Capsule().fill(Theme.amber.opacity(0.06))
        )
        .overlay(
            Capsule().strokeBorder(Theme.amber.opacity(0.22), lineWidth: 0.5)
        )
        .shadow(color: Theme.amberGlow.opacity(0.15), radius: 12, x: 0, y: 0)
    }

    private var textInput: some View {
        HStack(spacing: 10) {
            TextField("say anything to regis", text: $draft)
                .font(Fonts.body(15))
                .foregroundStyle(Theme.pearl)
                .focused($textFocused)
                .submitLabel(.send)
                .onSubmit { send(draft) }
                .padding(.leading, 18)
                .padding(.vertical, 8)
            Button(action: { send(draft) }) {
                ZStack {
                    Circle()
                        .fill(
                            draft.trimmingCharacters(in: .whitespaces).isEmpty
                            ? AnyShapeStyle(Theme.pearl.opacity(0.08))
                            : AnyShapeStyle(RadialGradient(
                                colors: [Color(red: 1.0, green: 246/255.0, blue: 226/255.0), Theme.amberDeep],
                                center: UnitPoint(x: 0.38, y: 0.32),
                                startRadius: 0, endRadius: 22
                            ))
                        )
                        .frame(width: 38, height: 38)
                        .shadow(color: draft.isEmpty ? .clear : Theme.amberGlow, radius: 7, x: 0, y: 0)
                    Text("↑")
                        .font(Fonts.body(18, .semibold))
                        .foregroundStyle(Theme.bgBase)
                }
            }
            .buttonStyle(.plain)
            .disabled(draft.trimmingCharacters(in: .whitespaces).isEmpty)
            .padding(6)
        }
        .background(
            Capsule().fill(Theme.pearl.opacity(0.05))
        )
        .overlay(
            Capsule().strokeBorder(Theme.pearl.opacity(0.14), lineWidth: 0.5)
        )
        .onAppear { textFocused = true }
    }

    private func send(_ raw: String) {
        let text = raw.trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else { return }
        transcript.append(ChatTurn(from: .you, text: text))
        draft = ""
        thinking = true

        // Cancel any pre-existing inflight request so back-to-back sends don't
        // race each other.
        inflight?.cancel()
        let convId = appState.conversationId
        inflight = Task { @MainActor in
            do {
                let reply = try await APIClient.shared.chat(
                    message: text,
                    conversationId: convId
                )
                guard !Task.isCancelled else { return }
                appState.conversationId = reply.conversationId
                thinking = false
                transcript.append(ChatTurn(from: .regis, text: reply.text))
            } catch {
                guard !Task.isCancelled else { return }
                thinking = false
                let fallback = localFallbackReply(text)
                let note = (error as? APIClient.APIError)?.userFacing ?? "couldn't reach mac"
                transcript.append(ChatTurn(
                    from: .regis,
                    text: "\(fallback)\n\n[offline · \(note)]"
                ))
            }
        }
    }
}

// MARK: - SuggestionChip

struct SuggestionChip: View {
    var text: String
    var action: () -> Void
    var body: some View {
        Button(action: action) {
            Text(text)
                .font(Fonts.body(13))
                .foregroundStyle(Theme.pearlDim)
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
                .background(Capsule().fill(Theme.pearl.opacity(0.05)))
                .overlay(Capsule().strokeBorder(Theme.pearl.opacity(0.12), lineWidth: 0.5))
        }
        .buttonStyle(.plain)
    }
}

// MARK: - VoiceOrb (Regis + expanding listening rings)

struct VoiceOrb: View {
    var listening: Bool
    var mood: RegisMood
    var hrv: Double
    @State private var ring1 = false
    @State private var ring2 = false

    var body: some View {
        ZStack {
            if listening {
                Circle()
                    .strokeBorder(Color(red: 1.0, green: 200/255.0, blue: 140/255.0).opacity(0.35), lineWidth: 0.5)
                    .frame(width: 200, height: 200)
                    .scaleEffect(ring1 ? 1.08 : 1.0)
                    .opacity(ring1 ? 0.78 : 1.0)
                    .animation(.easeInOut(duration: 2.2).repeatForever(autoreverses: true), value: ring1)
                Circle()
                    .strokeBorder(Color(red: 1.0, green: 200/255.0, blue: 140/255.0).opacity(0.18), lineWidth: 0.5)
                    .frame(width: 240, height: 240)
                    .scaleEffect(ring2 ? 1.08 : 1.0)
                    .opacity(ring2 ? 0.78 : 1.0)
                    .animation(.easeInOut(duration: 2.8).delay(0.3).repeatForever(autoreverses: true), value: ring2)
            }
            RegisView(size: 170, mood: mood, hrv: hrv, form: .png)
        }
        .frame(width: 240, height: 240)
        .onAppear { ring1 = true; ring2 = true }
    }
}

// MARK: - LiveWaveform

struct LiveWaveform: View {
    var active: Bool
    private let bars = 32

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0/30.0, paused: !active)) { ctx in
            waveformBody(t: ctx.date.timeIntervalSinceReferenceDate)
        }
    }

    private func waveformBody(t: Double) -> some View {
        HStack(alignment: .center, spacing: 4) {
            ForEach(0..<bars, id: \.self) { i in
                WaveformBar(active: active, height: barHeight(i: i, t: t), color: barColor(i: i))
            }
        }
        .frame(height: 44, alignment: .center)
    }

    private func barHeight(i: Int, t: Double) -> CGFloat {
        let seed = sin(Double(i) * 7.31) * 0.5 + 0.5
        let phase = (sin(t * 5 + Double(i) * 0.6) * 0.5 + 0.5)
        return active ? CGFloat(6 + (seed * 0.5 + phase * 0.5) * 28) : 4
    }

    private func barColor(i: Int) -> Color {
        let seed = sin(Double(i) * 7.31) * 0.5 + 0.5
        if active {
            return Color(red: 1.0, green: 200/255.0, blue: 120/255.0).opacity(0.55 + seed * 0.45)
        }
        return Theme.pearl.opacity(0.15)
    }
}

private struct WaveformBar: View {
    var active: Bool
    var height: CGFloat
    var color: Color
    var body: some View {
        Capsule()
            .fill(color)
            .frame(width: 3, height: height)
    }
}

// MARK: - Turn view

struct TurnView: View {
    var turn: ChatTurn
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if turn.from == .regis {
                Text("regis")
                    .labelTiny(Color(red: 1.0, green: 200/255.0, blue: 140/255.0).opacity(0.6))
            } else {
                Text("you").labelTiny(Theme.pearl.opacity(0.5))
            }
            if turn.from == .regis {
                Text(turn.text)
                    .font(Fonts.quote(19))
                    .lineSpacing(6)
                    .foregroundStyle(Theme.amberReply)
            } else {
                Text(turn.text)
                    .font(Fonts.body(17))
                    .lineSpacing(4)
                    .foregroundStyle(Theme.pearlDim)
            }
        }
        .padding(.vertical, 8)
    }
}

// MARK: - Thinking dots

struct ThinkingDots: View {
    @State private var animate = false
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("regis").labelTiny(Color(red: 1.0, green: 200/255.0, blue: 140/255.0).opacity(0.6))
            HStack(spacing: 5) {
                ForEach(0..<3, id: \.self) { i in
                    Circle()
                        .fill(Color(red: 1.0, green: 200/255.0, blue: 140/255.0).opacity(animate ? 1.0 : 0.55))
                        .frame(width: 5, height: 5)
                        .animation(.easeInOut(duration: 1.2).repeatForever(autoreverses: true).delay(Double(i) * 0.2), value: animate)
                }
            }
            .frame(height: 18, alignment: .leading)
        }
        .padding(.vertical, 8)
        .onAppear { animate = true }
    }
}

// MARK: - Offline fallback reply
//
// Kept around (renamed from `pickReply`) as a graceful degradation when the
// Mac-side Regis (FastAPI bridge) is unreachable. The live chat path calls
// the API; only when that throws does the overlay fall back to these canned
// regex replies plus a small "[offline]" annotation.

func localFallbackReply(_ input: String) -> String {
    let t = input.lowercased()
    if t.range(of: "tired|exhaust|drain", options: .regularExpression) != nil {
        return "yeah, your hrv's been soft since saturday. nothing dramatic — just a debt building. fewer hard things today?"
    }
    if t.range(of: "plan|day|schedule", options: .regularExpression) != nil {
        return "morning's clear til standup. i'd put the writing in there while you're still quiet inside. after lunch you'll be more social — save the calls for then."
    }
    if t.contains("iris") {
        return "march eleventh. and last year you forgot until the night before — i can nudge you a week out this time."
    }
    if t.range(of: "why|how|what", options: .regularExpression) != nil {
        return "give me a beat. i'm thinking about it."
    }
    if t.range(of: "no|never|nope|nvm", options: .regularExpression) != nil {
        return "okay. i'm here whenever."
    }
    if t.range(of: "more|tell", options: .regularExpression) != nil {
        return "monday and tuesday you slept less than seven. thursday you skipped dinner. friday your shoulders. it's small things stacked."
    }
    return "i hear you. let me sit with that for a second."
}
