import Foundation

// The opening's timeline, walked. Compiled by run_launch_intro_tests.sh with
// the production LaunchIntro.swift and FirstRunRoute.swift — this file is the
// suite's main.swift, so it may hold top-level code.

var failures = 0
func check(_ ok: Bool, _ name: String, _ detail: @autoclosure () -> String = "") {
    if ok { print("PASS: \(name)") } else { failures += 1; print("FAIL: \(name) \(detail())") }
}
func near(_ a: Double, _ b: Double, _ eps: Double = 1e-6) -> Bool { abs(a - b) <= eps }

// ---- the curves are the browser's curves
let linear = UnitBezier(0, 0, 1, 1)
check(near(linear(0), 0) && near(linear(1), 1), "a bezier starts at 0 and ends at 1")
check(near(linear(0.25), 0.25, 1e-3) && near(linear(0.5), 0.5, 1e-3) && near(linear(0.75), 0.75, 1e-3),
      "cubic-bezier(0,0,1,1) is the identity")
check(LaunchIntro.easeRipple(0.5) > 0.5, "the ripple's ease-out is ahead of linear at the midpoint",
      "got \(LaunchIntro.easeRipple(0.5))")
check(near(LaunchIntro.easeRipple(-1), 0) && near(LaunchIntro.easeRipple(2), 1), "inputs outside 0...1 are clamped")

// ---- t = 0: nothing on screen yet
let first = LaunchIntro.frame(at: 0)
check(first.dotRX == 0 && first.dotRY == 0, "at zero the seed has no size")
check(first.dotOpacity == 0, "at zero the seed is invisible")
check(first.revealRadius == 0 && first.ringOpacity == 0, "at zero nothing is revealed and there is no ring")

// ---- the seed blooms with one overshoot and settles to its radius
var peak = 0.0
var t = 0.0
while t < LaunchIntro.seedEnd { peak = max(peak, LaunchIntro.frame(at: t).dotRX); t += 0.005 }
check(peak > LaunchIntro.dotRadius, "the bloom overshoots the resting radius once", "peak \(peak)")
check(peak < LaunchIntro.dotRadius * 1.25, "and the overshoot is a micro-overshoot, not a balloon", "peak \(peak)")
let settled = LaunchIntro.frame(at: LaunchIntro.seedEnd)
check(near(settled.dotRX, LaunchIntro.dotRadius) && near(settled.dotRY, LaunchIntro.dotRadius),
      "at seedEnd the seed is exactly its resting radius")
let squash = LaunchIntro.frame(at: (LaunchIntro.seedEnd + LaunchIntro.landEnd) / 2)
check(squash.dotRX > LaunchIntro.dotRadius && squash.dotRY < LaunchIntro.dotRadius,
      "between seedEnd and landEnd the seed squashes wide to launch the ring")
check(near(squash.dotCY, LaunchIntro.centerY), "and has not moved yet")

// ---- one radius drives the ring and the clip, and it only grows
var lastR = -1.0
var monotonic = true
var ringSeen = false
t = 0
while t <= LaunchIntro.end {
    let f = LaunchIntro.frame(at: t)
    if f.revealRadius < lastR - 1e-9 { monotonic = false }
    lastR = f.revealRadius
    if f.ringOpacity > 0 { ringSeen = true }
    t += 0.01
}
check(monotonic, "the wavefront never shrinks")
check(ringSeen, "the ring is visible at some point")
let justBefore = LaunchIntro.frame(at: LaunchIntro.landEnd + 0.01)
check(justBefore.ringOpacity > 0.7 && justBefore.revealRadius > 0,
      "the ring is bright as it leaves the seed", "opacity \(justBefore.ringOpacity)")
let atReveal = LaunchIntro.frame(at: LaunchIntro.revealEnd)
check(atReveal.ringOpacity == 0, "at revealEnd the ring is gone")
check(atReveal.revealRadius > LaunchIntro.farthestPaintedRadius,
      "the wavefront has passed every painted point of the capsule",
      "reveal \(atReveal.revealRadius) farthest \(LaunchIntro.farthestPaintedRadius)")
check(LaunchIntro.revealRadius > LaunchIntro.farthestPaintedRadius,
      "the ring itself, not just the overshoot, clears the corners",
      "ring \(LaunchIntro.revealRadius) farthest \(LaunchIntro.farthestPaintedRadius)")

// ---- the seed slides home after the mark exists, and only then
check(near(LaunchIntro.frame(at: LaunchIntro.revealEnd - 0.01).dotCY, LaunchIntro.centerY),
      "the seed is still centred a frame before the reveal ends")
var lastY = LaunchIntro.centerY
var descends = true
t = LaunchIntro.revealEnd
while t <= LaunchIntro.dotEnd {
    let y = LaunchIntro.frame(at: t).dotCY
    if y < lastY - 1e-9 { descends = false }
    lastY = y
    t += 0.005
}
check(descends, "the slide home never reverses")
check(near(LaunchIntro.frame(at: LaunchIntro.dotEnd).dotCY, LaunchIntro.dotHome), "at dotEnd the seed is home")
check(LaunchIntro.dotHome > LaunchIntro.centerY, "home is below centre — the mark's dot sits low")
check(LaunchIntro.dotHome + LaunchIntro.dotRadius < LaunchIntro.capsuleY + LaunchIntro.capsuleHeight - LaunchIntro.capsuleStroke,
      "and inside the capsule, clear of the stroke")

// ---- the end is the logo, and the logo is what reduced motion shows
check(LaunchIntro.frame(at: LaunchIntro.end) == LaunchIntro.finalFrame, "the last frame is the final frame")
check(LaunchIntro.frame(at: LaunchIntro.end + 10) == LaunchIntro.finalFrame, "and it stays there")
check(LaunchIntro.finalFrame.dotOpacity == 1 && LaunchIntro.finalFrame.ringOpacity == 0,
      "the final frame is the mark alone")
check(near(LaunchIntro.end, 4.0), "the piece is four seconds", "end \(LaunchIntro.end)")
check(LaunchIntro.seedEnd < LaunchIntro.landEnd && LaunchIntro.landEnd < LaunchIntro.revealEnd
      && LaunchIntro.revealEnd < LaunchIntro.dotEnd && LaunchIntro.dotEnd < LaunchIntro.end,
      "the beats are in order")
check(LaunchIntro.reducedMotionHold > 0 && LaunchIntro.reducedMotionHold < LaunchIntro.end,
      "reduced motion holds the mark for a moment, shorter than the piece")

// ---- where it plays: in front of a stranger, never in front of Home
check(LaunchIntro.plays(route: .intro), "plays before the welcome")
check(LaunchIntro.plays(route: .door), "plays before the door")
check(LaunchIntro.plays(route: .tour(.rest)), "plays before the rest of the tour")
check(LaunchIntro.plays(route: .tour(.whole)), "plays before the whole tour")
check(!LaunchIntro.plays(route: .home), "never plays over Home")

if failures == 0 {
    print("LaunchIntroTests: all passed")
} else {
    print("LaunchIntroTests: \(failures) case(s) came back wrong")
    exit(1)
}
