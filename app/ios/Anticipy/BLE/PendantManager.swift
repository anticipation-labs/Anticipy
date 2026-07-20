import CoreBluetooth
import Foundation

/// Connects to the Anticipy pendant over BLE and streams its Opus audio.
/// Protocol verified on real hardware: GATT service 19B10000, audio notifies on
/// 19B10001 (3-byte header: packet index lo/hi + intra-frame counter, then Opus
/// payload; a new frame starts when the counter is 0), codec id on 19B10002
/// (20 = Opus 16kHz mono), standard Battery Service 0x180F for percentage.
final class PendantManager: NSObject, ObservableObject {
    static let serviceUUID = CBUUID(string: "19B10000-E8F2-537E-4F6C-D104768A1214")
    static let audioUUID = CBUUID(string: "19B10001-E8F2-537E-4F6C-D104768A1214")
    static let codecUUID = CBUUID(string: "19B10002-E8F2-537E-4F6C-D104768A1214")
    static let batteryServiceUUID = CBUUID(string: "180F")
    static let batteryLevelUUID = CBUUID(string: "2A19")

    @Published var state: String = "off"
    @Published var deviceName: String?
    @Published var battery: Int?

    /// Reassembled Opus frames are handed to the audio pipeline.
    var onOpusFrame: ((Data) -> Void)?

    private var central: CBCentralManager!
    private var peripheral: CBPeripheral?
    private var frameBuffer = Data()

    override init() {
        super.init()
        // Restoration identifier keeps the BLE link alive in the background
        // (requires the bluetooth-central UIBackgroundModes entitlement).
        central = CBCentralManager(delegate: self, queue: nil, options: [
            CBCentralManagerOptionRestoreIdentifierKey: "anticipy.pendant",
        ])
    }

    func startScan() {
        guard central.state == .poweredOn else { return }
        state = "scanning"
        central.scanForPeripherals(withServices: [Self.serviceUUID])
    }
}

extension PendantManager: CBCentralManagerDelegate, CBPeripheralDelegate {
    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        if central.state == .poweredOn { startScan() } else { state = "bluetooth unavailable" }
    }

    func centralManager(_ central: CBCentralManager, willRestoreState dict: [String: Any]) {
        if let restored = (dict[CBCentralManagerRestoredStatePeripheralsKey] as? [CBPeripheral])?.first {
            peripheral = restored
            restored.delegate = self
        }
    }

    func centralManager(_ central: CBCentralManager, didDiscover p: CBPeripheral,
                        advertisementData: [String: Any], rssi RSSI: NSNumber) {
        peripheral = p
        deviceName = p.name
        central.stopScan()
        state = "connecting"
        central.connect(p)
    }

    func centralManager(_ central: CBCentralManager, didConnect p: CBPeripheral) {
        state = "connected"
        p.delegate = self
        p.discoverServices([Self.serviceUUID, Self.batteryServiceUUID])
    }

    func centralManager(_ central: CBCentralManager, didDisconnectPeripheral p: CBPeripheral, error: Error?) {
        state = "reconnecting"
        central.connect(p) // auto-reconnect; pendant streams again on link-up
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
