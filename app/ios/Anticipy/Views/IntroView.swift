import SwiftUI

/// THE OPENING, on the phone. `LaunchIntro` decides every number; this view
/// scales the 300×600 stage to the screen, asks it for the frame at `t`, and
/// draws three things — the seed, the wavefront, and the capsule behind the
/// wavefront's clip. Nothing else is on screen: no text, no button, no filler.
/// The owner's rule for the piece was that nothing appears that was not drawn
/// in front of them.
///
/// A tap anywhere ends it early, so a returning stranger is never held for
/// four seconds; VoiceOver reads the whole stage as one control for the same
/// reason. With Reduce Motion on, the finished mark is shown still and held
/// for a moment, because a person who asked for less motion asked for less
/// motion, not for a shorter product.
struct IntroView: View {
    var onDone: () -> Void

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var start: Date?
    @State private var finished = false

    var body: some View {
        GeometryReader { geo in
            let stageH = min(geo.size.height * 0.82, 660)
            let stageW = stageH * (LaunchIntro.stageWidth / LaunchIntro.stageHeight)
            ZStack {
                OnboardTheme.ground
                TimelineView(.animation(paused: finished || reduceMotion || start == nil)) { context in
                    IntroStage(frame: frame(at: context.date))
                }
                .frame(width: stageW, height: stageH)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .ignoresSafeArea()
        .contentShape(Rectangle())
        .onTapGesture { complete() }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Anticipy")
        .accessibilityHint("Skips the intro")
        .accessibilityAddTraits(.isButton)
        .accessibilityAction { complete() }
        .onAppear { start = Date() }
        .task {
            let hold = reduceMotion ? LaunchIntro.reducedMotionHold : LaunchIntro.end
            try? await Task.sleep(nanoseconds: UInt64(hold * 1_000_000_000))
            guard !Task.isCancelled else { return }
            complete()
        }
    }

    private func frame(at date: Date) -> LaunchIntro.Frame {
        if reduceMotion || finished { return LaunchIntro.finalFrame }
        guard let start else { return LaunchIntro.frame(at: 0) }
        let t = date.timeIntervalSince(start)
        return t >= LaunchIntro.end ? LaunchIntro.finalFrame : LaunchIntro.frame(at: t)
    }

    private func complete() {
        guard !finished else { return }
        finished = true
        onDone()
    }
}

/// One frame of the piece, drawn in stage units scaled to the canvas.
private struct IntroStage: View {
    var frame: LaunchIntro.Frame

    var body: some View {
        Canvas(rendersAsynchronously: false) { ctx, size in
            let s = size.height / LaunchIntro.stageHeight
            let ink = OnboardTheme.ink
            let cx = LaunchIntro.centerX * s
            let cy = LaunchIntro.centerY * s

            // The capsule, under the wavefront's clip. ONE radius drives the
            // clip and the visible ring below, so the outline appears exactly
            // where the ring has just been.
            if frame.revealRadius > 0 {
                var revealed = ctx
                let r = frame.revealRadius * s
                revealed.clip(to: Path(ellipseIn: CGRect(x: cx - r, y: cy - r, width: 2 * r, height: 2 * r)))
                let rect = CGRect(x: LaunchIntro.capsuleX * s,
                                  y: LaunchIntro.capsuleY * s,
                                  width: LaunchIntro.capsuleWidth * s,
                                  height: LaunchIntro.capsuleHeight * s)
                revealed.stroke(Path(roundedRect: rect, cornerRadius: LaunchIntro.capsuleCorner * s, style: .circular),
                                with: .color(ink),
                                style: StrokeStyle(lineWidth: LaunchIntro.capsuleStroke * s, lineJoin: .round))
            }

            // The seed: blooms, squashes once, later slides to its home and
            // becomes the mark's dot.
            if frame.dotOpacity > 0, frame.dotRX > 0 {
                let rx = frame.dotRX * s
                let ry = frame.dotRY * s
                let dotY = frame.dotCY * s
                ctx.fill(Path(ellipseIn: CGRect(x: cx - rx, y: dotY - ry, width: 2 * rx, height: 2 * ry)),
                         with: .color(ink.opacity(frame.dotOpacity)))
            }

            // The wavefront: a hairline ring that fades as it expands.
            if frame.ringOpacity > 0.001 {
                let r = frame.revealRadius * s
                ctx.stroke(Path(ellipseIn: CGRect(x: cx - r, y: cy - r, width: 2 * r, height: 2 * r)),
                           with: .color(ink.opacity(frame.ringOpacity)),
                           lineWidth: LaunchIntro.ringStroke * s)
            }
        }
    }
}
