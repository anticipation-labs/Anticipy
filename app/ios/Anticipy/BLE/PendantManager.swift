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
        /// The owner asked, and we are waiting for the Bluetooth radio itself to
        /// finish coming up. Distinct from `.searching` on purpose: "Looking for
        /// pendant" is not true yet, and docs ex 88 is about the app never
        /// describing a state it is not actually in.
        case warmingUp
        case off, unavailable, searching, connecting, connected, reconnecting

        /// What a person may read. `rawValue` is an identifier, not English:
        /// SettingsView rendered `rawValue.capitalized` straight onto the
        /// screen, so this enum's spelling was the UI copy - "Warmingup",
        /// "Reconnecting". docs ex 83: no ids, no status words, no raw strings
        /// ever rendered, and it must be impossible rather than merely avoided.
        var plainWords: String {
            switch self {
            case .warmingUp: return "Turning on Bluetooth"
            case .off: return "Not connected"
            case .unavailable: return "Bluetooth off"
            case .searching: return "Looking for your pendant"
            case .connecting: return "Connecting"
            case .connected: return "Connected"
            case .reconnecting: return "Reconnecting"
            }
        }
    }

    @Published var state: ConnectionState = .off
    @Published var deviceName: String?
    @Published var battery: Int?
    @Published var rssi: Int?
    @Published var hasPairedPendant = UserDefaults.standard.string(forKey: savedUUIDKey) != nil

    /// Reassembled Opus frames are handed to the audio pipeline.
    var onOpusFrame: ((Data) -> Void)?

    /// Fired whenever the assembler measures airtime nobody captured — a
    /// packet-index jump on the live stream. The wall-clock gap of a full
    /// disconnect is a different number with a different owner: the session
    /// marks it from reconnect time. Both exist so the transcript can carry
    /// a mark instead of a model's invention.
    var onGap: ((TimeInterval) -> Void)?

    private var central: CBCentralManager?
    private var peripheral: CBPeripheral?
    private var frameAssembler = OpusFrameAssembler()
    private var manuallyDisconnected = false
    private var rssiTimer: Timer?
    /// Did the owner ask to connect on this launch? Survives the radio warming
    /// up, which is the whole fix for the dead first tap (PendantRadioPolicy).
    private var connectRequested = false

    override init() {
        super.init()
        // Only build the Bluetooth stack for someone who actually HAS a
        // pendant. Constructing it unconditionally made a system Bluetooth
        // permission alert the literal first thing a new person saw — asking
        // for a radio so hardware they don't own could "hear your day", on top
        // of the welcome screen. State restoration still works for owners,
        // because they take this branch on every launch.
        if hasPairedPendant { ensureCentral() }
    }

    /// Build the central on first real need. Restoration requires it to exist
    /// early in the launch, so this is a GATE (owners construct in init), not
    /// a deferral for people who have a pendant.
    private func ensureCentral() {
        guard central == nil else { return }
        central = CBCentralManager(delegate: self, queue: nil, options: [
            CBCentralManagerOptionRestoreIdentifierKey: "anticipy.pendant",
            CBCentralManagerOptionShowPowerAlertKey: true,
        ])
    }

    // MARK: - Public API

    func startScan() {
        // The user asked for this, so NOW the Bluetooth prompt is expected.
        connectRequested = true
        manuallyDisconnected = false
        ensureCentral()
        // No guard-and-return here. `ensureCentral()` may have just built the
        // central, in which case its state is `.unknown` for a moment and the
        // old code silently dropped this request on the floor (docs ex 87).
        applyRadio()
    }

    func disconnect() {
        manuallyDisconnected = true
        // Disarm the standing request too, or the next radio state callback
        // would helpfully start scanning again for someone who just asked it
        // to stop — a Stop that does not stay stopped.
        connectRequested = false
        stopRssiKeepAlive()
        frameAssembler.discardCurrentFrame()
        if let p = peripheral { central?.cancelPeripheralConnection(p) }
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

    /// Read the radio, ask the policy what that means, and do it.
    ///
    /// One funnel for both entry points - the owner's tap and the radio's own
    /// state callback - so a request made before the radio was ready is acted
    /// on the moment it becomes ready, instead of being forgotten.
    private func applyRadio() {
        let power: PendantRadioPolicy.Power
        switch central?.state {
        case .some(.poweredOn): power = .poweredOn
        case .some(.poweredOff): power = .poweredOff
        case .some(.unauthorized): power = .unauthorized
        case .some(.unsupported): power = .unsupported
        case .some(.resetting): power = .resetting
        default: power = .unknown
        }

        switch PendantRadioPolicy.next(power: power,
                                       connectRequested: connectRequested,
                                       hasPairedPendant: hasPairedPendant) {
        case .idle:
            break
        case .waitingForRadio:
            // NOT `.searching` — we have not started looking for a pendant yet,
            // we are waiting for the radio to finish waking up. Saying "Looking
            // for pendant" here would be the app describing a state it is not
            // in, which is the whole of docs ex 88.
            state = .warmingUp
        case .unavailable:
            state = .unavailable
        case .scanNow:
            state = .searching
            central?.scanForPeripherals(withServices: [Self.serviceUUID])
        case .connectSavedNow:
            connectToSavedPendant()
        }
    }


    // MARK: - Internals

    /// Reconnect to the remembered pendant without scanning. iOS parks the
    /// connect request in the Bluetooth chipset until the device appears.
    private func connectToSavedPendant() {
        guard let saved = UserDefaults.standard.string(forKey: Self.savedUUIDKey),
              let uuid = UUID(uuidString: saved),
              let p = central?.retrievePeripherals(withIdentifiers: [uuid]).first
        else {
            startScan()
            return
        }
        peripheral = p
        p.delegate = self
        deviceName = p.name
        state = .connecting
        central?.connect(p)
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
        // One funnel, shared with startScan(). This used to be
        //
        //     guard central.state == .poweredOn else { state = .unavailable; return }
        //     if hasPairedPendant { connectToSavedPendant() }
        //
        // which had both bugs in four lines: a first-time owner's tap was never
        // honoured when the radio came up (only remembered pendants were), and
        // the transient `.unknown`/`.resetting` states on the way up were
        // reported to the person as "unavailable" (docs ex 87, ex 88).
        applyRadio()
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
        frameAssembler.discardCurrentFrame()
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
            self?.central?.connect(p)
        }
    }

    func centralManager(_ central: CBCentralManager, didDisconnectPeripheral p: CBPeripheral, error: Error?) {
        stopRssiKeepAlive()
        frameAssembler.discardCurrentFrame()
        guard !manuallyDisconnected else { return }
        state = .reconnecting
        // Re-issue immediately: iOS holds the request at the chipset level and
        // completes it the moment the pendant is back in range.
        DispatchQueue.main.asyncAfter(deadline: .now() + .milliseconds(200)) { [weak self] in
            self?.central?.connect(p)
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
            if let frame = frameAssembler.accept(data) { onOpusFrame?(frame) }
            let gap = frameAssembler.takeGapSeconds()
            if gap > 0 { onGap?(gap) }
        case Self.batteryLevelUUID:
            if let level = data.first { battery = Int(level) }
        default:
            break
        }
    }
}
