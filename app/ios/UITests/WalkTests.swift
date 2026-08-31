import XCTest

final class WalkTests: XCTestCase {

    override func setUpWithError() throws {
        continueAfterFailure = false
    }

    private func snap(_ name: String, settle: TimeInterval = 1.4) {
        Thread.sleep(forTimeInterval: settle)
        let att = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        att.name = name
        att.lifetime = .keepAlways
        add(att)
    }

    private func back() {
        let app = XCUIApplication()
        let custom = app.buttons["Back"].firstMatch
        if custom.waitForExistence(timeout: 2) {
            custom.tap()
            return
        }

        // Diagnostics and the legacy Form use the system navigation bar,
        // whose back button inherits the previous page's title instead of the
        // custom sheet's explicit "Back" accessibility label.
        let system = app.navigationBars.buttons.firstMatch
        XCTAssertTrue(system.waitForExistence(timeout: 3),
                      "Expected a custom or system Back button")
        system.tap()
    }

    @discardableResult
    private func require(_ text: String,
                         in app: XCUIApplication,
                         timeout: TimeInterval = 6) -> XCUIElement {
        let element = app.descendants(matching: .any)
            .matching(NSPredicate(format: "label == %@", text)).firstMatch
        XCTAssertTrue(element.waitForExistence(timeout: timeout),
                      "Expected to see \(text)")
        return element
    }

    private func tap(_ label: String,
                     in app: XCUIApplication,
                     timeout: TimeInterval = 6) {
        let button = app.buttons[label].firstMatch
        XCTAssertTrue(button.waitForExistence(timeout: timeout),
                      "Expected a \(label) button")
        button.tap()
    }

    /// Walks the real first-run route, signs in to the local walkthrough
    /// account, reaches Home, and then records every top-level Settings page.
    /// The shell runner removes the app before this test, so every run begins
    /// at the same first-run state instead of inheriting the previous run.
    func testWalkEverything() throws {
        let app = XCUIApplication()
        app.launchArguments += ["-backendURL", "http://127.0.0.1:8090"]
        app.launch()

        // The two explanatory beats intentionally precede account creation.
        require("Anticipy", in: app)
        snap("01-welcome")
        tap("Continue", in: app)

        require("How it works", in: app)
        snap("02-how-it-works")
        tap("Continue", in: app)

        // The door opens in sign-up mode; record it, then use the real sign-in
        // path so the walkthrough does not create a new owner on every run.
        require("Let's make it yours.", in: app)
        snap("03-sign-up")
        let signInLink = app.staticTexts["Sign in"].firstMatch
        XCTAssertTrue(signInLink.waitForExistence(timeout: 4))
        signInLink.tap()

        require("Welcome back.", in: app)
        snap("04-sign-in")
        let email = app.textFields.firstMatch
        XCTAssertTrue(email.waitForExistence(timeout: 3))
        email.tap()
        email.typeText("walk@anticipy.test")
        let password = app.secureTextFields.firstMatch
        XCTAssertTrue(password.exists)
        password.tap()
        password.typeText("walkthrough123")
        tap("Sign in", in: app)

        // Record the consent page but take its explicit first-class exit. The
        // visual audit does not need to start capturing a simulated room.
        require("May I listen?", in: app, timeout: 10)
        snap("05-microphone-consent")
        tap("Not right now", in: app)

        require("This is what I have.", in: app)
        snap("06-account-confirmation")
        tap("Start living your day", in: app)

        // HOME — the Settings control is the proof that first run really
        // ended. A missing control now fails the test instead of producing a
        // mislabeled screenshot of whatever page happened to remain visible.
        let settings = app.buttons["Settings"].firstMatch
        XCTAssertTrue(settings.waitForExistence(timeout: 10),
                      "First run never reached Home")
        snap("07-home")
        app.swipeUp(); snap("08-home-scrolled"); app.swipeDown()

        // SETTINGS
        settings.tap()
        require("Settings", in: app)
        snap("09-settings-home")

        let row = { (label: String) in
            let element = app.descendants(matching: .any)
                .matching(NSPredicate(format: "label == %@", label)).firstMatch
            XCTAssertTrue(element.waitForExistence(timeout: 4),
                          "Expected Settings row \(label)")
            element.tap()
        }
        row("Listening")
        let listeningState = require("Right now", in: app)
        XCTAssertEqual(listeningState.value as? String, "Off")
        snap("10-listening")
        app.swipeUp(); snap("11-listening-scrolled"); app.swipeDown()
        row("Find out what listening actually did")
        require("Listening right now", in: app)
        snap("12-listening-diagnostics")
        app.swipeUp(); snap("13-listening-diagnostics-scrolled")
        back()
        back()
        row("What I can see")
        require("Your calendar", in: app)
        snap("14-access")
        row("Your calendar")
        require("Right now", in: app)
        snap("15-calendar-access")
        back(); back()
        row("Profile")
        require("First name", in: app)
        snap("16-profile")
        XCTAssertFalse(app.staticTexts[
            "That doesn't look like a full number yet — country code and all."
        ].exists, "Unchanged profile details must not show a phone validation error")
        back()

        row("Pendant, voice, browser and the rest")
        require("Listening", in: app)
        snap("17-legacy-settings-top")
        for index in 1...5 {
            app.swipeUp()
            snap("legacy-settings-scroll-\(index)")
        }
        back()

        let info = app.buttons["About Anticipy"].firstMatch
        XCTAssertTrue(info.waitForExistence(timeout: 3))
        info.tap()
        require("About", in: app); snap("about")
        tap("Close", in: app)

        // A consumer app also has to survive its own alternate appearance.
        // Exercise the real picker rather than injecting a launch preference.
        row("Dark")
        snap("settings-dark")
        back(); snap("home-dark")
    }
}
