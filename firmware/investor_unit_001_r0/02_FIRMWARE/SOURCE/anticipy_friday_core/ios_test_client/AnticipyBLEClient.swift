import CoreBluetooth
import Foundation

/// Minimal CoreBluetooth transport inherited from the founder-EVT firmware.
/// For Friday Core, prefer the complete foreground app in `ios_client_stage`;
/// its UI omits disabled storage, button, and haptic features.
///
/// This file deliberately stops at raw Opus frames. Feed each frame separately
/// to Anticipy's streaming endpoint or to a libopus decoder configured for
/// 16 kHz, mono, 160 samples (10 ms) per frame.
final class AnticipyBLEClient: NSObject {
    static let audioService = CBUUID(string: "19B10000-E8F2-537E-4F6C-D104768A1214")
    static let audioData = CBUUID(string: "19B10001-E8F2-537E-4F6C-D104768A1214")
    static let audioCodec = CBUUID(string: "19B10002-E8F2-537E-4F6C-D104768A1214")

    static let storageService = CBUUID(string: "30295780-4301-EABD-2904-2849ADFEAE43")
    static let storageCommand = CBUUID(string: "30295781-4301-EABD-2904-2849ADFEAE43")
    static let storageStatus = CBUUID(string: "30295782-4301-EABD-2904-2849ADFEAE43")

    static let buttonService = CBUUID(string: "23BA7924-0000-1000-7450-346EAC492E92")
    static let buttonData = CBUUID(string: "23BA7925-0000-1000-7450-346EAC492E92")

    static let hapticService = CBUUID(string: "CAB1AB95-2EA5-4F4D-BB56-874B72CFC984")
    static let hapticCommand = CBUUID(string: "CAB1AB96-2EA5-4F4D-BB56-874B72CFC984")

    static let sdRecordBytes = 440

    var onState: ((String) -> Void)?
    var onError: ((String) -> Void)?
    var onLiveOpusFrame: ((Data) -> Void)?
    var onBacklogOpusFrame: ((Data) -> Void)?
    var onBacklogProgress: ((_ committedBytes: UInt32, _ totalBytes: UInt32) -> Void)?
    var onButton: ((UInt8) -> Void)?

    private lazy var central = CBCentralManager(delegate: self, queue: .main)
    private var peripheral: CBPeripheral?
    private var audioDataCharacteristic: CBCharacteristic?
    private var codecCharacteristic: CBCharacteristic?
    private var storageCommandCharacteristic: CBCharacteristic?
    private var storageStatusCharacteristic: CBCharacteristic?
    private var hapticCharacteristic: CBCharacteristic?

    private var storageNotificationsReady = false
    private var pendingBackfill = false
    private var backlogBuffer = Data()
    private var backlogTotal: UInt32 = 0
    private var committedOffset: UInt32 = 0
    private var sinkURL: URL?
    private var sinkHandle: FileHandle?

    private var liveFrameID: UInt16?
    private var liveExpectedFragment: UInt8 = 0
    private var liveFrame = Data()

    override init() {
        super.init()
        _ = central
    }

    deinit {
        try? sinkHandle?.close()
    }

    func start() {
        guard central.state == .poweredOn else {
            onState?("Waiting for Bluetooth")
            return
        }
        central.scanForPeripherals(withServices: [Self.audioService], options: [
            CBCentralManagerScanOptionAllowDuplicatesKey: false,
        ])
        onState?("Looking for Anticipy Friday Core")
    }

    func stop() {
        pendingBackfill = false
        if let peripheral {
            central.cancelPeripheralConnection(peripheral)
        }
        central.stopScan()
    }

    /// The sink is raw concatenated 440-byte SD records. It is fsynced before
    /// committedOffset advances, which makes reconnect/resume crash-safe at a
    /// record boundary.
    func setBacklogSink(_ url: URL) throws {
        try sinkHandle?.close()
        sinkHandle = nil
        sinkURL = url

        try FileManager.default.createDirectory(
            at: url.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        if !FileManager.default.fileExists(atPath: url.path) {
            guard FileManager.default.createFile(atPath: url.path, contents: nil) else {
                throw ClientError.cannotCreateSink
            }
        }

        let handle = try FileHandle(forUpdating: url)
        let size = try handle.seekToEnd()
        let completeSize = size - (size % UInt64(Self.sdRecordBytes))
        if completeSize != size {
            try handle.truncate(atOffset: completeSize)
        }
        guard completeSize <= UInt64(UInt32.max) else {
            throw ClientError.sinkTooLarge
        }
        committedOffset = UInt32(completeSize)
        sinkHandle = handle
    }

    /// Subscribe first, read the device's current file size, then request bytes
    /// from the last locally fsynced 440-byte boundary.
    func requestBackfill() {
        guard sinkHandle != nil else {
            onError?("Choose a backlog sink file before starting backfill")
            return
        }
        pendingBackfill = true
        guard let peripheral, let status = storageStatusCharacteristic else {
            onState?("Backfill queued until storage is discovered")
            return
        }
        peripheral.readValue(for: status)
    }

    func stopBackfill() {
        pendingBackfill = false
        writeStorageCommand(command: 3, file: 1, offset: 0)
    }

    func playHaptic(level: UInt8) {
        guard (1...3).contains(level), let peripheral, let hapticCharacteristic else {
            return
        }
        peripheral.writeValue(Data([level]), for: hapticCharacteristic, type: .withResponse)
    }

    private func beginBackfillIfReady() {
        guard pendingBackfill, storageNotificationsReady, backlogTotal > 0 else { return }
        if committedOffset > backlogTotal {
            do {
                try sinkHandle?.truncate(atOffset: 0)
                try sinkHandle?.seek(toOffset: 0)
                committedOffset = 0
            } catch {
                onError?("Could not reset stale backlog sink: \(error)")
                return
            }
        }
        backlogBuffer.removeAll(keepingCapacity: true)
        writeStorageCommand(command: 0, file: 1, offset: committedOffset)
        onState?("Backfill requested at byte \(committedOffset)")
    }

    private func writeStorageCommand(command: UInt8, file: UInt8, offset: UInt32) {
        guard let peripheral, let characteristic = storageCommandCharacteristic else { return }
        let commandBytes = Data([
            command,
            file,
            UInt8((offset >> 24) & 0xff),
            UInt8((offset >> 16) & 0xff),
            UInt8((offset >> 8) & 0xff),
            UInt8(offset & 0xff),
        ])
        peripheral.writeValue(commandBytes, for: characteristic, type: .withResponse)
    }

    private func consumeLiveNotification(_ data: Data) {
        guard data.count >= 4 else {
            onError?("Short live-audio notification")
            return
        }
        let id = UInt16(data[data.startIndex]) | (UInt16(data[data.startIndex + 1]) << 8)
        let fragment = data[data.startIndex + 2]
        let payload = data.dropFirst(3)

        if liveFrameID != id {
            flushLiveFrame()
            liveFrameID = id
            liveExpectedFragment = 0
        }
        guard fragment == liveExpectedFragment else {
            onError?("Dropped/out-of-order live fragment for frame \(id)")
            liveFrame.removeAll(keepingCapacity: true)
            liveFrameID = nil
            return
        }
        liveFrame.append(contentsOf: payload)
        liveExpectedFragment &+= 1

        // The wire format has a frame ID and fragment index, but no explicit
        // "last fragment" bit.  A frame is complete only when the next frame
        // ID arrives (or the link closes).  Flushing fragment zero immediately
        // corrupts any Opus packet that happens to span multiple ATT values.
    }

    private func flushLiveFrame() {
        if !liveFrame.isEmpty {
            onLiveOpusFrame?(liveFrame)
        }
        liveFrame.removeAll(keepingCapacity: true)
        liveFrameID = nil
        liveExpectedFragment = 0
    }

    private func consumeStorageNotification(_ data: Data) {
        guard !data.isEmpty else { return }
        if data.count == 1 {
            switch data[data.startIndex] {
            case 0:
                onState?("Backfill accepted")
            case 100:
                pendingBackfill = false
                if backlogBuffer.isEmpty {
                    onState?("Backfill complete")
                } else {
                    onError?("Backfill ended with an incomplete 440-byte record")
                }
            case 3: onError?("Backfill file number is invalid")
            case 4: onState?("No offline audio")
            case 5: onError?("Backfill offset is beyond the file")
            case 6: onError?("Backfill command is invalid")
            case 200: onState?("Offline audio deleted")
            default: onError?("Unknown storage status \(data[data.startIndex])")
            }
            return
        }

        backlogBuffer.append(data)
        while backlogBuffer.count >= Self.sdRecordBytes {
            let block = Data(backlogBuffer.prefix(Self.sdRecordBytes))
            backlogBuffer.removeFirst(Self.sdRecordBytes)
            do {
                try commitBacklogBlock(block)
            } catch {
                pendingBackfill = false
                stopBackfill()
                onError?("Could not persist backlog record: \(error)")
                return
            }
        }
    }

    private func commitBacklogBlock(_ block: Data) throws {
        guard block.count == Self.sdRecordBytes, let sinkHandle else {
            throw ClientError.badRecord
        }
        let frames = try Self.parseSDRecord(block)
        try sinkHandle.seek(toOffset: UInt64(committedOffset))
        try sinkHandle.write(contentsOf: block)
        try sinkHandle.synchronize()
        committedOffset += UInt32(Self.sdRecordBytes)
        for frame in frames {
            onBacklogOpusFrame?(frame)
        }
        onBacklogProgress?(committedOffset, backlogTotal)
    }

    static func parseSDRecord(_ block: Data) throws -> [Data] {
        guard block.count == sdRecordBytes else { throw ClientError.badRecord }
        var frames: [Data] = []
        var position = 0
        while position < block.count {
            let count = Int(block[block.startIndex + position])
            if count == 0 { break }
            let start = position + 1
            let end = start + count
            guard end <= block.count else { throw ClientError.badRecord }
            frames.append(block.subdata(in: start..<end))
            position = end
        }
        return frames
    }

    private static func littleEndianUInt32(_ data: Data, at offset: Int) -> UInt32 {
        UInt32(data[data.startIndex + offset]) |
            (UInt32(data[data.startIndex + offset + 1]) << 8) |
            (UInt32(data[data.startIndex + offset + 2]) << 16) |
            (UInt32(data[data.startIndex + offset + 3]) << 24)
    }

    enum ClientError: Error {
        case badRecord
        case cannotCreateSink
        case sinkTooLarge
    }
}

extension AnticipyBLEClient: CBCentralManagerDelegate {
    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        if central.state == .poweredOn {
            start()
        } else {
            onState?("Bluetooth state: \(central.state.rawValue)")
        }
    }

    func centralManager(
        _ central: CBCentralManager,
        didDiscover peripheral: CBPeripheral,
        advertisementData: [String: Any],
        rssi RSSI: NSNumber
    ) {
        central.stopScan()
        self.peripheral = peripheral
        peripheral.delegate = self
        central.connect(peripheral, options: nil)
        onState?("Connecting to \(peripheral.name ?? "Anticipy")")
    }

    func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) {
        peripheral.discoverServices([
            Self.audioService,
            Self.storageService,
            Self.buttonService,
            Self.hapticService,
        ])
        onState?("Connected; discovering services")
    }

    func centralManager(
        _ central: CBCentralManager,
        didFailToConnect peripheral: CBPeripheral,
        error: Error?
    ) {
        onError?("Connect failed: \(error?.localizedDescription ?? "unknown")")
        start()
    }

    func centralManager(
        _ central: CBCentralManager,
        didDisconnectPeripheral peripheral: CBPeripheral,
        error: Error?
    ) {
        flushLiveFrame()
        storageNotificationsReady = false
        onState?("Disconnected; looking again")
        start()
    }
}

extension AnticipyBLEClient: CBPeripheralDelegate {
    func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        if let error {
            onError?("Service discovery failed: \(error)")
            return
        }
        for service in peripheral.services ?? [] {
            switch service.uuid {
            case Self.audioService:
                peripheral.discoverCharacteristics([Self.audioData, Self.audioCodec], for: service)
            case Self.storageService:
                peripheral.discoverCharacteristics([Self.storageCommand, Self.storageStatus], for: service)
            case Self.buttonService:
                peripheral.discoverCharacteristics([Self.buttonData], for: service)
            case Self.hapticService:
                peripheral.discoverCharacteristics([Self.hapticCommand], for: service)
            default:
                break
            }
        }
    }

    func peripheral(
        _ peripheral: CBPeripheral,
        didDiscoverCharacteristicsFor service: CBService,
        error: Error?
    ) {
        if let error {
            onError?("Characteristic discovery failed: \(error)")
            return
        }
        for characteristic in service.characteristics ?? [] {
            switch characteristic.uuid {
            case Self.audioData:
                audioDataCharacteristic = characteristic
                peripheral.setNotifyValue(true, for: characteristic)
            case Self.audioCodec:
                codecCharacteristic = characteristic
                // This read asks iOS to establish an L2 encrypted link.
                // Bonding is supported by the firmware but is not required.
                peripheral.readValue(for: characteristic)
            case Self.storageCommand:
                storageCommandCharacteristic = characteristic
                peripheral.setNotifyValue(true, for: characteristic)
            case Self.storageStatus:
                storageStatusCharacteristic = characteristic
            case Self.buttonData:
                peripheral.setNotifyValue(true, for: characteristic)
            case Self.hapticCommand:
                hapticCharacteristic = characteristic
            default:
                break
            }
        }
    }

    func peripheral(
        _ peripheral: CBPeripheral,
        didUpdateNotificationStateFor characteristic: CBCharacteristic,
        error: Error?
    ) {
        if let error {
            onError?("Notification setup failed for \(characteristic.uuid): \(error)")
            return
        }
        if characteristic.uuid == Self.storageCommand {
            storageNotificationsReady = characteristic.isNotifying
            if pendingBackfill, let status = storageStatusCharacteristic {
                peripheral.readValue(for: status)
            }
        }
    }

    func peripheral(
        _ peripheral: CBPeripheral,
        didUpdateValueFor characteristic: CBCharacteristic,
        error: Error?
    ) {
        if let error {
            onError?("Read/notify failed for \(characteristic.uuid): \(error)")
            return
        }
        guard let data = characteristic.value else { return }
        switch characteristic.uuid {
        case Self.audioData:
            consumeLiveNotification(data)
        case Self.audioCodec:
            if data.first == 20 {
                onState?("Opus 16-kHz stream ready")
            } else {
                onError?("Unexpected codec ID \(data.first.map { String($0) } ?? "none")")
            }
        case Self.storageStatus:
            guard data.count >= 8 else {
                onError?("Short storage status")
                return
            }
            backlogTotal = Self.littleEndianUInt32(data, at: 0)
            beginBackfillIfReady()
        case Self.storageCommand:
            consumeStorageNotification(data)
        case Self.buttonData:
            if let event = data.first { onButton?(event) }
        default:
            break
        }
    }
}
