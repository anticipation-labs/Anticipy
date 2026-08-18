Anticipy live-stream firmware candidate
=======================================

This source package contains one fail-closed candidate for the Seeed XIAO
nRF52840 Sense board. It captures live audio only after an encrypted current
connection performs a fresh audio-CCC write. Offline recording, SD/filesystem
support, application DFU, NFC, speaker, button, haptic, accelerometer, legacy
board presets, host recording clients, and scripts that copy firmware to a
mounted device are intentionally absent.

The only selected application configuration is
``prj_xiao_ble_sense_devkitv2-adafruit.conf`` with
``overlay/xiao_ble_sense_devkitv2-adafruit_module.overlay``. Builds are
performed by the repository's locked candidate pipeline; this directory does
not contain an operator flash script.

Safety status
-------------

This is not production firmware. Encryption and one persisted bond do not
authenticate an owner: without a physical enrollment/erase gesture or an
allowlist, the first nearby central can still take the sole bond. The battery
percentage is a conservative development estimate based on an uncalibrated
voltage curve. A pinned embedded build, physical calibration, consent and
reconnect tests, indicator tests, and hardware verification remain required
before release or flashing.
