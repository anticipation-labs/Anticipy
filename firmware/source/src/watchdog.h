// SPDX-License-Identifier: MIT

#ifndef ANTICIPY_WATCHDOG_H
#define ANTICIPY_WATCHDOG_H

#include <stdbool.h>

/*
 * Hardware watchdog (nRF52840 WDT, devicetree alias watchdog0 -> wdt0).
 *
 * This pendant has no usable RESET button, so an unrecovered firmware hang is
 * indistinguishable from a dead device. The watchdog is the only mechanism
 * that can restart a wedged application without physical access.
 *
 *
 * WHY THE TIMEOUT IS THIS LONG
 * ----------------------------
 * On nRF52 the WDT is NOT cleared by a soft reset (NVIC_SystemReset). It is
 * cleared only by pin reset, power-on reset, brownout, or a watchdog reset
 * itself. It also cannot be stopped or reconfigured once started. Therefore
 * once this application arms the watchdog, the Adafruit bootloader INHERITS a
 * running watchdog every time we deliberately reset into it -- via GPREGRET
 * 0x57 (UF2, recovery_usb.c) or GPREGRET 0xA8 (BLE OTA, transport.c).
 *
 * Whether that bootloader feeds the watchdog could not be verified: no
 * Adafruit bootloader source is present on this machine, only the opaque
 * binary at ~/Anticipy/bootloader0.9.0.uf2. The timeout below is therefore
 * chosen to be safe under the WORST assumption -- that the bootloader does
 * not feed it at all.
 *
 * If the watchdog fired partway through a UF2 drag-and-drop or a legacy BLE
 * OTA transfer, it would reset the SoC mid-write and could leave a truncated
 * application image: a permanent brick on the owner's only pendant. That risk
 * is asymmetric against the benefit of fast hang detection, because a hang
 * can also be cleared by letting the battery run down (a real power-on reset)
 * whereas a truncated flash write cannot be cleared at all.
 *
 * 15 minutes comfortably exceeds a UF2 copy (seconds) and a legacy BLE DFU of
 * a ~500 KB image (single-digit minutes), while still guaranteeing that a
 * hung pendant returns to service on its own in bounded time instead of never.
 *
 * If the owner later confirms on hardware that the installed bootloader does
 * feed the watchdog, this can safely drop to single-digit seconds. Until then,
 * treat this constant as a flash-gating decision, not a tunable.
 */
#define WATCHDOG_TIMEOUT_MS 900000u

/*
 * Feed cadence. Two orders of magnitude below the timeout, so a single missed
 * or delayed feed can never cause a spurious reset. Waking the main thread
 * once a second is negligible against the BLE connection event load.
 */
#define WATCHDOG_FEED_INTERVAL_MS 1000u

/*
 * Install and start the watchdog. Returns 0 on success, or a negative errno
 * if the watchdog is unavailable. Callers must treat failure as non-fatal:
 * losing hang recovery is bad, but refusing to boot removes the recovery
 * hatches entirely, which is worse.
 *
 * Must be called only AFTER every initialization step that can fail and
 * return early from main(). An armed watchdog with no live feeder resets the
 * SoC straight back into the same failing path, and a boot loop tears down
 * the USB CDC endpoint repeatedly, which would make the 1200-baud recovery
 * touch nearly impossible to land.
 */
int watchdog_start(void);

/*
 * Feed the watchdog. Safe to call before watchdog_start() or after it has
 * failed; it is a no-op in that case. Also called immediately before each
 * deliberate reset into the bootloader (recovery_usb.c, transport.c) to hand
 * the bootloader a full, fresh timeout window.
 */
void watchdog_feed(void);

#endif
