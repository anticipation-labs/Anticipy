import Foundation

/// A fixed-capacity FIFO for live Opus frames. When the network falls behind,
/// keeping recent speech is more useful than allowing stale audio to consume
/// unbounded memory, so the oldest whole frame is dropped.
struct BoundedOpusQueue {
    static let defaultCapacity = 256

    let capacity: Int
    private var storage: [Data?]
    private var head = 0
    private(set) var count = 0
    private(set) var droppedFrames = 0
    private(set) var peakCount = 0

    init(capacity: Int = BoundedOpusQueue.defaultCapacity) {
        precondition(capacity > 0)
        self.capacity = capacity
        storage = Array(repeating: nil, count: capacity)
    }

    mutating func enqueue(_ frame: Data) {
        guard !frame.isEmpty else { return }
        if count == capacity {
            storage[head] = frame
            head = (head + 1) % capacity
            droppedFrames += 1
            return
        }

        let tail = (head + count) % capacity
        storage[tail] = frame
        count += 1
        peakCount = max(peakCount, count)
    }

    mutating func dequeue() -> Data? {
        guard count > 0 else { return nil }
        let frame = storage[head]
        storage[head] = nil
        head = (head + 1) % capacity
        count -= 1
        return frame
    }

    mutating func clear() {
        storage = Array(repeating: nil, count: capacity)
        head = 0
        count = 0
    }
}
