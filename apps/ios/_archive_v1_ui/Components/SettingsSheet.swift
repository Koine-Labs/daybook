import SwiftUI

// SettingsSheet — half-sheet overlay opened from the WispProfileBtn (top-right
// of every non-immersive screen). Section nav at the top, content below.
// For v0, section content is stub rows; full population comes later.

enum SettingsSection: String, CaseIterable, Hashable {
    case persona
    case presence
    case devices
    case permissions
    case lab
    case dev
    case about

    var label: String {
        switch self {
        case .persona:     return "Regis · persona"
        case .presence:    return "Presence + voice"
        case .devices:     return "Devices"
        case .permissions: return "Permissions"
        case .lab:         return "Lab · advanced"
        case .dev:         return "Dev · triggers"
        case .about:       return "About"
        }
    }
}

struct SettingsSheet: View {
    @Environment(AppState.self) private var appState
    @Environment(Theme.self) private var theme

    @State private var section: SettingsSection = .persona

    var body: some View {
        ZStack(alignment: .bottom) {
            // Scrim
            Color.black.opacity(0.32)
                .ignoresSafeArea()
                .onTapGesture { close() }

            // Sheet
            VStack(spacing: 0) {
                // Drag handle
                RoundedRectangle(cornerRadius: 99)
                    .fill(Color.black.opacity(0.12))
                    .frame(width: 38, height: 4)
                    .padding(.top, 14)
                    .padding(.bottom, 14)

                // Head
                HStack(alignment: .center) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("SETTINGS")
                            .dbEyebrow(theme.ink3)
                        Text("The dials.")
                            .font(.custom("Charter", size: 28))
                            .foregroundStyle(theme.ink)
                    }
                    Spacer()
                    Button("done") { close() }
                        .font(.custom("Charter-Italic", size: 14).italic())
                        .foregroundStyle(theme.ink2)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 6)
                        .background(Color.black.opacity(0.05))
                        .clipShape(Capsule())
                }
                .padding(.horizontal, 22)
                .padding(.bottom, 12)

                // Section pill nav
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        ForEach(SettingsSection.allCases, id: \.self) { s in
                            sectionPill(s)
                        }
                    }
                    .padding(.horizontal, 22)
                }
                .padding(.bottom, 12)

                // Section content
                ScrollView(.vertical, showsIndicators: false) {
                    sectionContent
                        .padding(.horizontal, 22)
                        .padding(.bottom, 40)
                }
            }
            .frame(maxWidth: .infinity)
            .frame(height: UIScreen.main.bounds.height * 0.84)
            .background(theme.bg)
            .clipShape(.rect(topLeadingRadius: 22, topTrailingRadius: 22))
            .shadow(color: .black.opacity(0.18), radius: 60, x: 0, y: -16)
            .transition(.move(edge: .bottom))
        }
    }

    private func close() {
        appState.settingsOpen = false
    }

    @ViewBuilder
    private func sectionPill(_ s: SettingsSection) -> some View {
        let isActive = section == s
        Button { section = s } label: {
            Text(s.label)
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(isActive ? theme.bg : theme.ink2)
                .padding(.horizontal, 13)
                .padding(.vertical, 7)
                .background(isActive ? theme.ink : Color.clear)
                .clipShape(Capsule())
        }
        .buttonStyle(.plain)
    }

    @ViewBuilder
    private var sectionContent: some View {
        switch section {
        case .persona:     PersonaSettingsContent()
        case .presence:    PresenceSettingsContent()
        case .devices:     DevicesSettingsContent()
        case .permissions: stubContent("Permissions live here. Microphone, motion, HealthKit, notifications.")
        case .lab:         LabSettingsContent()
        case .dev:         DevSettingsContent()
        case .about:       stubContent("Daybook · v0.1\nBuilt with care by Aakash Agrawal\nLearn more at koinelabs.com")
        }
    }

    @ViewBuilder
    private func stubContent(_ body: String) -> some View {
        Text(body)
            .font(.system(size: 14))
            .foregroundStyle(theme.ink2)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.top, 8)
    }
}

// MARK: - Per-section stub content (real wiring later)

private struct PersonaSettingsContent: View {
    @Environment(Theme.self) private var theme
    var body: some View {
        VStack(spacing: 0) {
            settingsRow(label: "Playfulness", value: "0.62", theme: theme)
            settingsRow(label: "Reverence", value: "0.48", theme: theme)
            settingsRow(label: "Chattiness", value: "0.35", theme: theme)
            settingsRow(label: "Directness", value: "0.71", theme: theme)
            settingsRow(label: "Familiarity", value: "0.88", theme: theme)
            settingsRow(label: "Humor (dry)", value: "0.79", theme: theme)
        }
    }
}

private struct PresenceSettingsContent: View {
    @Environment(Theme.self) private var theme
    var body: some View {
        VStack(spacing: 0) {
            settingsRow(label: "TTS voice", value: "not picked", theme: theme)
            settingsRow(label: "Speak quietly", value: "auto", theme: theme)
            settingsRow(label: "Wake-word", value: "off", theme: theme)
        }
    }
}

private struct DevicesSettingsContent: View {
    @Environment(Theme.self) private var theme
    var body: some View {
        VStack(spacing: 0) {
            settingsRow(label: "Apple Watch", value: "paired", theme: theme)
            settingsRow(label: "Pi 4 (bedside)", value: "discovering...", theme: theme)
            settingsRow(label: "Bone-conduction", value: "arriving ~3 days", theme: theme)
            settingsRow(label: "BioAmp EXG Pill", value: "arriving ~10 days", theme: theme)
        }
    }
}

private struct LabSettingsContent: View {
    @Environment(Theme.self) private var theme
    var body: some View {
        VStack(spacing: 0) {
            settingsRow(label: "EEG sensor view", value: "—", theme: theme)
            settingsRow(label: "Hypnogram (last night)", value: "open →", theme: theme)
            settingsRow(label: "Realtime classifier", value: "v2-bio · F1=0.45", theme: theme)
            settingsRow(label: "API base", value: "localhost:8000", theme: theme)
        }
    }
}

private struct DevSettingsContent: View {
    @Environment(AppState.self) private var appState
    @Environment(Theme.self) private var theme

    var body: some View {
        VStack(spacing: 0) {
            triggerRow("Threshold", "pre-sleep wind-down", .threshold)
            triggerRow("Night", "REM cue — witness mode", .night)
            triggerRow("Recall", "morning capture ceremony", .recall)
        }
    }

    @ViewBuilder
    private func triggerRow(_ label: String, _ sub: String, _ route: ImmersiveRoute) -> some View {
        Button {
            appState.immersive = route
            appState.settingsOpen = false
        } label: {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(label)
                        .font(.system(size: 14, weight: .medium))
                        .foregroundStyle(theme.ink)
                    Text(sub)
                        .font(.custom("Charter-Italic", size: 13).italic())
                        .foregroundStyle(theme.ink3)
                }
                Spacer()
                Text("OPEN →")
                    .dbMeta(theme.amber)
            }
            .padding(.vertical, 14)
            .frame(maxWidth: .infinity)
            .overlay(
                Rectangle()
                    .fill(theme.edge)
                    .frame(height: 0.5),
                alignment: .bottom
            )
        }
        .buttonStyle(.plain)
    }
}

private func settingsRow(label: String, value: String, theme: Theme) -> some View {
    HStack(alignment: .center) {
        Text(label)
            .font(.system(size: 14, weight: .medium))
            .foregroundStyle(theme.ink)
        Spacer()
        Text(value)
            .font(.system(size: 11.5, design: .monospaced))
            .foregroundStyle(theme.ink2)
    }
    .padding(.vertical, 14)
    .overlay(
        Rectangle()
            .fill(theme.edge)
            .frame(height: 0.5),
        alignment: .bottom
    )
}
