// SPDX-License-Identifier: MIT

#include "recovery_usb.h"
#include "recovery_touch.h"
#include "watchdog.h"

#include <errno.h>

#include <hal/nrf_power.h>
#include <soc.h>
#include <zephyr/device.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/drivers/usb/usb_dc.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/usb/usb_device.h>

#define ADAFRUIT_UF2_RESET_MAGIC 0x57u
#define RECOVERY_TOUCH_POLL_INTERVAL_MS 20u

static const struct device *recovery_device;
static atomic_t recovery_usb_configured;
static struct k_spinlock recovery_state_lock;
static struct recovery_touch_state recovery_state;

static void recovery_poll(struct k_work *work_item);
K_WORK_DELAYABLE_DEFINE(recovery_poll_work, recovery_poll);

static void reset_touch_state(void)
{
    k_spinlock_key_t key = k_spin_lock(&recovery_state_lock);
    recovery_touch_reset(&recovery_state);
    k_spin_unlock(&recovery_state_lock, key);
}

static void recovery_usb_status_changed(
    enum usb_dc_status_code status,
    const uint8_t *parameter)
{
    (void)parameter;
    switch (status) {
    case USB_DC_CONFIGURED:
    case USB_DC_RESUME:
        reset_touch_state();
        atomic_set(&recovery_usb_configured, 1);
        (void)k_work_reschedule(&recovery_poll_work, K_NO_WAIT);
        break;
    case USB_DC_ERROR:
    case USB_DC_RESET:
    case USB_DC_CONNECTED:
    case USB_DC_DISCONNECTED:
    case USB_DC_SUSPEND:
        atomic_clear(&recovery_usb_configured);
        (void)k_work_cancel_delayable(&recovery_poll_work);
        reset_touch_state();
        break;
    default:
        break;
    }
}

static void recovery_poll(struct k_work *work_item)
{
    (void)work_item;
    if (!atomic_get(&recovery_usb_configured)) {
        return;
    }

    uint32_t baud_rate = 0u;
    uint32_t dtr = 0u;
    int baud_error = uart_line_ctrl_get(
        recovery_device, UART_LINE_CTRL_BAUD_RATE, &baud_rate);
    int dtr_error = uart_line_ctrl_get(
        recovery_device, UART_LINE_CTRL_DTR, &dtr);

    bool reset_requested = false;
    k_spinlock_key_t key = k_spin_lock(&recovery_state_lock);
    if (baud_error != 0 || dtr_error != 0) {
        recovery_touch_reset(&recovery_state);
    } else {
        reset_requested = recovery_touch_update(
            &recovery_state,
            true,
            baud_rate,
            dtr != 0u);
    }
    k_spin_unlock(&recovery_state_lock, key);

    if (reset_requested) {
        /*
         * The installed Adafruit nRF52 bootloader consumes GPREGRET 0x57 as
         * its explicit UF2 request. Detach first so the host observes a clean
         * application-to-bootloader USB transition.
         */
        (void)usb_dc_detach();
        /*
         * The nRF52 watchdog survives a soft reset and cannot be stopped, so
         * the bootloader inherits it. Feed it immediately before resetting so
         * the UF2 volume gets a full, fresh timeout window to be written to.
         */
        watchdog_feed();
        nrf_power_gpregret_set(
            NRF_POWER, ADAFRUIT_UF2_RESET_MAGIC);
        __DSB();
        NVIC_SystemReset();
    }
    if (atomic_get(&recovery_usb_configured)) {
        (void)k_work_reschedule(
            &recovery_poll_work,
            K_MSEC(RECOVERY_TOUCH_POLL_INTERVAL_MS));
    }
}

int recovery_usb_start(void)
{
    recovery_device =
        DEVICE_DT_GET_ONE(zephyr_cdc_acm_uart);
    if (!device_is_ready(recovery_device)) {
        return -ENODEV;
    }
    reset_touch_state();
    atomic_clear(&recovery_usb_configured);
    return usb_enable(recovery_usb_status_changed);
}
