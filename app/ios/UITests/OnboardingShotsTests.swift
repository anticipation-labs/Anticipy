import XCTest

/// TEMPORARY screenshot rig for the first-run redesign. Walks every screen and
/// writes PNGs to the job's scratch directory. Deleted after capture.
final class OnboardingShotsTests: XCTestCase {
    private let dir = "/Users/cjxsez/.claude/jobs/c9af554c/tmp/shots"

    override func setUpWithError() throws { continueAfterFailure = true }

    private func shot(_ name: String, settle: TimeInterval = 1.2) {
        Thread.sleep(forTimeInterval: settle)
        let data = XCUIScreen.main.screenshot().pngRepresentation
        try? data.write(to: URL(fileURLWithPath: "\(dir)/\(name).png"))
    }

    private func tap(_ app: XCUIApplication, _ label: String, timeout: TimeInterval = 8) {
        let b = app.buttons[label].firstMatch
        XCTAssertTrue(b.waitForExistence(timeout: timeout), "no button \(label)")
        if b.isHittable { b.tap() } else { b.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap() }
    }

    private func tapContaining(_ app: XCUIApplication, _ text: String, timeout: TimeInterval = 8) {
        let b = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", text)).firstMatch
        XCTAssertTrue(b.waitForExistence(timeout: timeout), "no button containing \(text)")
        b.tap()
    }

    func testPreAuth() throws {
        let app = XCUIApplication()
        app.launchArguments += ["-backendURL", "http://127.0.0.1:9"]
        app.launch()
        shot("01-welcome", settle: 2.2)
        tap(app, "Take a quick tour")
        shot("02-tour-1", settle: 1.6)
        app.swipeLeft(); shot("03-tour-2", settle: 1.3)
        app.swipeLeft(); shot("04-tour-3", settle: 1.3)
        tap(app, "Get started")
        shot("05-email", settle: 1.4)
        let email = app.textFields.firstMatch
        XCTAssertTrue(email.waitForExistence(timeout: 4))
        email.tap(); email.typeText("you@anticipy.ai")
        shot("06-email-filled", settle: 0.8)
        tap(app, "Continue")
        shot("07-password", settle: 1.3)
        let pw = app.secureTextFields.firstMatch
        XCTAssertTrue(pw.waitForExistence(timeout: 4))
        pw.tap(); pw.typeText("walkthrough123")
        tap(app, "Continue")
        shot("08-phone", settle: 1.3)
        let phone = app.textFields.firstMatch
        XCTAssertTrue(phone.waitForExistence(timeout: 4))
        phone.tap(); phone.typeText("6045550123")
        shot("09-phone-filled", settle: 0.9)
        tap(app, "Back"); tap(app, "Back")
        tapContaining(app, "Sign in")
        shot("10-sign-in", settle: 1.3)
        tapContaining(app, "Text me a code")
        shot("11-forgot", settle: 1.3)
        let fe = app.textFields.firstMatch
        XCTAssertTrue(fe.waitForExistence(timeout: 4))
        fe.tap(); fe.typeText("you@anticipy.ai")
        tap(app, "Text me a code")
        shot("12-code", settle: 1.8)
        app.typeText("512884")
        shot("13-code-filled", settle: 0.9)
        tap(app, "Continue")
        shot("14-new-password", settle: 1.3)
    }

    func testPostAuth() throws {
        let app = XCUIApplication()
        // Seed exactly the defaults the real routing reads, so
        // FirstRunRoute.decide lands on .tour(.rest) with sample identity and
        // an unreachable backend — no rig code in the app.
        app.launchArguments += ["-backendURL", "http://127.0.0.1:9",
                                "-hasSeenIntro", "YES", "-hasOnboarded", "NO",
                                "-accountID", "shots", "-authToken", "shots",
                                "-ownerFirstName", "Alex", "-ownerEmail", "you@anticipy.ai",
                                "-ownerPhone", "+16045550123", "-home.tipsSeen", "NO"]
        app.launch()
        shot("20-name", settle: 2.0)
        tap(app, "Continue")
        shot("21-computer", settle: 1.4)
        tap(app, "Continue")
        shot("22-may-i-listen", settle: 1.4)
        tap(app, "Finish")
        shot("23-finale", settle: 1.3)
        XCTAssertTrue(app.buttons["Next"].firstMatch.waitForExistence(timeout: 12))
        shot("24-tips-1", settle: 1.0)
        tap(app, "Next")
        shot("25-tips-2", settle: 1.0)
        tap(app, "Next")
        shot("26-tips-3", settle: 1.0)
        tap(app, "Done")
        shot("27-coach-mark", settle: 1.4)
        let coach = app.buttons["Start by tapping Listen with phone"].firstMatch
        if coach.waitForExistence(timeout: 3) { coach.tap() }
        shot("28-home", settle: 1.2)
    }
}
