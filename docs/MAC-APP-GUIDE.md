# Anticipy for Mac

The meeting recorder for macOS. This is the same guide the app shows under
Help, kept here so it can be read before installing. The sections below are
the sections in the app, in the same order; `app/macos/Tests/run_app_shell_tests.sh`
refuses a heading that exists in one and not the other.

Requirements: macOS 26 on Apple silicon or Intel, and an Anticipy account if
you want the words to sync. Download: https://www.anticipy.ai/download.

## What Anticipy for Mac does

It records a meeting from both sides: your microphone, and whatever your Mac is
playing, which is everyone else on the call. The two are kept as separate
tracks so nobody's words are mixed into anybody else's.

On this Mac, the audio becomes text. The text reaches the same Anticipy your
phone talks to, so what you agreed to in a meeting can become work. The audio
never leaves this Mac.

## Starting a recording

Press Start recording in the window, press Command-R, or click the microphone
in the menu bar. Press Stop, or Command-period, when the meeting ends.

When a call starts in Zoom, Teams, FaceTime, a browser or any other app,
Anticipy notices and offers: a notification, and a banner at the top of the
window. The click is yours. In Settings you can ask it to start on its own
instead.

## During a meeting

The window shows the clock, one sentence about the state of both wires, and
the transcript as it settles. Lines from your microphone are marked You; lines
from the call are marked Others. A line in grey italics is a phrase the
transcriber may still revise.

Type notes on the right at any time. They are saved as you type, into the same
folder as the recording, and are there when the meeting becomes a record.

## After a meeting

Every recording appears in the sidebar under the day it happened, with its
length. Click one to read the transcript and your notes. Click the title to
rename it.

Copy as Markdown puts the whole meeting, notes first, on the clipboard. Show in
Finder opens its folder. Move to Trash sends the folder to the Trash; nothing
is ever deleted outright.

## Permissions

macOS asks for the Microphone and for Speech Recognition during first run. The
first recording also asks for System Audio Recording, which is how the other
side of a call is heard; there is no way to ask for that one sooner.

If a switch is off, the app says so in as many words and can only send you to
System Settings, under Privacy & Security. It cannot ask again on its own.

## Privacy

Audio is written to Application Support, under Anticipy, under Meetings, and
stays there. Transcript text is sent to api.anticipy.ai when you are signed
in, over the same wire the phone app uses, with the same account.

If a line cannot be sent, it waits on this Mac and is sent when a connection
returns. The sidebar says how many are waiting. Nothing is dropped, and nothing
is sent about a meeting while you are signed out.

## Where things are

Settings, under the Anticipy menu or Command-comma: the account, whether
recording starts on its own, light or dark, and the meetings folder.

The menu bar microphone: start, stop, open the window, quit. The window can be
closed and reopened from the Dock or the menu bar without losing anything.

### For the curious: what is in a meeting folder

```
~/Library/Application Support/Anticipy/Meetings/20260907-143000-1a2b3c4d/
  meeting.json            the recorder's manifest: times, app, transcript lines
  owner-microphone-1.caf  your side, as recorded
  system-audio-1.caf      the call's side, as recorded
  owner.json              your title and notes, written by the window
```

`meeting.json` and the audio are written by the recorder and never edited by
the window. `owner.json` is written by the window and never read by the
recorder. Move the folder anywhere and both halves stay readable.
