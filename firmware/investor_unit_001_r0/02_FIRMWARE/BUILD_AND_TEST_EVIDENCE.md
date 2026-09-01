# Firmware build and static-test evidence

## Single candidate

- Release label: `HOLD_FOR_PHYSICAL_RELEASE_TEST_Anticipy_0.9.3_owner2_live_50mA.uf2`
- Size: 528,384 bytes
- SHA-256: `f246fc79ff9925fb427585e8babf4fe106ea1ad1c32a82b2c4351d3cc55ea5d6`
- Board target: `xiao_ble/nrf52840/sense`
- Application revision: `0.9.3-wed-live-bh-owner2`
- NCS: v2.7.0, commit `5cb85570ca43`
- Zephyr: commit `100befc70c74`
- Toolchain: Zephyr SDK 0.16.5, GCC 12.2.0

Clean build directories `candidate_live_owner_c` and
`candidate_live_owner_d` produced byte-identical UF2 files. Source host checks
for baseline invariants and owner-lock invariants pass.

## What static inspection proves

- One BLE connection and one stored bond.
- Zero-bond boots open a 120-second commissioning window.
- D7 owner-reset input and D0 haptic output are compiled in.
- Live Opus audio and nominal 50 mA application charge configuration.
- microSD/filesystem/SPI and offline audio-backlog application paths disabled.
- Audio, button, haptic, and application DFU-trigger paths check the stored
  owner connection.

## What static inspection does not prove

It does not prove iPhone compatibility, physical charge current, bootloader
behavior from USB insertion, motor-driver safety, closed-shell audio/RF,
system-off/wake, runtime, thermal behavior, or physical owner isolation.
Copying a UF2 alone also does not erase an old bond or external QSPI contents.

The commissioning link is encrypted after pairing but the 120-second window
does not authenticate the human. Bluetooth privacy, APPROTECT lock,
signed/verified boot, and bootloader authorization are not established. This
is why the binary remains explicitly held until `QA_RELEASE.md` passes.
