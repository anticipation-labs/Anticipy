# Native macOS action path: first-run permission prompts

The first time `engine/app/product/native_action_macos.py` is invoked
against each native app, macOS pops an Automation consent dialog.
The dialog is gated by the system's TCC (Transparency, Consent, and
Control) database under System Settings, Privacy and Security,
Automation. The user MUST click "OK" once per (controlling_process,
target_app) pair. If the user clicks "Don't Allow", the AppleScript
call fails with error -1743 ("Not authorized to send Apple events")
and the engine returns a `NativeResult(ok=False)` receipt.

## Prompts triggered

This module triggers the following dialogs, each at most once per
controlling process for the lifetime of the TCC grant:

- `Python wants access to control "Calendar.app"` (first
  `calendar_create_event` / `calendar_list_events` / `calendar_delete_event`).
- `Python wants access to control "Reminders.app"` (first
  `reminders_add` / `reminders_list` / `reminders_delete`).
- `Python wants access to control "Notes.app"` (first `notes_create`
  / `notes_list` / `notes_delete`).
- `Python wants access to control "Messages.app"` (first
  `messages_draft` when `send=true`, or any iMessage send command).
- `Python wants access to control "System Events.app"` (first call
  to `is_app_running`, `activate_app`, `screenshot_app`, or any
  keystroke-based `messages_draft` fallback).
- Screen Recording prompt may appear the first time
  `screenshot_app` runs `/usr/sbin/screencapture` (under Screen and
  System Audio Recording, not Automation).

## Observed during development

`osascript -e 'tell application "Calendar" to name of calendars'`
returned:

  ```
  31:35: execution error: Not authorized to send Apple events to
  Calendar. (-1743)
  ```

This is the expected first-call denial path until the user grants
Automation access. After granting once and re-running, the call
succeeds.

## Operator unblock

1. Open System Settings, Privacy and Security, Automation.
2. Locate the controlling process (Terminal, iTerm, Python, the
   engine launcher).
3. Toggle ON each native app the engine needs (Calendar, Reminders,
   Notes, Messages, System Events).
4. Re-run the engine. The dialogs do not reappear unless TCC is
   reset (`tccutil reset AppleEvents`).

For Screen Recording (used by `screenshot_app`):
1. Open System Settings, Privacy and Security, Screen and System
   Audio Recording.
2. Toggle ON for the same controlling process.

No em-dashes.
