# Installer-level Permission Walkthrough Design

Audience: design + engineering review before applying patches.
Status: draft, not yet applied.
Date: 2026-05-27.
Author: V7 build agent.

The current bare Anticipy.app declares only `NSMicrophoneUsageDescription`.
Every other macOS Transparency, Consent, and Control (TCC) gate fires
silently or as the generic "Python wants access to control ..." dialog
spawned by the bundled engine subprocess. New users do not understand
those dialogs, decline them, and the engine returns Apple error -1743
forever after. This document specifies the fix: an Anticipy.app
first-launch walkthrough that pre-requests every permission with proper
copy, polls the result, and recovers from declines.

Frozen-path note: nothing in `engine/app/action_engine/`,
`engine/app/proactive_day/`, or `engine/app/anticipy/` is modified.
The walkthrough is a new product surface that talks to a new
`/api/permissions/*` router under `app.product.permission_walkthrough`,
attached the same way every other router attaches in
`app.product.server`.

## Section A. Permissions Anticipy needs and the Apple keys for each

| # | Capability         | TCC bucket                       | Info.plist usage-description key       |
|---|--------------------|----------------------------------|----------------------------------------|
| 1 | Accessibility      | Privacy and Security, Accessibility | `NSAccessibilityUsageDescription`    |
| 2 | Automation         | Privacy and Security, Automation | `NSAppleEventsUsageDescription`        |
| 3 | Screen recording   | Privacy and Security, Screen and System Audio Recording | `NSScreenCaptureUsageDescription` |
| 4 | Microphone         | Privacy and Security, Microphone | `NSMicrophoneUsageDescription`         |
| 5 | Notifications      | Notifications (separate root)    | `NSUserNotificationsUsageDescription`  |

The Automation bucket is per target-app inside the same controlling
process. Anticipy.app must trigger Apple events to Calendar.app,
Reminders.app, Notes.app, Messages.app, and System Events.app once
each, so the walkthrough fires five Automation prompts in sequence,
not one. Apple does not provide individual target-app usage strings.
One `NSAppleEventsUsageDescription` covers the whole bucket.

## Section B. Exact usage-description strings

Plain English, second person, under 200 characters each, no em-dashes.

- `NSAccessibilityUsageDescription`
  `Anticipy reads the on-screen contents of your active app so it can act on what you mention out loud.`

- `NSAppleEventsUsageDescription`
  `Anticipy uses Calendar, Reminders, Notes, and Messages on your behalf so reminders, drafts, and events appear without you switching apps.`

- `NSScreenCaptureUsageDescription`
  `Anticipy captures the visible part of your screen only when it needs to read a canvas app like Figma or a PDF you reference out loud.`

- `NSMicrophoneUsageDescription`
  `Anticipy listens for ambient conversational intent. Microphone access is required for the product to work.`

- `NSUserNotificationsUsageDescription`
  `Anticipy sends a Confirm Card a few seconds before any irreversible action so you can quietly cancel without picking up your phone.`

## Section C. First-launch UX wireframe

A modal that takes the whole `/app` viewport on first open and steps
the user through a 6-card flow. The right column shows live status
for each permission, the left column shows the active step.

```
+-----------------------------------------------------------------------+
| Card 1 - Welcome                                                      |
|                                                                       |
|   [serif] One last setup step.                                        |
|   [body]  Anticipy works by hearing you, reading your screen, and    |
|           quietly using your apps. macOS asks you to grant each of   |
|           those once. Five quick clicks, then you never see this     |
|           screen again.                                              |
|                                                                       |
|                                       [ Start ]                       |
+-----------------------------------------------------------------------+

+-----------------------------------------------------------------------+
| Card 2 - Microphone                       |  Status panel             |
|   "So Anticipy can hear you."             |  - Microphone   ...       |
|   [Why we need this]                      |  - Accessibility ...      |
|                                           |  - Screen rec.  ...       |
|        [ Grant microphone ]               |  - Automation   ...       |
|        [ Skip, I'll grant later ]         |  - Notifications ...      |
+-----------------------------------------------------------------------+

(Cards 3 through 6 repeat the same shape for Accessibility,
Screen recording, Automation (Calendar, Reminders, Notes, Messages,
System Events in one card with 5 prompts), then Notifications.)

+-----------------------------------------------------------------------+
| Card 7 - All set                                                      |
|                                                                       |
|   [serif] You're all set.                                             |
|   [body]  Anticipy is listening. Talk normally; we'll surface a       |
|           Confirm Card before anything irreversible.                  |
|                                                                       |
|                                       [ Take me in ]                  |
+-----------------------------------------------------------------------+
```

If any permission shows `denied`, the success card is replaced by a
remediation card that lists exactly which permission is missing, shows
a friendly one-liner of why it matters, and renders a button that
opens the right System Settings pane via the deep link in Section E.
The walkthrough never blocks the user from skipping. Skip writes a
half-completed `first_launch_complete.json` with the booleans recorded
so we can re-show only the missing ones on subsequent launches.

## Section D. Programmatic triggers

These are the calls the backend uses to make macOS pop each dialog
from inside the Anticipy.app process. Each is implemented in
`engine/app/product/permission_walkthrough.py` so the trigger is
the same code that signs the request: dialogs attribute to
"Anticipy" once we run inside the bundled .app, not to "Python".

- Microphone:
  `AVCaptureDevice.requestAccessForMediaType_completionHandler_(AVMediaTypeAudio, cb)`
  (reuses the same pattern as `engine/app/product/main.py` line 44).

- Accessibility:
  `ApplicationServices.AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})`
  via pyobjc. The first call with `prompt=True` shows the system
  dialog. Subsequent calls do not.

- Screen recording:
  `Quartz.CGRequestScreenCaptureAccess()` from
  `pyobjc-framework-Quartz`. Available on macOS 11 and later, which
  matches `minimumSystemVersion: 11.0` in `tauri.conf.json`.
  Fallback for older / missing binding: a one-shot
  `/usr/sbin/screencapture -x -R 0,0,1,1 /tmp/anticipy_probe.png`
  which forces the system dialog.

- Automation (per target app):
  `osascript -e 'tell application "Calendar" to count calendars'`
  (and the same for `Reminders`, `Notes`, `Messages`, `System Events`).
  Each first call surfaces an Automation consent dialog. The
  Info.plist `NSAppleEventsUsageDescription` string is shown inside.

- Notifications:
  `UserNotifications.UNUserNotificationCenter.currentNotificationCenter().requestAuthorizationWithOptions_completionHandler_(UNAuthorizationOptionAlert | UNAuthorizationOptionSound, cb)`.

Each call has a paired status read so the walkthrough polls without
re-prompting. The status reads are:

- Microphone: `AVCaptureDevice.authorizationStatusForMediaType_`.
- Accessibility: `ApplicationServices.AXIsProcessTrusted()`
  (no-arg form, no prompt).
- Screen recording: `Quartz.CGPreflightScreenCaptureAccess()`.
- Automation: re-run the same `osascript` and inspect for error -1743.
- Notifications: `UNUserNotificationCenter.getNotificationSettingsWithCompletionHandler_`.

## Section E. Recovery for declined permissions

System Settings on macOS 13 and later accepts `x-apple.systempreferences:`
URLs that jump directly to the right pane. Anticipy never has to ask
the user to "find Privacy and Security in System Settings".

| Permission        | Deep link                                                                       |
|-------------------|---------------------------------------------------------------------------------|
| Accessibility     | `x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility` |
| Automation        | `x-apple.systempreferences:com.apple.preference.security?Privacy_Automation`    |
| Screen recording  | `x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture` |
| Microphone        | `x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone`    |
| Notifications     | `x-apple.systempreferences:com.apple.Notifications-Settings.extension`          |

Each remediation card renders:
1. A one-line reminder of what stops working without it.
2. A button labelled `Open System Settings` that hits the deep link
   via `window.open(url, "_self")` (the OS handles the scheme).
3. A "Try again" button that re-polls the status read from Section D.
4. A "Skip for now" link that records the decline in
   `~/.anticipy/v7/first_launch_complete.json` and continues the flow.

If the user grants in System Settings, the next status poll flips
the badge to green and the walkthrough advances. We never need to
re-launch Anticipy.app to pick up the new TCC value, because Apple
re-evaluates on the next API call.

## Definition of "done" for the walkthrough

A user installs the .app on a clean Mac, double-clicks, sees the
welcome card, clicks through five permission cards in under 60
seconds, lands on the success card, and never sees a raw "Python
wants access" dialog. If they decline any single permission, the
remediation card opens the right System Settings pane in one click.
`first_launch_complete.json` exists after either success or
deliberate-skip, so subsequent launches never re-show the flow.

No em-dashes.
