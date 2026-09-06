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
        if button.isHittable {
            button.tap()
        } else {
            // Page-style TabViews can report a visible footer button outside
            // the collection cell's hit frame. Tap its actual centre so the
            // walk tests the control the screenshot shows, rather than an
            // accessibility-frame quirk in the simulator.
            button.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        }
    }

    /// Custom settings chrome must stay below the physical status bar at every
    /// navigation depth. Existence alone missed a bug where alternate nested
    /// destinations rendered the title at y=0 while remaining tappable.
    private func requireChrome(_ title: String, in app: XCUIApplication) {
        let heading = require(title, in: app)
        XCTAssertGreaterThan(heading.frame.minY, 44,
                             "\(title) title overlaps the status bar")
        let back = app.buttons["Back"].firstMatch
        XCTAssertTrue(back.waitForExistence(timeout: 2))
        XCTAssertGreaterThan(back.frame.minY, 44,
                             "\(title) back button overlaps the status bar")
    }

    /// Walks the real first-run route, signs in to the local walkthrough
    /// account, reaches Home, and then records every top-level Settings page.
    /// The shell runner removes the app before this test, so every run begins
    /// at the same first-run state instead of inheriting the previous run.
    func testWalkEverything() throws {
        let app = XCUIApplication()
        app.launchArguments += ["-backendURL", "http://127.0.0.1:8090"]
        app.launch()

        // The opening plays over every cold launch into first run: a seed, a
        // wavefront, the mark. It is one control to VoiceOver and to this
        // walk; record it mid-piece, then tap it through so the beats behind
        // it are reached on their own timings rather than four seconds late.
        let intro = app.buttons["Anticipy"].firstMatch
        XCTAssertTrue(intro.waitForExistence(timeout: 6), "Expected the opening")
        snap("00-intro", settle: 2.2)
        intro.tap()

        // The two explanatory beats intentionally precede account creation:
        // the welcome, then the three-page tour.
        require("Capture conversations, keep track of commitments, and turn them into follow-ups.", in: app)
        snap("01-welcome")
        tap("Take a quick tour", in: app)

        require("Capture every conversation", in: app)
        snap("02-tour")
        tap("Get started", in: app)

        // The door opens on the email step of sign-up; record it, then use the
        // real sign-in path so the walkthrough does not create a new owner on
        // every run. The switcher is one button whose label carries both the
        // question and the answer.
        require("Let's make it yours.", in: app)
        snap("03-sign-up")
        let signInLink = app.buttons
            .matching(NSPredicate(format: "label CONTAINS %@", "Sign in")).firstMatch
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

        // iOS may offer to save the walkthrough password. It is a system
        // sheet over the app, not part of Anticipy's route, and its presence
        // can swallow the first tap on the consent screen while still leaving
        // that screen visible to accessibility. Clear it before screenshots
        // or route assertions so the walk records and operates the app itself.
        let passwordOffer = app.buttons["Not Now"].firstMatch
        if passwordOffer.waitForExistence(timeout: 2) {
            passwordOffer.tap()
        }

        // Behind the door: the name beat opens exactly one box. The arrow is
        // inert until it holds something, so the walk gives it a name.
        require("What's your name?", in: app, timeout: 10)
        snap("05-your-name")
        let firstName = app.textFields.firstMatch
        XCTAssertTrue(firstName.waitForExistence(timeout: 3))
        if (firstName.value as? String ?? "").isEmpty || firstName.value as? String == "First name" {
            firstName.tap()
            firstName.typeText("Walk")
        }
        tap("Continue", in: app)

        require("Your computer", in: app)
        require("Send to computer", in: app)
        require("Send to Mac", in: app)
        snap("06-computer-handoff")
        tap("Continue", in: app)

        // Record the consent page and finish with both switches off. The
        // visual audit does not need to start capturing a simulated room.
        require("May I listen?", in: app, timeout: 10)
        snap("07-microphone-consent")
        tap("Finish", in: app)

        // The finale plays over Home, then three tips and a coach mark. Walk
        // through them so the Settings control underneath is reachable.
        tap("Next", in: app, timeout: 12)
        snap("08-home-tips")
        tap("Next", in: app)
        tap("Done", in: app)
        let coach = app.buttons["Start by tapping Listen with phone"].firstMatch
        if coach.waitForExistence(timeout: 3) {
            snap("09-home-coach-mark")
            coach.tap()
        }

        // HOME — the Settings control is the proof that first run really
        // ended. A missing control now fails the test instead of producing a
        // mislabeled screenshot of whatever page happened to remain visible.
        let settings = app.buttons["Settings"].firstMatch
        XCTAssertTrue(settings.waitForExistence(timeout: 10),
                      "First run never reached Home")
        snap("08-home")
        app.swipeUp(); snap("09-home-scrolled"); app.swipeDown()

        // SETTINGS
        settings.tap()
        require("Settings", in: app)
        snap("10-settings-home")

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
        row("Listening activity")
        require("Listening right now", in: app)
        snap("12-listening-diagnostics")
        app.swipeUp(); snap("13-listening-diagnostics-scrolled")
        back()
        back()
        row("Notifications")
        requireChrome("Notifications", in: app)
        require("Quiet hours", in: app)
        snap("14-notifications")
        back()

        row("Connectors")
        requireChrome("Connectors", in: app)
        require("Your calendar", in: app)
        snap("15-connectors")
        row("Your calendar")
        require("Right now", in: app)
        snap("16-calendar-access")
        back()
        row("Browser")
        requireChrome("Browser", in: app)
        require("Status", in: app)
        snap("17-browser-connector")
        back()
        row("Mac app")
        requireChrome("Mac app", in: app)
        require("Open Mac setup", in: app)
        require("Send setup to Mac", in: app)
        snap("18-mac-connector")
        back()
        row("Pendant")
        requireChrome("Pendant", in: app)
        require("Status", in: app)
        snap("19-pendant-connector")
        back(); back()

        // CONNECTED APPS — spec page 26's Settings screen, and the other end of
        // the setup card. It is the screen a person reaches to add an app we
        // never asked about, to turn "let Anticipy make changes" on, and to
        // disconnect one. It was in the app and in nobody's walk.
        //
        // ASSERTED, not guarded: unlike the onboarding beat, this row is always
        // there for a signed-in owner. A walk that shrugged at its absence would
        // be a walk that cannot tell a missing screen from a slow one.
        row("Connected apps")
        requireChrome("Connected apps", in: app)
        snap("19a-connected-apps")
        back()

        row("Profile")
        require("First name", in: app)
        snap("20-profile")
        XCTAssertFalse(app.staticTexts[
            "That doesn't look like a full number yet — country code and all."
        ].exists, "Unchanged profile details must not show a phone validation error")
        back()

        row("Advanced")
        requireChrome("Advanced", in: app)
        require("Haptic feedback", in: app)
        snap("21-advanced")
        back()

        // A consumer app also has to survive its own alternate appearance.
        // Exercise the real picker rather than injecting a launch preference.
        row("Appearance")
        requireChrome("Appearance", in: app)
        require("Light", in: app)
        snap("22-appearance")
        row("Dark")
        snap("23-appearance-dark")
        back()

        row("About Anticipy")
        require("About", in: app)
        snap("24-about-dark")
        back()
        snap("25-settings-dark")
        back(); snap("26-home-dark")
    }
}
