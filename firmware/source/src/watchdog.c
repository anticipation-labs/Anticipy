// SPDX-License-Identifier: MIT

#include "watchdog.h"

#include <errno.h>

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/watchdog.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(watchdog, CONFIG_LOG_DEFAULT_LEVEL);

#define WATCHDOG_NODE DT_ALIAS(watchdog0)

#if !DT_NODE_HAS_STATUS(WATCHDOG_NODE, okay)
#error "watchdog0 alias is missing or disabled; the pendant has no reset button"
#endif

static const struct device *watchdog_device;
static int watchdog_channel = -1;

int watchdog_start(void)
{
    const struct device *device = DEVICE_DT_GET(WATCHDOG_NODE);
    if (!device_is_ready(device)) {
        return -ENODEV;
    }

    /*
     * WDT_FLAG_RESET_SOC with no pre-reset callback. A callback would run
     * application code on an already-wedged system; the whole point of this
     * watchdog is an unconditional hardware reset that does not depend on the
     * firmware still being sane. The nRF52 WDT has no windowed mode, so the
     * lower bound must be zero.
     */
    const struct wdt_timeout_cfg timeout = {
        .window = {
            .min = 0u,
            .max = WATCHDOG_TIMEOUT_MS,
        },
        .callback = NULL,
        .flags = WDT_FLAG_RESET_SOC,
    };

    int channel = wdt_install_timeout(device, &timeout);
    if (channel < 0) {
        return channel;
    }

    /*
     * WDT_OPT_PAUSE_HALTED_BY_DBG only.
     *
     * WDT_OPT_PAUSE_IN_SLEEP is deliberately NOT set. The pendant spends
     * almost all of its life with the CPU asleep between BLE connection
     * events, so a watchdog that paused in sleep would effectively never
     * expire and could not recover the exact low-power hang it exists to
     * catch. Pausing under a halted debugger is kept so an attached debug
     * session does not trigger spurious resets.
     */
    int err = wdt_setup(device, WDT_OPT_PAUSE_HALTED_BY_DBG);
    if (err != 0) {
        return err;
    }

    watchdog_device = device;
    watchdog_channel = channel;
    LOG_INF("Watchdog armed: %u ms timeout, %u ms feed interval",
            (unsigned int)WATCHDOG_TIMEOUT_MS,
            (unsigned int)WATCHDOG_FEED_INTERVAL_MS);
    return 0;
}

void watchdog_feed(void)
{
    if (watchdog_device == NULL || watchdog_channel < 0) {
        return;
    }
    (void)wdt_feed(watchdog_device, watchdog_channel);
}
