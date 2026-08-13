import Foundation

private func queueRequire(_ condition: @autoclosure () -> Bool, _ message: String) {
    guard condition() else {
        fputs("FAIL: \(message)\n", stderr)
        exit(1)
    }
}

@main
struct BoundedOpusQueueStress {
    static func main() {
        var order = BoundedOpusQueue(capacity: 3)
        order.enqueue(Data([1]))
        order.enqueue(Data([2]))
        order.enqueue(Data([3]))
        order.enqueue(Data([4]))
        queueRequire(order.droppedFrames == 1, "a full queue records the dropped oldest frame")
        queueRequire(order.dequeue() == Data([2]), "overflow retains the newest frames in FIFO order")
        queueRequire(order.dequeue() == Data([3]), "FIFO order survives ring wraparound")
        queueRequire(order.dequeue() == Data([4]), "newest frame remains available")

        let totalFrames = 10_000_000
        var stress = BoundedOpusQueue()
        let frame = Data(repeating: 0x55, count: 80)
        let started = Date()
        for _ in 0..<totalFrames { stress.enqueue(frame) }
        let elapsed = Date().timeIntervalSince(started)

        queueRequire(stress.count == BoundedOpusQueue.defaultCapacity,
                "ten million queued frames never exceed the production cap")
        queueRequire(stress.peakCount == BoundedOpusQueue.defaultCapacity,
                "reported peak equals the hard cap")
        queueRequire(stress.droppedFrames == totalFrames - BoundedOpusQueue.defaultCapacity,
                "every overflow is accounted for")
        print("PASS BoundedOpusQueue: \(totalFrames) frames, peak \(stress.peakCount), " +
              "\(stress.droppedFrames) dropped, " + String(format: "%.2fs", elapsed))
    }
}
