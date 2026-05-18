import SwiftUI

// ChatView — port of ScreenChat from screens-companion.jsx.
// Placeholder thread + canned auto-reply. Once apps/api/ ships, wire the input
// path through APIClient.post("/chat") and the thread via APIClient.get("/chat/history").
struct ChatView: View {
    @Environment(AppState.self) private var appState
    @Environment(Theme.self) private var theme

    enum Speaker: Hashable {
        case meta
        case me
        case regis
        case observation
    }

    struct Message: Identifiable, Hashable {
        let id = UUID()
        let who: Speaker
        let text: String
    }

    // Real conversation thread — starts empty for a new user.
    // TODO: wire to APIClient.get("/chat/conversations/{id}/messages")
    @State private var thread: [Message] = []

    @State private var input: String = ""
    @State private var composing: Bool = false
    @FocusState private var inputFocused: Bool

    // No canned replies. When the user sends, we'd hit the real backend.
    // For now (until APIClient.post is wired), the message goes through as
    // a user-only turn — Regis stays silent until you connect him to the API.
    // TODO: wire to APIClient.post("/chat/conversations/{id}/messages")

    var body: some View {
        ZStack {
            theme.bg.ignoresSafeArea()

            VStack(spacing: 0) {
                header
                thread_view
                inputBar
            }
        }
    }

    // MARK: - Header
    //
    // Combines: identity strip (wisp + Regis + state) + current empathic read
    // (the "line" — what NowView used to lead with, now lives as a chat header)
    // + WispProfileBtn (Settings entry).

    // Empathic read line — derived from sensor state once /state/stream is wired.
    // For now: empty (honest — Regis has no data yet for a brand-new user).
    // TODO: subscribe to GET /state/stream SSE → derive line from latest
    //       user_state_estimate. Until then, show nothing rather than fake.
    private let empathicLine: String? = nil

    private var header: some View {
        VStack(alignment: .leading, spacing: 14) {
            // Identity strip — the wisp lives in the WispAgentLayer overlay;
            // here we just reserve space for it via an anchor.
            HStack(alignment: .center) {
                HStack(alignment: .center, spacing: 10) {
                    // Invisible anchor — wisp drifts here in idle / dormant.
                    Color.clear
                        .frame(width: 42, height: 42)
                        .wispAnchor(.headerLeft, active: !composing && !inputFocused)

                    VStack(alignment: .leading, spacing: 3) {
                        Text("Regis")
                            .font(DBFont.serif(20))
                            .foregroundStyle(theme.ink)
                        Text(composing ? "composing" : "present · dry today")
                            .dbMeta(composing ? theme.amber : theme.ink3)
                    }
                }
                Spacer()
                // Settings tap target — small static mark, NOT the agent.
                Button {
                    appState.settingsOpen = true
                } label: {
                    WispMark(size: 14, mode: theme.mode)
                        .frame(width: 36, height: 36)
                        .contentShape(Circle())
                }
                .buttonStyle(.plain)
            }

            // The line — Regis's current read of you. Italic serif warm.
            // Only shown when there's something real to say (sensor-derived).
            if let line = empathicLine {
                Text("\u{201C}\(line)\u{201D}")
                    .regisVoice(theme.voice, size: 17)
                    .fixedSize(horizontal: false, vertical: true)
                    .multilineTextAlignment(.leading)
                    .padding(.leading, 36)
                    .padding(.trailing, 4)
            }
        }
        .padding(.horizontal, 22)
        .padding(.top, 54)
        .padding(.bottom, 14)
        .overlay(alignment: .bottom) {
            Rectangle().fill(theme.edge).frame(height: 0.5)
        }
    }

    // MARK: - Thread

    private var thread_view: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 14) {
                    if thread.isEmpty && !composing {
                        emptyChatState
                            .frame(maxWidth: .infinity)
                            .padding(.top, 80)
                            .padding(.bottom, 40)
                    } else {
                        ForEach(thread) { message in
                            bubble(for: message)
                                .id(message.id)
                                // The most recent message becomes a wisp target
                                .wispAnchor(.latestMessage, active: message.id == thread.last?.id)
                        }
                    }
                    if composing {
                        composingIndicator
                            .id("composing")
                    }
                }
                .padding(.horizontal, 22)
                .padding(.top, 18)
                .padding(.bottom, 14)
            }
            .onChange(of: thread) { _, _ in
                if let last = thread.last {
                    withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                }
            }
            .onChange(of: composing) { _, isComposing in
                if isComposing {
                    withAnimation { proxy.scrollTo("composing", anchor: .bottom) }
                }
            }
        }
    }

    // Empty state — what a brand-new user sees. No fake messages.
    // The wisp is wandering around the screen via the WispAgentLayer; here
    // we just provide the quiet space.
    private var emptyChatState: some View {
        VStack(spacing: 18) {
            Text("nothing yet between us.")
                .regisVoice(theme.voice, size: 17)
                .multilineTextAlignment(.center)
                .opacity(0.75)
            Text("say something, or just sit.\nhe's getting to know you.")
                .font(.system(size: 13))
                .foregroundStyle(theme.ink3)
                .multilineTextAlignment(.center)
                .lineSpacing(4)
        }
        .padding(.horizontal, 32)
    }

    @ViewBuilder
    private func bubble(for message: Message) -> some View {
        switch message.who {
        case .meta:
            HStack {
                Spacer()
                Text(message.text)
                    .dbMeta(theme.ink3)
                Spacer()
            }
            .padding(.vertical, 6)
        case .me:
            HStack {
                Spacer(minLength: 0)
                Text(message.text)
                    .font(DBFont.sans(15))
                    .foregroundStyle(theme.ink)
                    .lineSpacing(15 * 0.35)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    .background(
                        UnevenRoundedRectangle(
                            cornerRadii: .init(
                                topLeading: 18,
                                bottomLeading: 18,
                                bottomTrailing: 6,
                                topTrailing: 18
                            ),
                            style: .continuous
                        )
                        .fill(Color.black.opacity(0.06))
                    )
                    .frame(maxWidth: .infinity * 0.78, alignment: .trailing)
            }
        case .regis:
            HStack(alignment: .top, spacing: 8) {
                WispMark(size: 14, mode: theme.mode)
                    .padding(.top, 4)
                RegisQuote(message.text, size: 19)
                Spacer(minLength: 0)
            }
            .padding(.trailing, 30)
        case .observation:
            HStack {
                Text("regis · noticed")
                    .dbMeta(theme.ink2)
                Spacer()
                Text(message.text)
                    .font(DBFont.mono(11))
                    .tracking(0.55)
                    .foregroundStyle(theme.ink2)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .background(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(theme.amber.opacity(0.05))
                    .overlay(
                        RoundedRectangle(cornerRadius: 12, style: .continuous)
                            .strokeBorder(
                                theme.amber,
                                style: StrokeStyle(lineWidth: 0.5, dash: [3, 3])
                            )
                    )
            )
            .padding(.vertical, 4)
        }
    }

    private var composingIndicator: some View {
        HStack(spacing: 8) {
            WispMark(size: 14, mode: theme.mode)
            HStack(spacing: 3) {
                ForEach(0..<3) { i in
                    Circle()
                        .fill(theme.amber)
                        .frame(width: 5, height: 5)
                        .opacity(composing ? 1.0 : 0.6)
                        .animation(
                            .easeInOut(duration: 0.45)
                                .repeatForever(autoreverses: true)
                                .delay(Double(i) * 0.18),
                            value: composing
                        )
                }
            }
            Spacer(minLength: 0)
        }
    }

    // MARK: - Input bar

    private var inputBar: some View {
        HStack(spacing: 8) {
            // Anchor above the input bar — when the user focuses the input
            // OR Regis is composing, the wisp drifts here.
            // (Rendered as an invisible row above the input.)
            TextField("say something", text: $input)
                .focused($inputFocused)
                .font(DBFont.sans(15))
                .foregroundStyle(theme.ink)
                .tint(theme.amber)
                .padding(.horizontal, 16)
                .padding(.vertical, 11)
                .background(
                    Capsule(style: .continuous)
                        .fill(theme.card)
                        .overlay(
                            Capsule(style: .continuous)
                                .stroke(theme.edge, lineWidth: 0.5)
                        )
                )
                .overlay(alignment: .top) {
                    // Wisp drifts to a point just above the input bar when active
                    Color.clear
                        .frame(width: 1, height: 1)
                        .offset(y: -38)
                        .wispAnchor(.inputComposing, active: composing || inputFocused)
                }
                .onSubmit(send)
                .submitLabel(.send)

            Button(action: send) {
                ZStack {
                    Circle()
                        .fill(input.trimmingCharacters(in: .whitespaces).isEmpty
                              ? Color.black.opacity(0.08)
                              : theme.amber)
                        .frame(width: 38, height: 38)
                    Image(systemName: "arrow.up")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(input.trimmingCharacters(in: .whitespaces).isEmpty
                                         ? theme.ink3
                                         : Color.white)
                }
            }
            .buttonStyle(.plain)
            .disabled(input.trimmingCharacters(in: .whitespaces).isEmpty)
        }
        .padding(.horizontal, 16)
        .padding(.top, 10)
        .padding(.bottom, 86)
        .background(theme.bg)
        .overlay(alignment: .top) {
            Rectangle().fill(theme.edge).frame(height: 0.5)
        }
    }

    // MARK: - Logic

    private func send() {
        let trimmed = input.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { return }
        thread.append(.init(who: .me, text: trimmed))
        input = ""
        // Once APIClient is wired, this is where we'd POST + await response.
        // For now: message lands in thread; Regis stays silent until connected.
    }
}

#Preview {
    let theme = Theme()
    return ChatView()
        .environment(theme)
}
