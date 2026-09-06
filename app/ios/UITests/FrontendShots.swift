import XCTest

/// Every screen in the app, photographed on one build.
///
/// Three passes, because first run can only be walked once per install and the
/// pages behind the door need an account the simulator has no backend for:
///   1. `testPreAuth` — the opening, the welcome, the tour, and every page of
///      the door, on a fresh install.
///   2. `testFirstRunBehindTheDoor` — the name, computer and microphone beats,
///      the finale, the three tips and the coach mark, reached by seeding the
///      same defaults the real routing reads.
///   3. `testDashboardAndSettings` — the conversation dashboard's three faces
///      and every settings page, light and dark.
///
/// The seeding is launch arguments only. There is no rig code in the app: a
/// screenshot path that exists in the shipped binary is a screenshot of
/// something nobody else can reach.
final class FrontendShots: XCTestCase {
    private let dir = "/Users/cjxsez/.claude/jobs/c9af554c/tmp/frontend"

    override func setUpWithError() throws { continueAfterFailure = true }

    private func shot(_ name: String, settle: TimeInterval = 1.3) {
        Thread.sleep(forTimeInterval: settle)
        let data = XCUIScreen.main.screenshot().pngRepresentation
        try? FileManager.default.createDirectory(atPath: dir,
                                                 withIntermediateDirectories: true)
        try? data.write(to: URL(fileURLWithPath: "\(dir)/\(name).png"))
    }

    @discardableResult
    private func tap(_ app: XCUIApplication, _ label: String,
                     timeout: TimeInterval = 6) -> Bool {
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

    /// A settings row is any element carrying that label; rows are not always
    /// buttons.
    @discardableResult
    private func row(_ app: XCUIApplication, _ label: String,
                     timeout: TimeInterval = 5) -> Bool {
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

    private func fresh(_ extra: [String] = []) -> XCUIApplication {
        let app = XCUIApplication()
        // An unreachable backend on purpose: every screen then draws its own
        // honest offline face rather than a spinner waiting on a server this
        // machine does not run.
        app.launchArguments += ["-backendURL", "http://127.0.0.1:9"] + extra
        return app
    }

    // MARK: - 1. In front of the door

    func testPreAuth() throws {
        let app = fresh()
        app.launch()

        // The opening: a seed, a wavefront, the mark.
        let intro = app.buttons["Anticipy"].firstMatch
        if intro.waitForExistence(timeout: 8) {
            shot("01-intro-early", settle: 0.6)
            shot("02-intro-mark", settle: 1.1)
            // The piece is four seconds and ends on its own. By now it may
            // already have, so this is a courtesy rather than a step.
            if intro.exists && intro.isHittable { intro.tap() }
        }

        shot("03-welcome", settle: 3.4)
        tap(app, "Take a quick tour")
        shot("04-tour-1", settle: 1.6)
        app.swipeLeft(); shot("05-tour-2", settle: 1.2)
        app.swipeLeft(); shot("06-tour-3", settle: 1.2)
        tap(app, "Get started")

        shot("07-signup-email", settle: 1.4)
        let email = app.textFields.firstMatch
        if email.waitForExistence(timeout: 4) {
            email.tap(); email.typeText("you@anticipy.ai")
            shot("08-signup-email-filled", settle: 0.7)
            tap(app, "Continue")
        }
        shot("09-signup-password", settle: 1.2)
        let pw = app.secureTextFields.firstMatch
        if pw.waitForExistence(timeout: 4) {
            pw.tap(); pw.typeText("walkthrough123")
            tap(app, "Continue")
        }
        shot("10-signup-phone", settle: 1.3)
        let phone = app.textFields.firstMatch
        if phone.waitForExistence(timeout: 4) {
            phone.tap(); phone.typeText("6045550123")
            shot("11-signup-phone-filled", settle: 0.8)
        }

        // The door's other rooms.
        tap(app, "Back"); tap(app, "Back")
        tapContaining(app, "Sign in")
        shot("12-sign-in", settle: 1.3)
        tapContaining(app, "Text me a code")
        shot("13-forgot-password", settle: 1.3)
        let fe = app.textFields.firstMatch
        if fe.waitForExistence(timeout: 4) {
            fe.tap(); fe.typeText("you@anticipy.ai")
            tap(app, "Text me a code")
        }
        shot("14-code", settle: 2.0)
        app.typeText("512884")
        shot("15-code-filled", settle: 0.9)
        tap(app, "Continue")
        shot("16-new-password", settle: 1.3)
    }

    // MARK: - 2. Behind the door

    func testFirstRunBehindTheDoor() throws {
        let app = fresh(["-hasSeenIntro", "YES", "-hasOnboarded", "NO",
                         "-accountID", "shots", "-authToken", "shots",
                         "-ownerFirstName", "Alex", "-ownerEmail", "you@anticipy.ai",
                         "-ownerPhone", "+16045550123", "-home.tipsSeen", "NO"])
        app.launch()

        shot("20-your-name", settle: 2.2)
        tap(app, "Continue")
        shot("21-your-computer", settle: 1.5)
        tap(app, "Continue")
        shot("22-may-i-listen", settle: 1.5)

        // The privacy sheet this beat can open.
        if tapContaining(app, "Learn more", timeout: 3) {
            shot("23-microphone-promises", settle: 1.4)
            let done = app.buttons["Done"].firstMatch
            if done.waitForExistence(timeout: 3) { done.tap() } else { app.swipeDown() }
            Thread.sleep(forTimeInterval: 1.0)
        }

        tap(app, "Finish", timeout: 8)
        shot("24-finale", settle: 1.4)

        if app.buttons["Next"].firstMatch.waitForExistence(timeout: 14) {
            shot("25-tip-1", settle: 1.0)
            tap(app, "Next")
            shot("26-tip-2", settle: 1.0)
            tap(app, "Next")
            shot("27-tip-3", settle: 1.0)
            tap(app, "Done")
        }
        let coach = app.buttons["Start by tapping Listen with phone"].firstMatch
        if coach.waitForExistence(timeout: 4) {
            shot("28-coach-mark", settle: 1.2)
            coach.tap()
        }
        shot("29-home-arrived", settle: 1.6)
    }

    // MARK: - 3. The dashboard and every settings page

    func testDashboardAndSettings() throws {
        let app = fresh(["-hasSeenIntro", "YES", "-hasOnboarded", "YES",
                         "-accountID", "shots", "-authToken", "shots",
                         "-ownerFirstName", "Alex", "-ownerEmail", "you@anticipy.ai",
                         "-ownerPhone", "+16045550123", "-home.tipsSeen", "YES"])
        app.launch()

        shot("30-dashboard-thread", settle: 2.4)

        // The ask bar.
        let ask = app.textViews.firstMatch.exists ? app.textViews.firstMatch : app.textFields.firstMatch
        if ask.waitForExistence(timeout: 5) {
            ask.tap()
            ask.typeText("Remind me to call the plumber tomorrow morning")
            shot("31-dashboard-asking", settle: 1.0)
            // Put the keyboard away so the next shots are of the app.
            app.swipeDown()
            Thread.sleep(forTimeInterval: 0.8)
        }

        // The title switch, and History behind it.
        if tapContaining(app, "Switch view", timeout: 5) {
            shot("32-dashboard-menu", settle: 1.0)
            if tap(app, "History", timeout: 4) {
                shot("33-dashboard-history", settle: 1.4)
                if tapContaining(app, "Switch view", timeout: 4) {
                    tap(app, "Today", timeout: 4)
                    Thread.sleep(forTimeInterval: 1.0)
                }
            }
        }

        // The capture moment.
        if tap(app, "Listen with phone", timeout: 6) {
            let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
            for _ in 0..<2 {
                let allow = springboard.buttons["Allow"].firstMatch
                let ok = springboard.buttons["OK"].firstMatch
                if allow.waitForExistence(timeout: 6) { allow.tap() }
                else if ok.waitForExistence(timeout: 2) { ok.tap() }
                Thread.sleep(forTimeInterval: 1.1)
            }
            shot("34-capture-listening", settle: 3.0)
            if tap(app, "Hold listening", timeout: 5) {
                shot("35-capture-paused", settle: 1.6)
                tap(app, "Resume listening", timeout: 4)
                Thread.sleep(forTimeInterval: 1.0)
            }
            tap(app, "Done listening", timeout: 5)
            Thread.sleep(forTimeInterval: 1.5)
        }

        // SETTINGS
        guard tap(app, "Settings", timeout: 8) else { return }
        shot("40-settings", settle: 1.6)
        app.swipeUp(); shot("41-settings-scrolled", settle: 1.0); app.swipeDown()

        row(app, "Listening")
        shot("42-listening", settle: 1.3)
        app.swipeUp(); shot("43-listening-scrolled", settle: 1.0); app.swipeDown()
        if row(app, "Listening activity") {
            shot("44-listening-activity", settle: 1.3)
            back(app)
        }
        back(app)

        if row(app, "Notifications") { shot("45-notifications", settle: 1.3); back(app) }

        if row(app, "Connectors") {
            shot("46-connectors", settle: 1.3)
            if row(app, "Your calendar") { shot("47-calendar", settle: 1.2); back(app) }
            if row(app, "Browser") { shot("48-browser", settle: 1.2); back(app) }
            if row(app, "Mac app") { shot("49-mac", settle: 1.2); back(app) }
            if row(app, "Pendant") { shot("50-pendant", settle: 1.2); back(app) }
            back(app)
        }

        if row(app, "Profile") { shot("51-profile", settle: 1.3); back(app) }
        if row(app, "Advanced") { shot("52-advanced", settle: 1.3); back(app) }

        // The alternate appearance, exercised through the real picker.
        if row(app, "Appearance") {
            shot("53-appearance", settle: 1.2)
            if row(app, "Dark") {
                shot("54-appearance-dark", settle: 1.6)
            }
            back(app)
        }
        if row(app, "About Anticipy") { shot("55-about-dark", settle: 1.3); back(app) }
        shot("56-settings-dark", settle: 1.2)
        back(app)
        shot("57-dashboard-dark", settle: 1.6)
    }
}
