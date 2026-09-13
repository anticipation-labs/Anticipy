# Firmware ↔ phone collaboration handoff

Snapshot: 2026-09-13, released app source `a29bcea66565e8efe2d1710f0ba451d6af9a2548`
on `cloudflare-backend`. This is a development contract, **not permission to flash
or a claim that pendant audio works end to end**.

## The important boundary

The current iPhone app deliberately leaves `pendant.onOpusFrame` unset and
`pendantCapturing = false` in
[`startPendantTranscription`](../app/ios/Anticipy/AnticipyApp.swift).
It can pair/report device state, but it does not turn pendant Opus into speech.
The intended [local transcriber](../app/ios/Anticipy/Audio/LocalTranscriber.swift)
accepts PCM, not Opus. A reviewed on-device decoder and runtime bridge are missing.
Do not upload raw audio to a cloud decoder or show “listening” to conceal this gap.

```text
Mic → Opus encoder → encrypted, currently authorized BLE notifications
    → iPhone fragment assembler → [missing local Opus decoder / capture bridge]
    → on-device speech → owned transcript queue → brain → approved hand → receipt
```

An assembler regression is under repair: a sequence gap at a new frame boundary
can emit a partial old frame, and duplicate/reordered sequence arithmetic can
report an enormous false duration. The released assembler is not a trustworthy
airtime meter across arbitrary MTUs: sequence counts fragments, not codec frames.
Do not interpret every sequence increment as exactly ten milliseconds of audio.

## Source contract to preserve together

| Contract | Current source / requirement |
| --- | --- |
| Board/configuration | [Firmware candidate README](../firmware/source/README.rst), `prj_xiao_ble_sense_devkitv2-adafruit.conf` and its matching overlay. Do not substitute a board preset or prebuilt image by filename alone. |
| Codec | [codec.c](../firmware/source/src/codec.c), [config.h](../firmware/source/src/config.h): codec ID 20; 16 kHz mono, 160-sample codec frames. Decoder must validate format and bound output. |
| Service/data/format | [PendantManager.swift](../app/ios/Anticipy/BLE/PendantManager.swift) and [transport.c](../firmware/source/src/transport.c): UUIDs `19B10000/1/2-E8F2-537E-4F6C-D104768A1214`. Keep both ends aligned. |
| Packet header | Little-endian UInt16 notification sequence, UInt8 intra-frame fragment index, then payload. Fragment index zero begins a codec frame. Sequence advances on successful notification; an intentional whole-frame discard also steps it to signal a discontinuity. It is not a decoded-frame or duration counter. |
| Fragmentation | [transport_safety.c](../firmware/source/src/transport_safety.c) and [OpusFrameAssembler.swift](../app/ios/Anticipy/BLE/OpusFrameAssembler.swift). Test negotiated small/large MTUs, loss at every boundary, duplicate/reorder, wrap, malformed and oversized payloads, and disconnect/reset. Never concatenate stale sessions. |
| Capture authority | A current encrypted connection must perform a fresh audio-CCC write. Restored subscription state alone must not restart capture. Recheck authorization at PDM start and send. |
| Owner enrollment | Encryption and a persisted bond are not owner authentication. The candidate README explicitly says physical enrollment/erase or an allowlist is missing; first-central capture of the sole bond remains a release blocker. |
| Indicators/privacy | Verify capture indication before microphone start and stop on disconnect/revoke. Physical behavior needs bench proof, not just C assertions. |
| Recovery/battery | Preserve recovery access and obtain board-specific battery calibration. Current battery percentage is a conservative uncalibrated estimate. |
| Phone lifecycle | Bind capture/queue ownership to the signed-in owner, explicit permission and active session; no cross-account replay, hidden capture or cloud raw-audio fallback. |
| Task completion | BLE connection, a decoded frame and a transcript are intermediate stages. Completion needs the right owned task and a verified user-visible result. |

## Safe division of work

Omar: hardware/board identity, physical enrollment design, indicators, battery
calibration and candidate firmware build/hardware verification.
App lane: assembler/decoder contract, phone consent and lifecycle, on-device
speech and owned transcript replay. Coordinator: integration and release record.
Independent reviewer: security, loss/reconnect adversaries and evidence scope.

Keep hardware and app changes in reviewable branches. The app source of record
is `cloudflare-backend`; the separate hardware PRs currently target `main`.
Do not merge those lineages wholesale. Agree on packet/header/codec changes in
both directions before changing either endpoint. Preserve third-party licenses.

## What to send back with a firmware candidate

1. Exact source commit, board/bootloader revision, locked toolchain/build command,
   configuration/overlay, output hashes and build result.
2. Synthetic packet fixtures with expected decoded sample counts; include multiple
   MTUs, frame-boundary loss, duplicate/reorder, wrap and disconnect/reconnect.
3. Bench evidence for physical enrollment, wrong central refusal, encrypted CCC,
   restored-CCC refusal, revocation, indicators, recovery and power/battery behavior.
4. A joint phone run: exact installed build → explicit consent → local decode →
   on-device transcript with honest gaps → backend receipt. Record latency and
   failures without personal audio, credentials or identifying data in GitHub.

Host firmware checks can be run with
`sh firmware/source/tests/run_firmware_tests.sh` after reading the runner.
They are logic checks, not an embedded build, hardware test or flashing receipt.
The candidate README remains **non-production** until those missing gates close.
Do not treat checked-in `.hex`, `.uf2` or `.zip` files as safe to flash solely
because they exist. No device was flashed as part of this documentation update.

See the [full readiness board](EOD-READINESS-2026-09-13.md) and
[workspace reconciliation](WORKSPACE-SYNC-2026-09-13.md).
