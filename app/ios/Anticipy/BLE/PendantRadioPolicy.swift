import Foundation

/// What to do when the Bluetooth radio reports a state, given what the owner
/// has asked for.
///
/// Pure Foundation on purpose — no CoreBluetooth — so it compiles and runs in a
/// second with no simulator, no radio and no pendant. Same reason
/// `TranscriptFlushPolicy` was lifted out of `PhoneListener`: a decision tangled
/// with a system framework is a decision nobody can test.
///
/// -- The two failures this exists to prevent -----------------------------
///
/// 1. THE DEAD FIRST TAP (docs ex 87). `startScan()` used to read:
///
///        ensureCentral()
///        guard central?.state == .poweredOn else { return }
///
///    `ensureCentral()` constructs the CBCentralManager on that very first tap,
///    and CoreBluetooth publishes `.poweredOn` ASYNCHRONOUSLY afterwards. So on
///    a first tap the guard was always false, the function returned, the request
///    was forgotten, and `state` never left `.off`. Nothing on screen changed.
///    The second tap worked, which is exactly what makes it a demo killer: it
///    looks like the person mis-tapped. The request is remembered now, and the
///    radio coming up is what starts the scan.
///
/// 2. WARM-UP REPORTED AS BROKEN (docs ex 88). The state callback used to read:
///
///        guard central.state == .poweredOn else { state = .unavailable; return }
///
///    which labels `.unknown` and `.resetting` — the normal transient states on
///    the way up — as "unavailable". The app would say Bluetooth cannot be used
///    during the half-second it is being switched on. `.unknown` is "ask again
///    in a moment"; only off/unauthorized/unsupported are genuinely unavailable.
enum PendantRadioPolicy {
    /// Mirrors `CBManagerState` so this file needs no CoreBluetooth import.
    enum Power: Equatable {
        case unknown, resetting, unsupported, unauthorized, poweredOff, poweredOn
    }

    /// What the manager should do next, and what the person should see.
    enum Next: Equatable {
        /// Radio is not ready and nobody asked for anything. Stay quiet.
        case idle
        /// The owner asked and the radio is still coming up. Spinner, and the
        /// truth: we are waiting on the radio, not on them.
        case waitingForRadio
        /// Genuinely cannot proceed: switched off, or refused by permission.
        case unavailable
        /// Radio is up and there is no remembered pendant — look for one.
        case scanNow
        /// Radio is up and we know which pendant is theirs — reconnect without
        /// scanning, which iOS parks in the chipset until it is in range.
        case connectSavedNow
    }

    /// - Parameters:
    ///   - power: what the radio last reported.
    ///   - connectRequested: has the owner tapped connect on this launch?
    ///   - hasPairedPendant: is there a remembered pendant to go straight to?
    static func next(power: Power,
                     connectRequested: Bool,
                     hasPairedPendant: Bool) -> Next {
        switch power {
        case .poweredOn:
            // A remembered pendant is always worth reconnecting to, tap or no
            // tap — that is what makes it appear by itself on launch.
            if hasPairedPendant { return .connectSavedNow }
            return connectRequested ? .scanNow : .idle

        case .poweredOff, .unauthorized, .unsupported:
            // Worth saying even when they never asked: a pendant owner whose
            // Bluetooth is off should be told, not left with a silent screen.
            return .unavailable

        case .unknown, .resetting:
            // Transient. If they asked, this is the spinner; if they did not,
            // there is nothing to report yet.
            return connectRequested || hasPairedPendant ? .waitingForRadio : .idle
        }
    }
}
