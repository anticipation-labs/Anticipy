import CoreBluetooth
import Foundation

/// Connects to the Anticipy pendant over BLE and streams its Opus audio.
///
/// Protocol verified on real hardware: GATT service 19B10000, audio notifies on
/// 19B10001 (3-byte header: packet index lo/hi + intra-frame counter, then Opus
/// payload; a new frame starts when the counter is 0), codec id on 19B10002
/// (20 = Opus 16kHz mono), standard Battery Service 0x180F for percentage.
///
/// Connection stability model (same as Omi's production manager):
/// - CoreBluetooth state restoration relaunches the app after iOS kills it and
///   hands back the live peripheral (willRestoreState).
/// - The last paired peripheral UUID is persisted; on every power-on we
///   retrieve it directly (no scan needed) and issue a connect that iOS parks
///   at the chipset level until the pendant is in range — zero battery cost.
/// - Unexpected disconnects immediately re-issue connect (auto-reconnect).
/// - A periodic RSSI read keeps the link warm and exposes signal health.
final class PendantManager: NSObject, ObservableObject {
    static let serviceUUID = CBUUID(string: "19B10000-E8F2-537E-4F6C-D104768A1214")
    static let audioUUID = CBUUID(string: "19B10001-E8F2-537E-4F6C-D104768A1214")
    static let codecUUID = CBUUID(string: "19B10002-E8F2-537E-4F6C-D104768A1214")
    static let batteryServiceUUID = CBUUID(string: "180F")
    static let batteryLevelUUID = CBUUID(string: "2A19")
    private static let savedUUIDKey = "anticipy.pendant.uuid"

    enum ConnectionState: String {
        case off, unavailable, searching, connecting, connected, reconnecting
    }

    @Published var state: ConnectionState = .off
    @Published var deviceName: String?
    @Published var battery: Int?
    @Published var rssi: Int?
    @Published var hasPairedPendant = UserDefaults.standard.string(forKey: savedUUIDKey) != nil

    /// Reassembled Opus frames are handed to the audio pipeline.
    var onOpusFrame: ((Data) -> Void)?

    private var central: CBCentralManager!
    private var peripheral: CBPeripheral?
    private var frameBuffer = Data()
    private var manuallyDisconnected = false
    private var rssiTimer: Timer?

    override init() {
        super.init()
        central = CBCentralManager(delegate: self, queue: nil, options: [
            CBCentralManagerOptionRestoreIdentifierKey: "anticipy.pendant",
            CBCentralManagerOptionShowPowerAlertKey: true,
        ])
    }

    // MARK: - Public API

    func startScan() {
        guard central.state == .poweredOn else { return }
        manuallyDisconnected = false
        state = .searching
        central.scanForPeripherals(withServices: [Self.serviceUUID])
    }

    func disconnect() {
        manuallyDisconnected = true
        stopRssiKeepAlive()
        if let p = peripheral { central.cancelPeripheralConnection(p) }
        state = .off
    }

    func forgetPendant() {
        disconnect()
        UserDefaults.standard.removeObject(forKey: Self.savedUUIDKey)
        hasPairedPendant = false
        peripheral = nil
        deviceName = nil
        battery = nil
    }

    // MARK: - Internals

    /// Reconnect to the remembered pendant without scanning. iOS parks the
    /// connect request in the Bluetooth chipset until the device appears.
    private func connectToSavedPendant() {
        guard let saved = UserDefaults.standard.string(forKey: Self.savedUUIDKey),
              let uuid = UUID(uuidString: saved),
              let p = central.retrievePeripherals(withIdentifiers: [uuid]).first
        else {
            startScan()
            return
        }
        peripheral = p
        p.delegate = self
        deviceName = p.name
        state = .connecting
        central.connect(p)
    }

    private func rememberPendant(_ p: CBPeripheral) {
        UserDefaults.standard.set(p.identifier.uuidString, forKey: Self.savedUUIDKey)
        hasPairedPendant = true
    }

    private func startRssiKeepAlive(for p: CBPeripheral) {
        stopRssiKeepAlive()
        rssiTimer = Timer.scheduledTimer(withTimeInterval: 3.0, repeats: true) { [weak self, weak p] _ in
            guard let p, p.state == .connected else {
                self?.stopRssiKeepAlive()
                return
            }
            p.readRSSI()
        }
    }

    private func stopRssiKeepAlive() {
        rssiTimer?.invalidate()
        rssiTimer = nil
    }
}

extension PendantManager: CBCentralManagerDelegate, CBPeripheralDelegate {
    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        guard central.state == .poweredOn else {
            state = .unavailable
            return
        }
        if hasPairedPendant {
            connectToSavedPendant()
        }
    }

    func centralManager(_ central: CBCentralManager, willRestoreState dict: [String: Any]) {
        guard let restored = (dict[CBCentralManagerRestoredStatePeripheralsKey] as? [CBPeripheral])?.first
        else { return }
        peripheral = restored
        restored.delegate = self
        deviceName = restored.name
        if restored.state == .connected {
            state = .connected
            restored.discoverServices([Self.serviceUUID, Self.batteryServiceUUID])
        } else {
            state = .reconnecting
            central.connect(restored)
        }
    }

    func centralManager(_ central: CBCentralManager, didDiscover p: CBPeripheral,
                        advertisementData: [String: Any], rssi RSSI: NSNumber) {
        peripheral = p
        deviceName = p.name
        rssi = RSSI.intValue
        central.stopScan()
        state = .connecting
        central.connect(p)
    }

    func centralManager(_ central: CBCentralManager, didConnect p: CBPeripheral) {
        state = .connected
        rememberPendant(p)
        p.delegate = self
        p.discoverServices([Self.serviceUUID, Self.batteryServiceUUID])
        startRssiKeepAlive(for: p)
    }

    func centralManager(_ central: CBCentralManager, didFailToConnect p: CBPeripheral, error: Error?) {
        guard !manuallyDisconnected else { return }
        state = .reconnecting
        DispatchQueue.main.asyncAfter(deadline: .now() + .milliseconds(200)) { [weak self] in
            self?.central.connect(p)
        }
    }

    func centralManager(_ central: CBCentralManager, didDisconnectPeripheral p: CBPeripheral, error: Error?) {
        stopRssiKeepAlive()
        guard !manuallyDisconnected else { return }
        state = .reconnecting
        // Re-issue immediately: iOS holds the request at the chipset level and
        // completes it the moment the pendant is back in range.
        DispatchQueue.main.asyncAfter(deadline: .now() + .milliseconds(200)) { [weak self] in
            self?.central.connect(p)
        }
    }

    func peripheral(_ p: CBPeripheral, didDiscoverServices error: Error?) {
        for s in p.services ?? [] {
            p.discoverCharacteristics(nil, for: s)
        }
    }

    func peripheral(_ p: CBPeripheral, didDiscoverCharacteristicsFor service: CBService, error: Error?) {
        for c in service.characteristics ?? [] {
            switch c.uuid {
            case Self.audioUUID: p.setNotifyValue(true, for: c)
            case Self.batteryLevelUUID: p.setNotifyValue(true, for: c); p.readValue(for: c)
            case Self.codecUUID: p.readValue(for: c)
            default: break
            }
        }
    }

    func peripheral(_ p: CBPeripheral, didReadRSSI RSSI: NSNumber, error: Error?) {
        guard error == nil else { return }
        rssi = RSSI.intValue
    }

    func peripheral(_ p: CBPeripheral, didUpdateValueFor c: CBCharacteristic, error: Error?) {
        guard let data = c.value else { return }
        switch c.uuid {
        case Self.audioUUID:
            guard data.count > 3 else { return }
            let intraFrameCounter = data[2]
            let payload = data.subdata(in: 3 ..< data.count)
            if intraFrameCounter == 0 {
                if !frameBuffer.isEmpty { onOpusFrame?(frameBuffer) }
                frameBuffer = payload
            } else {
                frameBuffer.append(payload)
            }
        case Self.batteryLevelUUID:
            battery = Int(data[0])
        default:
            break
        }
    }
}
