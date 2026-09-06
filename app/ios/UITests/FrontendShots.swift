import XCTest

/// Every screen in the app, in the order a person meets them.
///
/// Four passes, because the app cannot be in all of these states at once:
///   1. `testOpeningAndDoor` — cold launch, the opening, the welcome, the
///      tour, and every page of the door, on a fresh install with no server.
///   2. `testFirstRun` — the three beats behind the door, the finale, the tips
///      and the coach mark, reached by seeding the defaults the routing reads.
///   3. `testDashboard` — the conversation dashboard with a day in it, served
///      by a local stand-in backend on :8092.
///   4. `testSettings` — every settings page, light then dark, over the same
///      stand-in so the rows show a signed-in owner rather than an outage.
///
/// The seeding is launch arguments only. There is no screenshot path in the
/// shipped binary: a rig somebody else can reach is a rig that ships.
final class FrontendShots: XCTestCase {
    private let dir = "/Users/cjxsez/.claude/jobs/c9af554c/tmp/frontend"

    /// Where the stand-in backend serves one invented day.
    private let live = "http://127.0.0.1:8092"
    /// A port with nothing on it, for the screens that must be seen offline.
    private let dead = "http://127.0.0.1:9"

    override func setUpWithError() throws { continueAfterFailure = true }

    private func shot(_ name: String, settle: TimeInterval = 1.3) {
        Thread.sleep(forTimeInterval: settle)
        let data = XCUIScreen.main.screenshot().pngRepresentation
        try? FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
        try? data.write(to: URL(fileURLWithPath: "\(dir)/\(name).png"))
    }

    @discardableResult
    private func tap(_ app: XCUIApplication, _ label: String, timeout: TimeInterval = 6) -> Bool {
        let b = app.buttons[label].firstMatch
        guard b.waitForExistence(timeout: timeout) else { return false }
        if b.isHittable { b.tap() }
        else { b.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap() }
        return true
    }

    @discardableResult
    private func tapContaining(_ app: XCUIApplication, _ text: String,
                               timeout: TimeInterval = 6) -> Bool {
        let b = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", text)).firstMatch
        guard b.waitForExistence(timeout: timeout) else { return false }
        b.tap()
        return true
    }

    /// A settings row is any element carrying that label; rows are not buttons.
    @discardableResult
    private func row(_ app: XCUIApplication, _ label: String, timeout: TimeInterval = 5) -> Bool {
        let e = app.descendants(matching: .any)
            .matching(NSPredicate(format: "label == %@", label)).firstMatch
        guard e.waitForExistence(timeout: timeout) else { return false }
        e.tap()
        return true
    }

    private func back(_ app: XCUIApplication) {
        let custom = app.buttons["Back"].firstMatch
        if custom.waitForExistence(timeout: 2) { custom.tap(); return }
        let system = app.navigationBars.buttons.firstMatch
        if system.waitForExistence(timeout: 2) { system.tap() }
    }

    /// Walk into a settings page, photograph it, come back — and verify the
    /// return, so one page that refuses to close cannot turn the rest of the
    /// pass into photographs of the same stuck screen. That has happened.
    private func page(_ app: XCUIApplication, _ label: String, _ name: String,
                      settle: TimeInterval = 1.4) {
        guard row(app, label) else { return }
        shot(name, settle: settle)
        back(app)
        _ = app.descendants(matching: .any)
            .matching(NSPredicate(format: "label == %@", "Settings")).firstMatch
            .waitForExistence(timeout: 4)
    }

    private func app(_ backend: String, _ extra: [String] = []) -> XCUIApplication {
        let a = XCUIApplication()
        a.launchArguments += ["-backendURL", backend] + extra
        return a
    }

    private var signedIn: [String] {
        ["-hasSeenIntro", "YES", "-hasOnboarded", "YES",
         "-accountID", "shots", "-authToken", "shots",
         "-ownerFirstName", "Alex", "-ownerEmail", "alex@example.com",
         "-ownerPhone", "+16045550123", "-home.tipsSeen", "YES"]
    }

    // MARK: - 1. The opening, and the door

    func testOpeningAndDoor() throws {
        let a = app(dead)
        a.launch()

        let intro = a.buttons["Anticipy"].firstMatch
        if intro.waitForExistence(timeout: 8) {
            shot("01-opening-seed", settle: 0.55)
            shot("02-opening-mark", settle: 1.05)
            // Four seconds, and it ends on its own; by now it may already have.
            if intro.exists && intro.isHittable { intro.tap() }
        }

        shot("03-welcome", settle: 3.4)
        tap(a, "Take a quick tour")
        shot("04-tour-conversations", settle: 1.7)
        a.swipeLeft(); shot("05-tour-commitments", settle: 1.3)
        a.swipeLeft(); shot("06-tour-follow-ups", settle: 1.3)
        tap(a, "Get started")

        shot("07-signup-email", settle: 1.5)
        let email = a.textFields.firstMatch
        if email.waitForExistence(timeout: 4) {
            email.tap(); email.typeText("you@anticipy.ai")
            shot("08-signup-email-filled", settle: 0.8)
            tap(a, "Continue")
        }
        shot("09-signup-password", settle: 1.3)
        let pw = a.secureTextFields.firstMatch
        if pw.waitForExistence(timeout: 4) {
            pw.tap(); pw.typeText("walkthrough123")
            tap(a, "Continue")
        }
        shot("10-signup-phone", settle: 1.4)
        let phone = a.textFields.firstMatch
        if phone.waitForExistence(timeout: 4) {
            phone.tap(); phone.typeText("6045550123")
            shot("11-signup-phone-filled", settle: 0.9)
        }

        tap(a, "Back"); tap(a, "Back")
        tapContaining(a, "Sign in")
        shot("12-sign-in", settle: 1.4)
        tapContaining(a, "Text me a code")
        shot("13-forgot", settle: 1.4)
        let fe = a.textFields.firstMatch
        if fe.waitForExistence(timeout: 4) {
            fe.tap(); fe.typeText("you@anticipy.ai")
            tap(a, "Text me a code")
        }
        shot("14-code", settle: 2.0)
        a.typeText("512884")
        shot("15-code-filled", settle: 0.9)
        tap(a, "Continue")
        shot("16-new-password", settle: 1.4)
    }

    // MARK: - 2. Behind the door

    func testFirstRun() throws {
        let a = app(dead, ["-hasSeenIntro", "YES", "-hasOnboarded", "NO",
                           "-accountID", "shots", "-authToken", "shots",
                           "-ownerFirstName", "Alex", "-ownerEmail", "you@anticipy.ai",
                           "-ownerPhone", "+16045550123", "-home.tipsSeen", "NO"])
        a.launch()

        shot("20-your-name", settle: 2.3)
        tap(a, "Continue")
        shot("21-your-computer", settle: 1.6)
        tap(a, "Continue")
        // Two frames a beat apart, so the breathing light can be seen to move.
        shot("22-your-pendant", settle: 1.8)
        shot("22a-your-pendant-breath", settle: 1.15)
        // Almost everybody leaves the pendant here. Photograph the branch too.
        if tap(a, "I have a pendant", timeout: 5) {
            shot("22b-pendant-wake", settle: 1.8)
            if tap(a, "Look for it", timeout: 5) {
                shot("22c-pendant-looking", settle: 2.6)
                // The explainer that opens BEFORE iOS asks.
                if tap(a, "Why Bluetooth?", timeout: 5) {
                    shot("22e-why-bluetooth", settle: 1.6)
                    if !tap(a, "Done", timeout: 3) { a.swipeDown() }
                    Thread.sleep(forTimeInterval: 1.2)
                }
            }
            tap(a, "I don't have it with me", timeout: 5)
            Thread.sleep(forTimeInterval: 1.4)
        } else {
            tap(a, "Continue without one", timeout: 5)
        }
        shot("22d-may-i-listen", settle: 1.8)
        tap(a, "Finish", timeout: 8)
        shot("24-finale", settle: 1.5)

        if a.buttons["Next"].firstMatch.waitForExistence(timeout: 14) {
            shot("25-tip-just-talk", settle: 1.1)
            tap(a, "Next")
            shot("26-tip-nothing-sends", settle: 1.1)
            tap(a, "Next")
            shot("27-tip-connect", settle: 1.1)
            tap(a, "Done")
        }
        let coach = a.buttons["Start by tapping Listen with phone"].firstMatch
        if coach.waitForExistence(timeout: 4) {
            shot("28-coach-mark", settle: 1.3)
            coach.tap()
        }
        shot("29-home-first-arrival", settle: 1.8)
    }

    /// The privacy sheet on the microphone beat, alone: it carries detents and
    /// no close button, and the drag that dismisses it also carries the beat
    /// back a page — which once turned a whole pass into photographs of one
    /// stuck screen.
    func testMicrophonePromises() throws {
        let a = app(dead, ["-hasSeenIntro", "YES", "-hasOnboarded", "NO",
                           "-accountID", "shots", "-authToken", "shots",
                           "-ownerFirstName", "Alex", "-ownerEmail", "you@anticipy.ai",
                           "-ownerPhone", "+16045550123", "-home.tipsSeen", "NO"])
        a.launch()
        // Two arrows to reach the microphone beat: the name, then the computer.
        tap(a, "Continue", timeout: 12)
        Thread.sleep(forTimeInterval: 1.2)
        tap(a, "Continue", timeout: 8)
        Thread.sleep(forTimeInterval: 1.2)
        if tap(a, "Learn more", timeout: 8) {
            shot("23-listening-promises", settle: 1.7)
            a.swipeUp()
            shot("23b-listening-promises-rest", settle: 1.3)
        }
    }

    // MARK: - 3. The dashboard, with a day in it

    func testDashboard() throws {
        let a = app(live, signedIn)
        a.launch()

        shot("30-dashboard-thread", settle: 6.0)
        a.swipeUp();  shot("31-dashboard-approval", settle: 1.7)
        a.swipeUp();  shot("32-dashboard-done", settle: 1.7)
        // The peek card sits where the "Done" heading was; tapping it opens
        // what it adds up to.
        if tapContaining(a, "You've talked to Anticipy", timeout: 5) {
            shot("38-insights", settle: 2.0)
            a.swipeUp(); shot("39-insights-lower", settle: 1.5)
            tap(a, "Close", timeout: 4)
            Thread.sleep(forTimeInterval: 1.2)
        }
        a.swipeDown(); a.swipeDown(); a.swipeDown()
        Thread.sleep(forTimeInterval: 1.4)

        if tapContaining(a, "Switch view", timeout: 6) {
            shot("33-title-menu", settle: 1.1)
            if tap(a, "History", timeout: 4) {
                shot("34-history", settle: 1.7)
                if tapContaining(a, "Switch view", timeout: 4) { tap(a, "Today", timeout: 4) }
                Thread.sleep(forTimeInterval: 1.3)
            }
        }

        let ask = a.textViews.firstMatch.exists ? a.textViews.firstMatch : a.textFields.firstMatch
        if ask.waitForExistence(timeout: 5) {
            ask.tap()
            ask.typeText("Move the dentist to Thursday at 4:15")
            shot("35-asking", settle: 1.1)
            a.swipeDown()
            Thread.sleep(forTimeInterval: 0.9)
        }

        if tap(a, "Listen with phone", timeout: 6) {
            let sb = XCUIApplication(bundleIdentifier: "com.apple.springboard")
            for _ in 0..<2 {
                let allow = sb.buttons["Allow"].firstMatch
                if allow.waitForExistence(timeout: 6) { allow.tap() }
                Thread.sleep(forTimeInterval: 1.1)
            }
            shot("36-capture-listening", settle: 3.2)
            if tap(a, "Hold listening", timeout: 5) {
                shot("37-capture-paused", settle: 1.7)
                tap(a, "Resume listening", timeout: 4)
                Thread.sleep(forTimeInterval: 1.0)
            }
            tap(a, "Done listening", timeout: 5)
            Thread.sleep(forTimeInterval: 1.4)
        }
    }

    // MARK: - 4. Settings, light and dark

    func testSettings() throws {
        let a = app(live, signedIn)
        a.launch()

        guard tap(a, "Settings", timeout: 12) else {
            XCTFail("never reached Settings"); return
        }
        shot("40-settings", settle: 2.0)
        a.swipeUp(); shot("41-settings-scrolled", settle: 1.2); a.swipeDown()
        Thread.sleep(forTimeInterval: 0.8)

        // About lives in the chrome, not in a row.
        if tap(a, "About", timeout: 4) {
            shot("42-about", settle: 1.5)
            back(a)
            Thread.sleep(forTimeInterval: 0.8)
        }

        page(a, "Profile", "43-profile")
        page(a, "Notifications", "44-notifications")
        page(a, "Privacy & Data", "45-privacy-and-data")
        page(a, "Personalization", "46-personalization")

        if row(a, "Listening") {
            shot("47-listening", settle: 1.5)
            a.swipeUp(); shot("48-listening-scrolled", settle: 1.1); a.swipeDown()
            Thread.sleep(forTimeInterval: 0.7)
            if row(a, "Listening activity") {
                shot("49-listening-activity", settle: 1.4)
                back(a)
            }
            back(a)
        }

        if row(a, "Connectors") {
            shot("50-connectors", settle: 1.5)
            page(a, "Your calendar", "51-calendar")
            page(a, "Browser", "52-browser")
            page(a, "Mac app", "53-mac-app")
            page(a, "Pendant", "54-pendant")
            back(a)
        }

        page(a, "Connected apps", "55-connected-apps")
        page(a, "Advanced", "56-advanced")

        // The alternate appearance, through the real picker.
        if row(a, "Appearance") {
            shot("57-appearance", settle: 1.4)
            if row(a, "Dark") { shot("58-appearance-dark", settle: 1.8) }
            back(a)
        }
        shot("59-settings-dark", settle: 1.4)
        Thread.sleep(forTimeInterval: 1.0)
        if tap(a, "About", timeout: 6) {
            shot("60-about-dark", settle: 1.6)
            back(a)
            Thread.sleep(forTimeInterval: 0.8)
        }
        back(a)
        shot("61-dashboard-dark", settle: 2.0)
    }
}
