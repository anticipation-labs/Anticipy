import XCTest

/// Walks the conversation dashboard's three faces and writes a PNG of each, so
/// the capture moment and the history list are reviewed as they actually
/// render rather than as they read in source. Kept because the capture face is
/// unreachable from a screenshot script: it only exists once the listen
/// control has been pressed.
final class DashboardShots: XCTestCase {
    private let dir = "/Users/cjxsez/.claude/jobs/c9af554c/tmp/shots"

    override func setUpWithError() throws { continueAfterFailure = true }

    private func shot(_ name: String, settle: TimeInterval = 1.4) {
        Thread.sleep(forTimeInterval: settle)
        let data = XCUIScreen.main.screenshot().pngRepresentation
        try? data.write(to: URL(fileURLWithPath: "\(dir)/\(name).png"))
    }

    func testDashboardFaces() throws {
        let app = XCUIApplication()
        app.launchArguments += ["-backendURL", "http://127.0.0.1:9",
                                "-hasSeenIntro", "YES", "-hasOnboarded", "YES",
                                "-accountID", "dash", "-authToken", "dash",
                                "-ownerFirstName", "Alex", "-home.tipsSeen", "YES"]
        app.launch()

        // THE THREAD
        XCTAssertTrue(app.buttons["Listen with phone"].firstMatch.waitForExistence(timeout: 10))
        shot("d-01-thread", settle: 2.0)

        // Type into the ask bar so the bubble treatment is on the page.
        let ask = app.textViews.firstMatch.exists ? app.textViews.firstMatch : app.textFields.firstMatch
        if ask.waitForExistence(timeout: 4) {
            ask.tap()
            ask.typeText("Remind me to call the plumber tomorrow morning")
            shot("d-02-ask-typed", settle: 1.0)
        }

        // HISTORY
        let title = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "Switch view")).firstMatch
        if title.waitForExistence(timeout: 4) {
            title.tap()
            shot("d-03-title-menu", settle: 1.0)
            let history = app.buttons["History"].firstMatch
            if history.waitForExistence(timeout: 3) {
                history.tap()
                shot("d-04-history", settle: 1.4)
                // Back to the thread.
                let back = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "Switch view")).firstMatch
                if back.waitForExistence(timeout: 3) {
                    back.tap()
                    let today = app.buttons["Today"].firstMatch
                    if today.waitForExistence(timeout: 3) { today.tap() }
                }
            }
        }

        // THE CAPTURE MOMENT. The simulator has no microphone permission and
        // no audio, so the listening state is whatever the app makes of a
        // refused start — which is exactly one of the faces this screen has to
        // draw honestly, and worth a picture of its own.
        let listen = app.buttons["Listen with phone"].firstMatch
        if listen.waitForExistence(timeout: 5) {
            listen.tap()
            shot("d-05-after-listen", settle: 2.4)
            // iOS asks twice — speech, then the microphone — and both dialogs
            // belong to Springboard rather than to the app.
            let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
            for _ in 0..<2 {
                let allow = springboard.buttons["Allow"].firstMatch
                let ok = springboard.buttons["OK"].firstMatch
                if allow.waitForExistence(timeout: 6) { allow.tap() }
                else if ok.waitForExistence(timeout: 2) { ok.tap() }
                Thread.sleep(forTimeInterval: 1.2)
            }
            shot("d-06-capture", settle: 3.0)
            // The hold control, so the paused face is on the record too.
            let hold = app.buttons["Hold listening"].firstMatch
            if hold.waitForExistence(timeout: 5) {
                hold.tap()
                shot("d-07-capture-held", settle: 1.8)
            }
        }
    }
}
