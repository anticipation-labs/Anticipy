import Foundation

func packet(index: UInt16, counter: UInt8, payloadBytes: Int = 20) -> Data {
    var data = Data([UInt8(index & 0xff), UInt8(index >> 8), counter])
    data.append(Data(repeating: UInt8(index & 0xff), count: payloadBytes))
    return data
}

func require(_ condition: @autoclosure () -> Bool, _ message: String) {
    guard condition() else {
        fputs("FAIL: \(message)\n", stderr)
        exit(1)
    }
}

@main
struct OpusFrameAssemblerStress {
    static func main() {
        // Exact ordering and payload preservation.
        var basic = OpusFrameAssembler()
        require(basic.accept(packet(index: 10, counter: 0)) == nil, "first packet starts a frame")
        require(basic.accept(packet(index: 11, counter: 1)) == nil, "continuation stays buffered")
        let first = basic.accept(packet(index: 12, counter: 0))
        require(first?.count == 40, "next start emits exactly the prior frame")

        // A packet gap invalidates one frame and recovers at the next start.
        var gap = OpusFrameAssembler()
        _ = gap.accept(packet(index: 100, counter: 0))
        _ = gap.accept(packet(index: 102, counter: 1))
        require(gap.accept(packet(index: 103, counter: 0)) == nil, "corrupt frame never leaves the assembler")
        _ = gap.accept(packet(index: 104, counter: 1))
        require(gap.accept(packet(index: 105, counter: 0))?.count == 40, "next clean frame recovers")

        // A radio reconnect is a hard stream boundary. The partial frame
        // before it must never be emitted as the first frame of the new link.
        var reconnect = OpusFrameAssembler()
        _ = reconnect.accept(packet(index: 200, counter: 0))
        _ = reconnect.accept(packet(index: 201, counter: 1))
        reconnect.discardCurrentFrame()
        require(reconnect.accept(packet(index: 9, counter: 0)) == nil,
                "reconnect cannot emit stale bytes from the old radio session")
        _ = reconnect.accept(packet(index: 10, counter: 1))
        require(reconnect.accept(packet(index: 11, counter: 0))?.count == 40,
                "a new radio session recovers on its first complete frame")

        // Ten million real calls through the production type. Four BLE
        // notifications form one Opus frame. Periodic gaps and oversized
        // frames exercise recovery; neither may make memory grow with stream
        // length.
        let totalPackets = 10_000_000
        var stress = OpusFrameAssembler()
        var emitted = 0
        var index: UInt16 = 0
        let started = Date()
        for n in 0..<totalPackets {
            let counter = UInt8(n & 3)
            if n > 0 && n % 100_003 == 0 { index &+= 1 } // one lost BLE notification
            let payload = n > 0 && n % 777_777 == 0 ? 4_100 : 20
            if stress.accept(packet(index: index, counter: counter, payloadBytes: payload)) != nil {
                emitted += 1
            }
            index &+= 1
        }
        if stress.finish() != nil { emitted += 1 }
        let elapsed = Date().timeIntervalSince(started)

        require(emitted > 2_499_000, "clean frames survive a ten-million-packet stream")
        require(stress.droppedFrames > 0, "injected gaps are observed and dropped")
        require(stress.peakBufferedBytes <= OpusFrameAssembler.maximumFrameBytes,
                "buffer stays under the production hard cap")
        print("PASS OpusFrameAssembler: \(totalPackets) packets, \(emitted) frames, " +
              "\(stress.droppedFrames) dropped, peak \(stress.peakBufferedBytes) bytes, " +
              String(format: "%.2fs", elapsed))
    }
}
