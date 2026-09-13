# Anticipy pendant firmware — Omi fork plan

Base: https://github.com/BasedHardware/omi (`omi/firmware/`, MIT license —
fork/rebrand/sell is legal; keep the MIT notice in the fork).

Why fork instead of write: Omi's Zephyr firmware + app already implement the
whole spec — BLE audio service (UUID `19B10000-E8F2-537E-4F6C-D104768A1214`,
Opus/PCM 16 kHz mono), offline recording to storage when disconnected with
back-sync on reconnect (DevKit2 behavior), button events, published protocol
(docs.omi.me/doc/developer/Protocol). The protocol-compatible Omi iOS app
works for bring-up day 1; the Anticipy-branded Flutter fork follows.

## Build (nRF Connect SDK)

```bash
pip install west
west init -m https://github.com/anticipy/omi anticipy-fw && cd anticipy-fw
west update
cd omi/firmware/devkit          # DevKit2 target = XIAO nRF52840 Sense class hw
west build -b xiao_ble_sense -- -DOVERLAY_CONFIG=overlay-anticipy.conf
```

Flash: double-tap reset → XIAO mounts as a UF2 drive → copy
`build/zephyr/zephyr.uf2`. No debugger needed.

## Anticipy changes (small, contained)

1. **Device name**: `CONFIG_BT_DEVICE_NAME="Anticipy"` in the overlay conf.
2. **Haptic driver** (new `src/haptic.c`): GPIO D3, patterns —
   1×60 ms buzz = BLE connected, 2×60 ms = went offline (recording locally),
   3×60 ms = backlog sync complete, 200 ms = button long-press acknowledged.
   Hook the existing connection callbacks and button handler; ~40 lines:

   ```c
   static const struct gpio_dt_spec haptic =
       GPIO_DT_SPEC_GET(DT_ALIAS(haptic), gpios);
   void haptic_buzz(int n) {
       for (int i = 0; i < n; i++) {
           gpio_pin_set_dt(&haptic, 1); k_msleep(60);
           gpio_pin_set_dt(&haptic, 0); k_msleep(80);
       }
   }
   ```

   Devicetree overlay: alias `haptic` → `&gpio0` pin for D3.
3. **Storage target**: DevKit2 code writes to SD over SPI — keep it for the
   microSD variant; for the W25Q128 variant switch the storage backend to the
   Zephyr flash API on the same SPI bus (littlefs on `spi-nor`).
4. **VAD**: keep Omi's energy gate in capture; full Silero VAD runs
   phone-side in the app pipeline (as Omi does).

## Status — honest

Nothing here is built or flashed yet. The fork, overlay, and haptic patch are
Day-1 work once the repo fork exists; budget one bench day for storage-backend
bring-up on real hardware. Do not claim runtimes or backlog behavior until
QA_CHECKLIST steps pass on unit #1.
