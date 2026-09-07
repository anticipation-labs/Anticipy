# Pendant audio: status and bounded follow-up

Observed 2026-09-07 against `a492703512881a935962e62e61b0d019a83b355a` on
`cloudflare-backend`. This investigation changed no product source, build
settings, firmware, or device state. It did not activate Bluetooth, capture
audio, use paid models, or flash a pendant.

## Plain-language answer

There is no pile of pending audio callbacks to clear. A callback is the function
the phone would call when a sound packet arrives. The app deliberately has **no
audio consumer connected**. It can pair over Bluetooth and reconstruct compressed
sound packets, but it cannot turn those packets into words yet.

That missing piece is a local Opus decoder plus its integration into the local
speech engine. It is unrelated to ordinary phone-microphone transcription. Given
the user's instruction to deprioritize hardware without a current pendant trial,
this should not block the browser, API, calendar, or texting repairs.

## What is and is not wired

| Stage | Evidence in this revision | Status |
|---|---|---|
| Bluetooth connection and audio notifications | `app/ios/Anticipy/BLE/PendantManager.swift:252–258,287–309` | Source connects, subscribes, assembles packets. This audit did not prove a physical connection. |
| Compressed frame assembly | `app/ios/Anticipy/BLE/OpusFrameAssembler.swift:38–80` | Bounded transport assembly exists. |
| Frame consumer | `app/ios/Anticipy/AnticipyApp.swift:2088–2107` | Both start and stop explicitly set `pendant.onOpusFrame = nil`; `pendantCapturing = false`. |
| Packet-loss reporting | `PendantManager.swift:308–309`; `AnticipyApp.swift:2098–2100` | The gap callback is connected even while audio consumption is disabled. Additional precision defects are recorded below. |
| Opus → PCM decoder | iOS source, `project.yml`, and Xcode project inspected | No decoder implementation or decoder dependency is linked into the iOS target. The firmware contains libopus source; that does not link it into iOS. |
| PCM → local text | `app/ios/Anticipy/Audio/LocalTranscriber.swift:20–99` | Implementation accepts PCM and chooses a local speech engine, but there are no `LocalTranscriber(...)` construction sites in the app. |
| Honest user status | `app/ios/Anticipy/Views/ContentView.swift:1550–1583` | The connected state says the phone cannot turn pendant sound into words and points to the phone microphone. |
| Current firmware build / flash | `firmware/source/ANTICIPY_SOURCE_RECEIPT.json` | `artifact_built`, `flash_performed`, and `physical_hardware_verified` are all false. These are source-receipt facts, not a claim that no physical pendant exists. |

The accurate description is **briefly assembled BLE packets with no downstream
consumer**, not a complete capture/transcription pipeline. Wiring an arbitrary
closure into `onOpusFrame` would not supply the missing decoder.

## Checks performed

`python3 overnight/firmware_gate.py` returned **2 (UNPROVEN)**. Its host-compiled
transport checks and source backpressure checks passed. The firmware build,
flash, and physical-stream requirements remain unproven. Output is retained in
`work/audit/pendant-firmware-status.log`.

No `west`, `arm-none-eabi-gcc`, or `cmake` executable was found on the current
shell PATH. No firmware build/flash task was found in `.github/workflows`.
These are environment observations, not a claim about all machines or all CI.

The parent agent is running the full iOS baseline separately at
`work/audit/repair-next-baseline-ios.log`; this document does not claim its final
result before that run completes.

## Additional transport issues reproduced without hardware

The existing packet assembler has two specific defects to address before a
pendant trial. Neither concerns the meaning of human words.

1. **Duplicate and backwards sequence packets report enormous lost time.** The
   wrap calculation in `OpusFrameAssembler.swift:52–61` turns packet `100 → 100`
   into **655.35 seconds** and `100 → 99` into **655.34 seconds**. A duplicate
   packet does not establish that almost eleven minutes of audio were lost.
2. **A sequence gap at the next frame boundary still emits the previous frame.**
   Input `index=100,counter=0,[1,2]`, followed by `index=102,counter=0,[5,6]`, emits
   `[1,2]`. The missing packet could have been the previous frame's continuation;
   the assembler cannot prove that frame is complete, but hands it onward.

There is also a precision assumption to resolve: `packetSeconds = 0.010` treats
every missing BLE notification as a whole audio frame. Firmware increments the
sequence per **fragment**, and its transport supports multiple fragments per
codec frame (`firmware/source/src/transport.c:1034–1081`). The fixed conversion
is valid only for the single-notification frame geometry. Firmware's own
`discard_pending_frame` comment at lines 1010–1016 discusses that limitation.

The existing production assembler was compiled, unchanged, with the following
probe. Output is retained at `work/audit/pendant-transport-probe/results.txt`:

```swift
import Foundation
func packet(_ index: UInt16, _ counter: UInt8, _ bytes: [UInt8] = [1, 2]) -> Data {
    Data([UInt8(index & 255), UInt8(index >> 8), counter] + bytes)
}
var duplicate = OpusFrameAssembler()
_ = duplicate.accept(packet(100, 0))
_ = duplicate.accept(packet(100, 0))
print(duplicate.takeGapSeconds()) // observed 655.35
var backward = OpusFrameAssembler()
_ = backward.accept(packet(100, 0))
_ = backward.accept(packet(99, 0))
print(backward.takeGapSeconds()) // observed 655.34
var boundary = OpusFrameAssembler()
_ = boundary.accept(packet(100, 0, [1, 2]))
print(boundary.accept(packet(102, 0, [5, 6]))?.count ?? 0) // observed 2
```

Reproduce by saving the snippet as `main.swift` and running:

```sh
swiftc app/ios/Anticipy/BLE/OpusFrameAssembler.swift main.swift -o pendant-probe
./pendant-probe
```

These synthetic byte inputs demonstrate source behavior. They do not prove the
frequency of those conditions on the real BLE link.

## Minimum sensible implementation when hardware becomes a priority

1. Define the supported codec and frame geometry from the characteristic value;
   reject unsupported codecs explicitly rather than feeding unknown bytes into
   speech recognition. The manager currently reads the codec characteristic but
   does not process its returned value.
2. Add a pinned, licensed local decoder and tests using real known Opus frames.
   No raw audio should go to a remote decoder.
3. Repair sequence continuity and incomplete-frame handling. Report an unknown
   gap when exact duration is not observable; do not manufacture precise time
   from a fragment counter alone.
4. Connect decoded PCM to `LocalTranscriber`, including permission completion,
   startup failure, stop/reconnect, bounded buffering, and explicit capture state.
   Only then connect final transcripts to the existing `source="pendant"` path.
5. Build and test firmware on the target, then verify a physical stream against
   the shipped iOS build: transcript arrival, gaps, reconnect, and no off-device
   raw-audio transmission. Host tests alone cannot establish those outcomes.

The implementation should be transport and lifecycle code. No word lists,
semantic regex, or instructions inferred from speech belong in this layer.
