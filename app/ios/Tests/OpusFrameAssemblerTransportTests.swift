import Foundation

@main
struct OpusFrameAssemblerTransportTests {
    static func main() {
        var checks = 0
        var failures = 0
        func check(_ condition: Bool, _ message: String) {
            checks += 1
            if !condition {
                failures += 1
                print("FAIL: \(message)")
            }
        }
        func packet(_ index: UInt16, _ counter: UInt8, _ byte: UInt8 = 0xAA) -> Data {
            Data([UInt8(index & 0xff), UInt8(index >> 8), counter, byte])
        }

        // Loss immediately before counter zero must not emit a truncated
        // previous frame. That boundary is recovery, not proof of completion.
        var boundary = OpusFrameAssembler()
        _ = boundary.accept(packet(100, 0, 1))
        check(boundary.accept(packet(102, 0, 2)) == nil,
              "a missing fragment before the next frame cannot emit partial Opus")
        check(boundary.droppedFrames == 1, "boundary loss counts one dropped frame")
        _ = boundary.accept(packet(103, 1, 3))
        check(boundary.accept(packet(104, 0, 4)) == Data([2, 3]),
              "the new frame recovers after a lost-boundary frame")

        // Duplicates and stale notifications cannot become a 16-bit wrap's
        // worth of loss, or themselves act as a new-frame completion witness.
        var duplicate = OpusFrameAssembler()
        _ = duplicate.accept(packet(100, 0, 1))
        check(duplicate.accept(packet(100, 0, 1)) == nil,
              "a duplicate frame start cannot emit a frame")
        check(duplicate.takeGap() == OpusTransportGap(missingNotifications: 0, discardedFrames: 1),
              "a duplicate reports the local frame discard, not missing airtime")
        check(duplicate.accept(packet(101, 0, 2)) == nil,
              "the first fresh start after a duplicate does not replay buffered bytes")
        check(duplicate.accept(packet(102, 0, 3)) == Data([2]),
              "a fresh continuous frame after a duplicate is preserved")

        var reorder = OpusFrameAssembler()
        _ = reorder.accept(packet(200, 0, 1))
        _ = reorder.accept(packet(201, 1, 2))
        check(reorder.accept(packet(199, 0, 9)) == nil,
              "an older frame start cannot emit or replace current bytes")
        check(reorder.takeGap()?.missingNotifications == 0, "a stale packet does not invent wrap loss")
        check(reorder.accept(packet(202, 0, 3)) == nil,
              "the next fresh start recovers without emitting stale bytes")
        check(reorder.accept(packet(203, 0, 4)) == Data([3]),
              "stale input never moves the high-water sequence backwards")

        var wrap = OpusFrameAssembler()
        _ = wrap.accept(packet(65534, 0, 1))
        _ = wrap.accept(packet(65535, 1, 2))
        check(wrap.accept(packet(0, 0, 3)) == Data([1, 2]),
              "ordinary 16-bit wrap preserves a complete frame")
        check(wrap.takeGap() == nil, "ordinary wrap invents no missing airtime")

        var wrapLoss = OpusFrameAssembler()
        _ = wrapLoss.accept(packet(65534, 0, 1))
        check(wrapLoss.accept(packet(0, 0, 2)) == nil,
              "loss at wrap also refuses a truncated previous frame")
        check(wrapLoss.droppedFrames == 1, "wrap loss drops one frame")
        check(wrapLoss.accept(packet(1, 0, 3)) == Data([2]),
              "wrap loss recovers without losing the fresh frame")

        var wrapReorder = OpusFrameAssembler()
        _ = wrapReorder.accept(packet(65535, 0, 1))
        _ = wrapReorder.accept(packet(0, 1, 2))
        check(wrapReorder.accept(packet(65535, 0, 9)) == nil,
              "a pre-wrap stale packet cannot masquerade as a forward wrap")
        check(wrapReorder.takeGap()?.missingNotifications == 0, "pre-wrap reorder does not invent airtime")
        _ = wrapReorder.accept(packet(1, 0, 3))
        check(wrapReorder.accept(packet(2, 0, 4)) == Data([3]),
              "pre-wrap reorder does not move the accepted sequence")

        var ambiguous = OpusFrameAssembler()
        _ = ambiguous.accept(packet(0, 0, 1))
        check(ambiguous.accept(packet(32768, 0, 2)) == nil,
              "an exact half-range sequence cannot prove serial ordering")
        check(ambiguous.takeGap()?.missingNotifications == 0, "ambiguous ordering claims no loss duration")
        _ = ambiguous.accept(packet(1, 0, 3))
        check(ambiguous.accept(packet(2, 0, 4)) == Data([3]),
              "ambiguous ordering does not move the accepted sequence")

        var repeated = OpusFrameAssembler()
        _ = repeated.accept(packet(10, 0, 1))
        _ = repeated.accept(packet(11, 1, 2))
        _ = repeated.accept(packet(11, 1, 2))
        _ = repeated.accept(packet(11, 1, 2))
        check(repeated.takeGap() == OpusTransportGap(missingNotifications: 0, discardedFrames: 1),
              "repeated duplicates accumulate only the single discarded frame")
        check(repeated.accept(packet(12, 0, 3)) == nil,
              "duplicate continuations invalidate the buffered frame; the next start emits nothing")
        check(repeated.droppedFrames == 1, "repeated bad input drops each buffered frame only once")

        var malformed = OpusFrameAssembler()
        _ = malformed.accept(packet(10, 0, 1))
        _ = malformed.accept(Data([0]))
        check(malformed.accept(packet(11, 0, 2)) == nil,
              "a short notification cannot leave a partial frame for the next start to emit")
        check(malformed.droppedFrames == 1, "a malformed notification drops one buffered frame")

        var disconnected = OpusFrameAssembler()
        _ = disconnected.accept(packet(50000, 0, 1))
        disconnected.discardCurrentFrame()
        check(disconnected.accept(packet(4, 0, 2)) == nil,
              "disconnect resets sequence without leaking the previous session")
        check(disconnected.accept(packet(5, 0, 3)) == Data([2]),
              "reconnect can restart the sequence anywhere")
        check(disconnected.takeGap() == nil,
              "reconnect does not infer a radio downtime duration")

        var empty = OpusFrameAssembler()
        _ = empty.accept(packet(10, 0, 1))
        check(empty.accept(Data([11, 0, 0])) == nil,
              "a header-only frame start cannot prove the previous frame complete")
        check(empty.droppedFrames == 1, "header-only input drops the buffered frame")
        check(empty.accept(packet(12, 0, 2)) == nil,
              "header-only input cannot leave a valid frame for the next start to emit")

        var pending = OpusFrameAssembler()
        _ = pending.accept(packet(10, 0, 1))
        _ = pending.accept(packet(12, 0, 2))
        pending.discardCurrentFrame()
        _ = pending.accept(packet(500, 0, 3))
        check(pending.takeGap() == nil,
              "undrained previous-session loss does not leak across reconnect")

        // THE STALL, as it actually behaves (2026-09-14). One jump past the
        // half-range window wedges the assembler until the counter laps or the
        // radio disconnects. This pins the CURRENT behaviour, not a wish: the
        // repair was reverted because two stale packets re-origin the stream
        // backward (see the assembler's comment). Change this case only with a
        // repair that cannot move the mark backward.
        var stalled = OpusFrameAssembler()
        _ = stalled.accept(packet(100, 0, 1))
        check(stalled.accept(packet(40100, 0, 2)) == nil,
              "the first packet past the window is rejected")
        check(stalled.droppedFrames == 1, "the frame in flight at the jump is discarded")
        check(stalled.accept(packet(40101, 0, 3)) == nil,
              "and so is the next one: the mark did not move")
        check(stalled.accept(packet(40102, 0, 4)) == nil,
              "the assembler stays wedged until the counter laps or the radio drops")
        check(stalled.takeGap() == OpusTransportGap(missingNotifications: 0, discardedFrames: 1),
              "a wedged assembler invents no missing airtime")
        stalled.discardCurrentFrame()
        _ = stalled.accept(packet(40103, 0, 5))
        check(stalled.accept(packet(40104, 0, 6)) == Data([5]),
              "a reconnect is the recovery point, and it works")

        var stray = OpusFrameAssembler()
        _ = stray.accept(packet(100, 0, 1))
        check(stray.accept(packet(40100, 0, 2)) == nil, "a stray far packet is rejected")
        check(stray.accept(packet(101, 0, 3)) == nil,
              "the in-order packet after a stray does not emit the discarded frame")
        check(stray.accept(packet(102, 0, 4)) == Data([3]),
              "one stray out-of-window packet does not move the accepted sequence")

        print("Opus transport: \(checks - failures)/\(checks) passed")
        if failures > 0 { exit(1) }
    }
}
