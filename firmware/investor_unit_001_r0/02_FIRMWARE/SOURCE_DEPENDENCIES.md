# Source dependency boundary

The application files and exact compiled configuration are reviewable in this
draft PR. The unchanged vendored Opus 1.2.1 directory is carried in the
verified builder archive rather than duplicated in this PR.

To reproduce the held candidate, copy the archive's
`02_FIRMWARE/SOURCE/anticipy_friday_core/src/lib/opus-1.2.1/` directory into
the matching source path, use the NCS/Zephyr/toolchain versions recorded in
`02_FIRMWARE/CANDIDATE_DO_NOT_SHIP_UNTIL_QA/BUILD_METADATA.json`, and build for
`xiao_ble/nrf52840/sense` with the listed base config, extra config, and
overlay. Two clean builds must produce the recorded UF2 SHA-256 before any
physical test begins.

The live candidate deliberately omits the development QSPI/microSD source and
configuration from this PR. The compiled config is the authority: Unit 001 is
live-stream only and has no releasable offline-audio path.
