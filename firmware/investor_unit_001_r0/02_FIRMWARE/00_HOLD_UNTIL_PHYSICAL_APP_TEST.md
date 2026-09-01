# Unit 001 owner2 firmware candidate

> **HOLD FOR PHYSICAL APP/HARDWARE RELEASE TESTS**

Flash only:

`HOLD_FOR_PHYSICAL_RELEASE_TEST_Anticipy_0.9.3_owner2_live_50mA.uf2`

- Size: 528,384 bytes
- SHA-256: `f246fc79ff9925fb427585e8babf4fe106ea1ad1c32a82b2c4351d3cc55ea5d6`
- Two clean builds (`candidate_live_owner_c` and `_d`) are byte-identical.
- Board: `xiao_ble/nrf52840/sense`
- Base config: `prj_xiao_ble_sense_devkitv2-adafruit.conf`
- Extra config: `candidate_live_button_haptic.conf`
- Overlay: `overlay/xiao_ble_sense_no_sd.overlay`

The compiled config and ELF show revision `0.9.3-wed-live-bh-owner2`, one
connection/bond, Secure Connections pairing, bonding/settings/filter accept
list, D7 button, D0 haptic, battery service, and live Opus audio. microSD,
filesystem, SPI, USB application stack, and QSPI audio backlog are disabled.

## Before first power for commissioning

1. Identify a headerless XIAO nRF52840 Sense.
2. Perform a controlled **full internal erase**, then restore the compatible
   bootloader/layout and candidate application. Copying only UF2 can preserve
   an old settings partition/bond. Sanitize external QSPI on any reused board.
3. Power in a private room. Any boot with zero stored bonds opens an
   unauthenticated 120-second Just-Works commissioning window; pair the intended
   iPhone immediately.
4. Allow more than two seconds for settings persistence, power-cycle, and prove
   owner reconnect and second-phone rejection.

## Physical release tests

- Phone A pair/stream/haptic/button/reconnect; Phone B rejected.
- Ten-second D7 owner reset then Phone B can own, if the switch is fitted;
  otherwise rehearse the controlled SWD recovery path.
- Exact TestFlight build receives intelligible live audio and reports gaps.
- Battery-branch charge current measured from USB insertion through bootloader,
  application, termination, and recharge.
- Transistor/flyback polarity, motor current/thermal/EMI/microphone-noise tests.
- Closed-shell radio, runtime, system-off/wake, watchdog, and abuse tests.

## Security boundary

The link is encrypted and application data paths are filtered to the stored
owner identity after commissioning. The commissioning window does not
cryptographically authenticate the person. Bluetooth privacy, APPROTECT,
signed/verified boot, and bootloader authorization were not established. The
application DFU trigger is owner-gated; do not claim secure owner-only OTA.

Live audio is discarded without an authorized subscriber. There is no offline
recovery of a phone-disconnect interval.
