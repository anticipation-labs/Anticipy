import Foundation

/// Reassembles the pendant's BLE notifications into bounded Opus frames.
///
/// Wire format: packet index (little-endian UInt16), intra-frame counter, then
/// payload. Counter zero starts a new Opus frame. A missing or reordered BLE
/// packet invalidates only the current frame; the next counter-zero packet is
/// a clean recovery point.
struct OpusFrameAssembler {
    static let maximumFrameBytes = 4096

    /// Omi-wire audio packets carry 160 samples at 16 kHz — one packet is
    /// 10 ms of airtime. A packet-index jump is therefore a gap with a
    /// measurable length, and the length is honest arithmetic, not a guess.
    static let packetSeconds: TimeInterval = 0.010

    private var buffer = Data()
    private var frameIsValid = false
    private var previousPacketIndex: UInt16?
    private var expectedCounter: UInt8 = 0

    private(set) var droppedFrames = 0
    private(set) var peakBufferedBytes = 0

    /// Airtime nobody captured, accumulated since the last drain. This is
    /// the number the gap law exists for: the transcript must carry a
    /// marker of this length, never a model's invention across the silence.
    private(set) var gapSeconds: TimeInterval = 0

    /// Hands over and clears the accumulated gap. Draining, not reading —
    /// a gap reported twice is a lie told once and repeated.
    mutating func takeGapSeconds() -> TimeInterval {
        let gap = gapSeconds
        gapSeconds = 0
        return gap
    }

    /// Accept one full GATT notification. Returns the previous complete frame
    /// when this packet starts the next one.
    mutating func accept(_ packet: Data) -> Data? {
        guard packet.count >= 3 else {
            invalidateCurrentFrame()
            return nil
        }
        let index = UInt16(packet[0]) | (UInt16(packet[1]) << 8)
        let counter = packet[2]
        let payload = packet.dropFirst(3)

        let packetIsContinuous = previousPacketIndex.map {
            index == $0 &+ 1
        } ?? true
        if !packetIsContinuous, let prev = previousPacketIndex {
            // The 16-bit counter wrapped — the distance across the wrap is
            // what the arithmetic below recovers. A reorder reads as a jump
            // too, and gets counted the same way: it IS airtime that never
            // arrived at this decoder, whatever the radio did with it.
            var delta = Int(index) - Int(prev)
            if delta <= 0 { delta += 65536 }
            if delta > 1 {
                gapSeconds += TimeInterval(delta - 1) * Self.packetSeconds
            }
        }
        previousPacketIndex = index

        if counter == 0 {
            let completed = frameIsValid && !buffer.isEmpty ? buffer : nil
            buffer = Data()
            frameIsValid = true
            expectedCounter = 1
            append(payload)
            return completed
        }

        guard frameIsValid, packetIsContinuous, counter == expectedCounter else {
            invalidateCurrentFrame()
            return nil
        }
        expectedCounter &+= 1
        append(payload)
        return nil
    }

    /// Hand out the final frame when the stream closes normally.
    mutating func finish() -> Data? {
        defer {
            buffer = Data()
            frameIsValid = false
            previousPacketIndex = nil
            expectedCounter = 0
        }
        return frameIsValid && !buffer.isEmpty ? buffer : nil
    }

    /// A BLE disconnect does not prove the current codec frame is complete.
    /// Drop it and clear packet continuity so the first frame after reconnect
    /// can never emit stale bytes from the previous radio session.
    mutating func discardCurrentFrame() {
        invalidateCurrentFrame()
        previousPacketIndex = nil
    }

    private mutating func append(_ payload: Data.SubSequence) {
        guard frameIsValid else { return }
        guard buffer.count + payload.count <= Self.maximumFrameBytes else {
            invalidateCurrentFrame()
            return
        }
        buffer.append(contentsOf: payload)
        peakBufferedBytes = max(peakBufferedBytes, buffer.count)
    }

    private mutating func invalidateCurrentFrame() {
        // Count the frame at the point it becomes unusable. Clearing the
        // buffer is what keeps a broken/hostile stream memory-bounded, so the
        // next counter-zero packet cannot infer this drop after the fact.
        if frameIsValid && !buffer.isEmpty { droppedFrames += 1 }
        frameIsValid = false
        buffer = Data()
        expectedCounter = 0
    }
}
