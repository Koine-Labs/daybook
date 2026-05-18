import SwiftUI

// NightView — REM cue moment. Witness Mode. Star field background, large wisp
// in 'witnessing' state, Regis utterance in serif italic warm.
// Port of ScreenNight from screens-witness.jsx. This screen should feel SPARSE
// and reverent — the most ceremonial of the three.
// TODO: replace mock hypnogram + cue log with realtime classifier output
// (apps/inference/realtime.py) once the live data pipeline is wired.
struct NightView: View {
    @Environment(Theme.self) private var theme

    // Mock hypnogram. 0=awake, 1=light, 2=deep, 3=rem.
    private let hyp: [Int] = [
        0,0,0,1,1,2,2,2,3,2,2,1,1,2,2,2,2,3,3,2,
        1,1,2,2,3,3,3,2,1,1,1,2,2,2,3,3,3,3,2,1,
        1,1,2,2,2,3,3,1,1,0
    ]

    private struct CueMarker {
        let index: Int
        let text: String
    }

    private let cueMarkers: [CueMarker] = [
        .init(index: 8,  text: "you are dreaming"),
        .init(index: 18, text: "notice the color"),
        .init(index: 26, text: "stay a moment longer"),
        .init(index: 36, text: "carry it back with you")
    ]

    private let nowIdx: Int = 26

    private struct LogEntry {
        let time: String
        let label: String
        let isRegis: Bool
        let isCurrent: Bool
    }

    private let logEntries: [LogEntry] = [
        .init(time: "22:50", label: "lights out · armed",       isRegis: false, isCurrent: false),
        .init(time: "23:14", label: "sleep onset · sound off",  isRegis: false, isCurrent: false),
        .init(time: "01:42", label: "\"you are dreaming\"",     isRegis: true,  isCurrent: false),
        .init(time: "03:08", label: "\"notice the color\"",     isRegis: true,  isCurrent: false),
        .init(time: "04:35", label: "\"stay a moment longer\"", isRegis: true,  isCurrent: true)
    ]

    var body: some View {
        ZStack {
            background
                .ignoresSafeArea()

            StarfieldView()
                .allowsHitTesting(false)

            VStack(spacing: 0) {
                header
                    .padding(.horizontal, 24)
                    .padding(.top, 54)

                Spacer(minLength: 0)

                centerStanza
                    .padding(.horizontal, 30)

                Spacer(minLength: 0)

                bottomTimeline
                    .padding(.horizontal, 24)
                    .padding(.bottom, 110)
            }
        }
    }

    // MARK: - Background

    private var background: some View {
        RadialGradient(
            gradient: Gradient(stops: [
                .init(color: Color(hex: "131a2a"), location: 0.0),
                .init(color: Color(hex: "0a0e1a"), location: 0.5),
                .init(color: Color(hex: "07090f"), location: 1.0)
            ]),
            center: UnitPoint(x: 0.5, y: 0.18),
            startRadius: 0,
            endRadius: 700
        )
    }

    // MARK: - Header

    private var header: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 4) {
                Text("witnessing · night 3 of 60")
                    .dbMeta(Color(red: 255/255, green: 203/255, blue: 149/255, opacity: 0.6))
                Text("04:38")
                    .font(DBFont.serif(38))
                    .tracking(-0.38)
                    .monospacedDigit()
                    .foregroundStyle(Color(hex: "FFCB95"))
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 4) {
                Text("do not disturb")
                    .dbMeta(Color(red: 232/255, green: 226/255, blue: 212/255, opacity: 0.4))
                WispView(size: 20, state: .witnessing, mode: .witness)
            }
        }
    }

    // MARK: - Center stanza

    private var centerStanza: some View {
        VStack(spacing: 18) {
            WispView(size: 70, state: .witnessing, mode: .witness)

            RegisQuote("\"stay a moment longer.\"", size: 26)
                .multilineTextAlignment(.center)

            Text("rem · whisper 3 of 4 · 04:35")
                .dbMeta(Color(red: 255/255, green: 203/255, blue: 149/255, opacity: 0.4))
                .padding(.top, 6)
        }
        .frame(maxWidth: .infinity)
    }

    // MARK: - Bottom timeline (hypnogram + cue log)

    private var bottomTimeline: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("22:47")
                    .dbMeta(Color(red: 232/255, green: 226/255, blue: 212/255, opacity: 0.5))
                Spacer()
                Text("stage · rem")
                    .dbMeta(Color(red: 232/255, green: 226/255, blue: 212/255, opacity: 0.5))
                Spacer()
                Text("06:30 ↗")
                    .dbMeta(Color(red: 232/255, green: 226/255, blue: 212/255, opacity: 0.5))
            }
            .padding(.bottom, 6)

            hypnogram
                .frame(height: 64)
                .padding(.vertical, 4)

            VStack(spacing: 6) {
                ForEach(Array(logEntries.enumerated()), id: \.offset) { _, entry in
                    logRow(entry)
                }
            }
            .padding(.top, 14)
        }
    }

    private var hypnogram: some View {
        GeometryReader { geo in
            ZStack(alignment: .topLeading) {
                // y-axis dashed labels
                ForEach(Array(["rem", "light", "deep", "awake"].enumerated()), id: \.offset) { idx, label in
                    let y = CGFloat(idx) * 12 + 8
                    ZStack(alignment: .topLeading) {
                        Rectangle()
                            .fill(Color(red: 232/255, green: 226/255, blue: 212/255, opacity: 0.07))
                            .frame(height: 0.5)
                            .offset(y: y)
                        Text(label)
                            .font(DBFont.mono(8))
                            .foregroundStyle(Color(red: 232/255, green: 226/255, blue: 212/255, opacity: 0.3))
                            .offset(x: 0, y: y - 9)
                    }
                }

                // bars + cue markers + now line
                Canvas { ctx, size in
                    let total = CGFloat(hyp.count)
                    let drawableHeight: CGFloat = 48
                    let topInset: CGFloat = 8
                    let barW = size.width / total

                    for (i, stage) in hyp.enumerated() {
                        let x = CGFloat(i) * barW
                        let y: CGFloat
                        switch stage {
                        case 3: y = 0
                        case 1: y = 12
                        case 2: y = 24
                        default: y = 36
                        }
                        let isRem = stage == 3
                        let past = i <= nowIdx
                        let color: Color
                        let opacity: Double
                        if isRem {
                            color = Color(hex: "E89456")
                            opacity = past ? 0.9 : 0.18
                        } else if past {
                            color = Color(hex: "FFCB95")
                            opacity = 0.45
                        } else {
                            color = Color(red: 232/255, green: 226/255, blue: 212/255, opacity: 0.3)
                            opacity = 0.18
                        }
                        let rect = CGRect(x: x, y: topInset + y, width: max(0, barW - 0.5), height: 10)
                        ctx.fill(Path(rect), with: .color(color.opacity(opacity)))
                    }

                    // cue markers (dashed verticals)
                    for cue in cueMarkers {
                        let x = (CGFloat(cue.index) / total) * size.width + barW / 2
                        var p = Path()
                        p.move(to: CGPoint(x: x, y: topInset - 2))
                        p.addLine(to: CGPoint(x: x, y: topInset + drawableHeight))
                        ctx.stroke(
                            p,
                            with: .color(Color(hex: "FFCB95").opacity(0.7)),
                            style: StrokeStyle(lineWidth: 0.8, dash: [2, 2])
                        )
                    }

                    // now line
                    let nowX = (CGFloat(nowIdx) / total) * size.width + 4
                    var nowPath = Path()
                    nowPath.move(to: CGPoint(x: nowX, y: topInset - 4))
                    nowPath.addLine(to: CGPoint(x: nowX, y: topInset + drawableHeight + 2))
                    ctx.stroke(nowPath, with: .color(Color(hex: "FFCB95")), lineWidth: 1.4)
                }
                .padding(.horizontal, 0)
                .padding(.vertical, 0)
                .frame(width: geo.size.width, height: geo.size.height)
            }
        }
    }

    @ViewBuilder
    private func logRow(_ entry: LogEntry) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            Text(entry.time)
                .font(DBFont.mono(10.5))
                .tracking(0.5)
                .foregroundStyle(entry.isCurrent
                                 ? Color(hex: "FFCB95")
                                 : Color(red: 232/255, green: 226/255, blue: 212/255, opacity: 0.4))
                .frame(width: 54, alignment: .leading)

            if entry.isRegis {
                Text(entry.label)
                    .font(DBFont.serif(entry.isCurrent ? 16 : 14, italic: true))
                    .foregroundStyle(entry.isCurrent
                                     ? Color(hex: "FFCB95")
                                     : Color(hex: "E89456").opacity(0.65))
                    .frame(maxWidth: .infinity, alignment: .leading)
            } else {
                Text(entry.label)
                    .font(DBFont.sans(13))
                    .foregroundStyle(Color(red: 232/255, green: 226/255, blue: 212/255, opacity: 0.45))
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }
}

#Preview {
    let theme = Theme()
    theme.mode = .witness
    return NightView()
        .environment(theme)
}
