import Foundation

// Checks for PendantRadioPolicy — the decision behind "tap connect".
//
// Every case below is a line from the brief's examples or a bug that shipped.
// Plain executable, no XCTest, matching TranscriptCursorTests.swift: the point
// is that this runs in a second with no simulator and no radio.

var failures = 0

func check(_ name: String, _ got: PendantRadioPolicy.Next,
           _ want: PendantRadioPolicy.Next) {
    if got == want {
        print("  ok   \(name)")
    } else {
        print("  FAIL \(name): got \(got), want \(want)")
        failures += 1
    }
}
@main
struct PendantRadioPolicyTests {
    static func main() {
        run()
    }
}

// Top-level expressions are only legal in main.swift, so the body lives in a
// function and @main calls it — same shape as TranscriptCursorTests.swift.
func run() {
// ── ex 87: the dead first tap ────────────────────────────────────────────────
// The tap arrives while the central is still `.unknown`, because
// ensureCentral() built it microseconds ago. The old code returned here and
// forgot the request. The person saw nothing change.
check("first tap while the radio is still unknown shows a spinner",
      PendantRadioPolicy.next(power: .unknown, connectRequested: true,
                              hasPairedPendant: false),
      .waitingForRadio)

// ...and the moment the radio comes up, that remembered request is what starts
// the scan. This is the assertion that fails if the request is dropped again.
check("radio coming up after a tap starts the scan",
      PendantRadioPolicy.next(power: .poweredOn, connectRequested: true,
                              hasPairedPendant: false),
      .scanNow)

// The inverse: nobody asked, radio warming. Silence, not a spinner.
check("no tap and a warming radio stays quiet",
      PendantRadioPolicy.next(power: .unknown, connectRequested: false,
                              hasPairedPendant: false),
      .idle)

// ── ex 88: warm-up is not a fault ───────────────────────────────────────────
// `.resetting` is the radio cycling, not a broken one. Calling it unavailable
// is the app lying about its own state.
check("a resetting radio with a pending request is not called unavailable",
      PendantRadioPolicy.next(power: .resetting, connectRequested: true,
                              hasPairedPendant: false),
      .waitingForRadio)

// Genuinely unavailable, all three ways, and worth saying even unasked: a
// pendant owner with Bluetooth off should be told, not left with a blank screen.
for (name, power) in [("switched off", PendantRadioPolicy.Power.poweredOff),
                      ("permission refused", .unauthorized),
                      ("no BLE hardware", .unsupported)] {
    check("\(name) reports unavailable",
          PendantRadioPolicy.next(power: power, connectRequested: false,
                                  hasPairedPendant: true),
          .unavailable)
}

// ── the remembered pendant ──────────────────────────────────────────────────
// It reconnects on its own, tap or no tap — that is what makes it "appear by
// name" on launch (ex 86). And it must not go through a scan it does not need.
check("a remembered pendant reconnects without being asked",
      PendantRadioPolicy.next(power: .poweredOn, connectRequested: false,
                              hasPairedPendant: true),
      .connectSavedNow)

check("a remembered pendant reconnects rather than scanning even after a tap",
      PendantRadioPolicy.next(power: .poweredOn, connectRequested: true,
                              hasPairedPendant: true),
      .connectSavedNow)

// An owner whose radio is warming should see the spinner without tapping,
// because their pendant is expected to come back by itself.
check("a remembered pendant shows a spinner while the radio warms",
      PendantRadioPolicy.next(power: .unknown, connectRequested: false,
                              hasPairedPendant: true),
      .waitingForRadio)

// ── nothing to do ───────────────────────────────────────────────────────────
check("radio up, no pendant, no request: nothing happens",
      PendantRadioPolicy.next(power: .poweredOn, connectRequested: false,
                              hasPairedPendant: false),
      .idle)

print(failures == 0 ? "\nall pendant radio cases hold"
                    : "\n\(failures) pendant radio case(s) came back wrong")
exit(failures == 0 ? 0 : 1)
}
