import Foundation

/// Transport diagnostics, not an audio-duration estimate. Firmware increments
/// its sequence per BLE fragment (and when discarding an unsent frame), so
/// unavailable sequence slots cannot be converted to codec frames or seconds.
struct OpusTransportGap: Equatable {
    let missingNotifications: Int
    /// Buffered frames this assembler rejected, not all frames absent on wire.
    let discardedFrames: Int
}

/// Reassembles the pendant's BLE notifications into bounded Opus frames.
///
/// Wire format: packet index (little-endian UInt16), intra-frame counter, then
/// payload. Counter zero starts a new Opus frame. A missing or reordered BLE
/// packet invalidates only the current frame; the next counter-zero packet is
/// a clean recovery point.
struct OpusFrameAssembler {
    static let maximumFrameBytes = 4096

    private var buffer = Data()
    private var frameIsValid = false
    private var previousPacketIndex: UInt16?
    private var expectedCounter: UInt8 = 0

    private(set) var droppedFrames = 0
    private(set) var peakBufferedBytes = 0

    private var missingNotifications = 0
    private var discardedFramesSinceDrain = 0

    /// Hands over and clears the accumulated gap. Draining, not reading —
    /// a gap reported twice is a lie told once and repeated.
    mutating func takeGap() -> OpusTransportGap? {
        guard missingNotifications > 0 || discardedFramesSinceDrain > 0 else { return nil }
        let gap = OpusTransportGap(missingNotifications: missingNotifications,
                                   discardedFrames: discardedFramesSinceDrain)
        missingNotifications = 0
        discardedFramesSinceDrain = 0
        return gap
    }

    /// Accept one full GATT notification. Returns the previous complete frame
    /// when this packet starts the next one.
    mutating func accept(_ packet: Data) -> Data? {
        guard packet.count > 3 else {
            invalidateCurrentFrame()
            return nil
        }
        let index = UInt16(packet[0]) | (UInt16(packet[1]) << 8)
        let counter = packet[2]
        let payload = packet.dropFirst(3)

        var packetIsContinuous = true
        if let previous = previousPacketIndex {
            let delta = index &- previous
            // Serial-number ordering is only unambiguous within half the
            // UInt16 space. Duplicates, older packets and the exact half-range
            // ambiguity never advance the accepted high-water mark or prove
            // a frame complete. A reconnect explicitly resets that mark.
            // KNOWN OPEN DEFECT, recorded 2026-09-14 rather than patched on a
            // release day: one jump past this window (a firmware restart, a
            // long stall on the far side) leaves the mark where it is, so every
            // later in-order packet is rejected too until the 16-bit counter
            // laps -- discardCurrentFrame() on a BLE disconnect is the only
            // reset. The obvious repair (adopt the mark after two consecutive
            // out-of-window packets that continue each other) was written,
            // reviewed and REVERTED: "behind the mark" and "far ahead of the
            // mark" are the same delta in serial arithmetic, so two stale or
            // replayed packets re-origin the stream BACKWARD and the genuine
            // stream's next packet is then billed tens of thousands of phantom
            // missing notifications. Distinguishing the two needs a session
            // epoch on the wire, which belongs with the firmware work, not
            // here. See docs/EOD-READINESS-2026-09-13.md, 2026-09-14 addendum.
            guard delta > 0, delta < 32768 else {
                invalidateCurrentFrame()
                return nil
            }
            packetIsContinuous = delta == 1
            if !packetIsContinuous {
                // Even a counter-zero packet may follow a lost tail fragment.
                // Discard the old frame before accepting that recovery start.
                invalidateCurrentFrame()
                missingNotifications += Int(delta - 1)
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

    /// A BLE disconnect does not prove the current codec frame is complete.
    /// Drop it and clear packet continuity so the first frame after reconnect
    /// can never emit stale bytes from the previous radio session.
    mutating func discardCurrentFrame() {
        invalidateCurrentFrame()
        previousPacketIndex = nil
        // Pending diagnostics belong to this radio session. The manager
        // drains each observed notification synchronously; undelivered counts
        // must not be attributed to a later session or owner after reconnect.
        missingNotifications = 0
        discardedFramesSinceDrain = 0
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
        if frameIsValid && !buffer.isEmpty {
            droppedFrames += 1
            discardedFramesSinceDrain += 1
        }
        frameIsValid = false
        buffer = Data()
        expectedCounter = 0
    }
}
