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


// ── ex 90: a dying pendant must say so before it dies ───────────────────────

func checkBattery(_ name: String, _ got: PendantBatteryPolicy.Warning,
                  _ want: PendantBatteryPolicy.Warning) {
    if got == want {
        print("  ok   \(name)")
    } else {
        print("  FAIL \(name): got \(got), want \(want)")
        failures += 1
    }
}

func checkDetail(_ name: String, _ got: String?, _ want: String?) {
    if got == want {
        print("  ok   \(name)")
    } else {
        print("  FAIL \(name): got \(got ?? "nil"), want \(want ?? "nil")")
        failures += 1
    }
}

func runBattery() {
    // A level we have never been told is not a level we may warn about. An
    // invented warning about someone's hardware is the same class of lie as an
    // invented memory (ex 56 / Part 2·5).
    checkBattery("an unknown level says nothing",
                 PendantBatteryPolicy.warning(percent: nil), .none)
    checkDetail("an unknown level renders no row",
                PendantBatteryPolicy.detail(percent: nil), nil)

    checkBattery("a healthy level says nothing",
                 PendantBatteryPolicy.warning(percent: 80), .none)

    // The boundaries, both sides. An off-by-one here is the whole bug: it either
    // warns a person whose pendant is fine, or stays quiet on one that is dying.
    let low = PendantBatteryPolicy.lowAtPercent
    let crit = PendantBatteryPolicy.criticalAtPercent
    checkBattery("one above the low dial is still quiet",
                 PendantBatteryPolicy.warning(percent: low + 1), .none)
    checkBattery("exactly the low dial warns",
                 PendantBatteryPolicy.warning(percent: low), .low)
    checkBattery("one above the critical dial is only low",
                 PendantBatteryPolicy.warning(percent: crit + 1), .low)
    checkBattery("exactly the critical dial is critical",
                 PendantBatteryPolicy.warning(percent: crit), .critical)
    checkBattery("flat is critical",
                 PendantBatteryPolicy.warning(percent: 0), .critical)

    // The words a person actually reads. No status words, no numbers to
    // interpret, and the number kept alongside so nothing is hidden (ex 83).
    checkDetail("a healthy level shows just the number",
                PendantBatteryPolicy.detail(percent: 80), "80%")
    checkDetail("a low level says what to do",
                PendantBatteryPolicy.detail(percent: low), "\(low)% · charge it soon")
    checkDetail("a dying level says so plainly",
                PendantBatteryPolicy.detail(percent: crit), "\(crit)% · about to die")

    // The dials must stay ordered, or the ladder is nonsense.
    if crit >= low {
        print("  FAIL the critical dial is not below the low dial")
        failures += 1
    } else {
        print("  ok   the dials are ordered")
    }
}

// ── ex 77 / ex 78: what a finished card leads with, and whether it lies ─────

func runReceipts() {
    // The receipt leads, verbatim. Never reformatted: ex 126 calls a
    // paraphrase an invented memory, and ex 44 calls the result evidence.
    let booked = "Booked: Earls West Van · Thu 7:30 · 4 people · conf #R7K2"
    let done = JobReceiptPolicy.doneCard(goal: "Book a table for two", result: booked)
    checkDetail("the receipt leads, untouched", done.lead, booked)
    checkDetail("the goal drops to context", done.context, "Book a table for two")
    if done.hasReceipt { print("  ok   a receipt is reported as a receipt") }
    else { print("  FAIL a receipt is not reported as one"); failures += 1 }

    // Done with nothing to show for it is a claim without a receipt (ex 106:
    // "Tempted to say 'done.' Only with the receipt in hand."). The old card
    // silently fell back to the goal, which reads as success.
    for (name, empty) in [("nil", String?.none), ("blank", ""), ("whitespace", "   \n ")] {
        let bare = JobReceiptPolicy.doneCard(goal: "Book a table", result: empty)
        if bare.hasReceipt {
            print("  FAIL a \(name) result is treated as a receipt"); failures += 1
        } else if bare.lead == "Book a table" {
            print("  FAIL a \(name) result silently falls back to the goal"); failures += 1
        } else {
            print("  ok   a \(name) result says there is nothing to show")
        }
    }

    // ex 78's middle answer. The uncertain case must warn about a duplicate -
    // ex 36: saying "nothing was done" there "is the sentence that buys a
    // duplicate booking nobody checks for".
    let unsure = JobReceiptPolicy.safetyLine(effectUncertain: true)
    if unsure.lowercased().contains("may already") {
        print("  ok   an uncertain effect warns before a retry")
    } else {
        print("  FAIL an uncertain effect does not warn: \(unsure)"); failures += 1
    }

    // And the ordinary case must NOT promise a resume, because the retry button
    // starts a fresh request (ex 108: no confident lies).
    for flag in [false, Bool?.none] {
        let safe = JobReceiptPolicy.safetyLine(effectUncertain: flag)
        let l = safe.lowercased()
        if l.contains("picks up") || l.contains("where it left off") || l.contains("resume") {
            print("  FAIL the safety line promises a resume the retry does not do"); failures += 1
        } else if l.contains("nothing you told me was lost") {
            print("  ok   the ordinary case reassures without promising a resume")
        } else {
            print("  FAIL the ordinary safety line says nothing useful: \(safe)"); failures += 1
        }
    }
}
runBattery()
runReceipts()
print(failures == 0 ? "\nall pendant and finished-card cases hold"
                    : "\n\(failures) case(s) came back wrong")
exit(failures == 0 ? 0 : 1)
}
