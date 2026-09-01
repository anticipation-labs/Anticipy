#include <zephyr/drivers/watchdog.h>
#include <zephyr/logging/log.h>
#include <zephyr/kernel.h>

LOG_MODULE_REGISTER(wdog_facade, CONFIG_LOG_DEFAULT_LEVEL);

/* Keep this deliberately long until the installed Adafruit bootloader is
 * hardware-verified to feed an inherited nRF52 watchdog during UF2/DFU. */
#define WATCHDOG_TIMEOUT_MS 900000U

static const struct device *wdt_dev;
static int wdt_channel_id;
static bool watchdog_running;

void watchdog_feed(void)
{
    if (watchdog_running) {
        int ret = wdt_feed(wdt_dev, wdt_channel_id);
        if (ret < 0) {
            LOG_ERR("Watchdog feed failed: %d", ret);
        }
    }
}

int watchdog_init(void)
{
    int ret;
    struct wdt_timeout_cfg wdt_config = {0};

    // Get watchdog device (nRF52840 uses wdt0 label)
    wdt_dev = DEVICE_DT_GET(DT_NODELABEL(wdt0));
    if (!device_is_ready(wdt_dev)) {
        LOG_ERR("Watchdog device not ready");
        return -ENODEV;
    }

    // Configure watchdog timeout
    wdt_config.flags = WDT_FLAG_RESET_SOC;         // Reset entire SoC on timeout
    wdt_config.window.min = 0U;                    // No minimum window
    wdt_config.window.max = WATCHDOG_TIMEOUT_MS;
    wdt_config.callback = NULL;                    // No callback, just reset

    // Install watchdog timeout
    wdt_channel_id = wdt_install_timeout(wdt_dev, &wdt_config);
    if (wdt_channel_id < 0) {
        LOG_ERR("Watchdog install failed: %d", wdt_channel_id);
        return wdt_channel_id;
    }

    // Start watchdog
    ret = wdt_setup(wdt_dev, WDT_OPT_PAUSE_HALTED_BY_DBG);
    if (ret < 0) {
        LOG_ERR("Watchdog setup failed: %d", ret);
        return ret;
    }

    watchdog_running = true;
    LOG_INF("Watchdog initialized (timeout: %u ms, channel: %d)",
            WATCHDOG_TIMEOUT_MS, wdt_channel_id);
    return 0;
}

int watchdog_deinit(void)
{
    if (!watchdog_running) {
        return 0;
    }

    int ret = wdt_disable(wdt_dev);
    if (ret == 0) {
        watchdog_running = false;
    }
    return ret;
}
