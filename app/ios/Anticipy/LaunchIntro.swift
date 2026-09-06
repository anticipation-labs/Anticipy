import Foundation

/// THE OPENING — a dot, a wavefront, and the mark it leaves behind.
///
/// This is the four-second intro the owner approved as `anticipy-intro.html`
/// (2026-09-05): no text, no colour but ink on the logo's cream, nothing on
/// screen that was already there. A seed dot blooms at the centre, squashes
/// once to launch a ring, and the ring's radius is the SAME number that clips
/// the capsule outline — so the mark is revealed by the wavefront, not faded
/// in beside it. When the ring has passed the corners the seed slides down
/// to its home, seventy percent of the way along the capsule, and the intro
/// is the logo.
///
/// Everything numeric lives here, in the HTML's own 300×600 stage units, as
/// pure Foundation: `IntroView` only scales and draws what `frame(at:)` says.
/// `run_launch_intro_tests.sh` compiles this file alone and walks the
/// timeline, so a curve that no longer reaches the corners or a dot that no
/// longer lands is a red leg rather than a feeling on a simulator.
enum LaunchIntro {

    // MARK: Stage geometry (HTML viewBox units)

    static let stageWidth: Double = 300
    static let stageHeight: Double = 600
    static let centerX: Double = 150
    static let centerY: Double = 300

    /// The capsule outline: x, y, width, height, corner radius, stroke.
    static let capsuleX: Double = 80
    static let capsuleY: Double = 160
    static let capsuleWidth: Double = 140
    static let capsuleHeight: Double = 280
    static let capsuleCorner: Double = 70
    static let capsuleStroke: Double = 15

    /// The seed dot's radius and where it comes to rest.
    static let dotRadius: Double = 11
    static let dotHome: Double = 356

    /// The wavefront has to clear the capsule's far corners, plus a margin.
    static let revealRadius: Double = 175
    static let revealOvershoot: Double = 30
    static let ringStroke: Double = 2
    static let ringPeakOpacity: Double = 0.85

    // MARK: Timeline (seconds)

    static let seedEnd: TimeInterval = 0.50
    static let landEnd: TimeInterval = 0.63
    static let revealEnd: TimeInterval = 2.10
    static let dotEnd: TimeInterval = 2.42
    static let end: TimeInterval = 4.00

    /// How long the finished mark is held when motion is reduced, so the
    /// opening is still a moment rather than a flicker.
    static let reducedMotionHold: TimeInterval = 1.2

    // MARK: Easing — the HTML's cubic-beziers, solved the same way

    static let easeSeed = UnitBezier(0.34, 1.28, 0.64, 1)     // one crisp bloom with a micro-overshoot
    static let easeRipple = UnitBezier(0.22, 1, 0.36, 1)      // smooth, deliberate expansion
    static let easeDot = UnitBezier(0.22, 1, 0.36, 1)

    // MARK: One frame

    struct Frame: Equatable {
        var dotRX: Double
        var dotRY: Double
        var dotCY: Double
        var dotOpacity: Double
        /// One value drives BOTH the visible ring and the clip that reveals
        /// the capsule. That is the whole idea of the piece.
        var revealRadius: Double
        var ringOpacity: Double
    }

    static func frame(at t: TimeInterval) -> Frame {
        // Seed dot: bloom, then a whisper of squash to birth the ripple.
        var rx = dotRadius, ry = dotRadius
        if t < seedEnd {
            let s = easeSeed(unit(t, 0, seedEnd))
            rx = dotRadius * s
            ry = rx
        } else if t < landEnd {
            let b = sin(unit(t, seedEnd, landEnd) * .pi) * 0.12
            ry = dotRadius * (1 - b)
            rx = dotRadius * (1 + b)
        }

        // The seed slides to its low home once the mark exists.
        var cy = centerY
        if t >= revealEnd {
            cy = t < dotEnd
                ? lerp(centerY, dotHome, easeDot(unit(t, revealEnd, dotEnd)))
                : dotHome
        }

        // The radial reveal.
        var radius = 0.0, ringOpacity = 0.0
        if t >= landEnd {
            let p = easeRipple(unit(t, landEnd, revealEnd))
            radius = revealRadius * p
            ringOpacity = ringPeakOpacity * (1 - p)
            if t >= revealEnd {
                radius = revealRadius + revealOvershoot
                ringOpacity = 0
            }
        }

        return Frame(dotRX: rx, dotRY: ry, dotCY: cy,
                     dotOpacity: unit(t, 0, 0.18),
                     revealRadius: radius, ringOpacity: ringOpacity)
    }

    /// The logo at rest — what reduced motion shows, and where every play ends.
    static let finalFrame = Frame(dotRX: dotRadius, dotRY: dotRadius, dotCY: dotHome,
                                  dotOpacity: 1,
                                  revealRadius: revealRadius + revealOvershoot,
                                  ringOpacity: 0)

    /// The distance from the stage centre to the capsule's farthest painted
    /// point, half the stroke included. The reveal radius has to pass it, or
    /// the wavefront leaves a corner undrawn.
    static var farthestPaintedRadius: Double {
        let dx = capsuleWidth / 2 + capsuleStroke / 2
        let dy = capsuleHeight / 2 + capsuleStroke / 2
        // The corners are rounded by `capsuleCorner`, so the farthest point
        // sits on the corner arc, not at the bounding box's vertex.
        let armX = capsuleWidth / 2 - capsuleCorner
        let armY = capsuleHeight / 2 - capsuleCorner
        let arc = capsuleCorner + capsuleStroke / 2
        return max(hypot(armX, armY) + arc, max(dx, dy))
    }

    // MARK: Where it plays

    /// The opening belongs to a person who has not yet arrived: it plays on a
    /// cold launch that lands anywhere in first run, and never over Home,
    /// where the owner is coming back to something.
    static func plays(route: FirstRunRoute) -> Bool {
        route != .home
    }

    // MARK: Helpers

    static func unit(_ x: Double, _ a: Double, _ b: Double) -> Double {
        min(max((x - a) / (b - a), 0), 1)
    }

    static func lerp(_ a: Double, _ b: Double, _ p: Double) -> Double {
        a + (b - a) * p
    }
}

/// A CSS `cubic-bezier(p1x, p1y, p2x, p2y)` solved with the same six Newton
/// steps the HTML used, so the curves on the phone are the curves the owner
/// approved in the browser.
struct UnitBezier {
    private let ax, bx, cx, ay, by, cy: Double

    init(_ p1x: Double, _ p1y: Double, _ p2x: Double, _ p2y: Double) {
        cx = 3 * p1x
        bx = 3 * (p2x - p1x) - cx
        ax = 1 - cx - bx
        cy = 3 * p1y
        by = 3 * (p2y - p1y) - cy
        ay = 1 - cy - by
    }

    func callAsFunction(_ x: Double) -> Double {
        let x = min(max(x, 0), 1)
        var t = x
        for _ in 0..<6 {
            let d = (3 * ax * t + 2 * bx) * t + cx
            if abs(d) < 1e-6 { break }
            t -= (((ax * t + bx) * t + cx) * t - x) / d
            t = min(max(t, 0), 1)
        }
        return ((ay * t + by) * t + cy) * t
    }
}
