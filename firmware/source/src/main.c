#include <stdbool.h>
#include <stdint.h>
#include <errno.h>

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

#include "codec.h"
#include "config.h"
#include "led.h"
#include "mic.h"
#include "recovery_usb.h"
#include "transport.h"
#include "watchdog.h"

#define BOOT_BLINK_DURATION_MS 600
#define BOOT_PAUSE_DURATION_MS 200

LOG_MODULE_REGISTER(main, CONFIG_LOG_DEFAULT_LEVEL);

/*
 * A FULL RING IS THE RADIO BEING BEHIND, NOT THE STREAM BEING OVER.
 *
 * Both handlers below used to hand every non-zero result to
 * transport_audio_fault, and that call switches the microphone off for the
 * remainder of the connection — recoverable only by a fresh CCC write, which
 * the phone does not send while a link is up. So a TX ring that filled for
 * 320ms, or a PCM ring that filled for a second, ended capture for the whole
 * session. Both rings drain on their own; neither says the stream is invalid.
 *
 * Dropping the block instead loses a tenth of a second of audio and keeps the
 * microphone alive, which is the trade Omi makes in the same place. There is
 * deliberately no counter here: the transport owns the loss count, because a
 * number kept in two places is a number that disagrees with itself.
 */
static void codec_handler(uint8_t *data, size_t len)
{
    if (!transport_audio_is_active()) {
        return;
    }

    int err = broadcast_audio_packets(data, len);
    if (err == -ENOSPC) {
        LOG_WRN("TX ring full, dropping one audio frame");
        return;
    }
    if (err != 0 && err != -ECANCELED) {
        LOG_ERR("Failed to queue audio packet: %d", err);
        transport_audio_fault(err);
    }
}

static void handle_mic_samples(int16_t *buffer)
{
    if (!transport_audio_is_active()) {
        return;
    }

    int err = codec_receive_pcm(buffer, MIC_BUFFER_SAMPLES);
    if (err == -ENOSPC) {
        LOG_WRN("PCM ring full, dropping one microphone block");
        return;
    }
    if (err != 0 && err != -ECANCELED) {
        LOG_ERR("Failed to queue PCM data: %d", err);
        transport_audio_fault(err);
    }
}

static void handle_mic_error(int error)
{
    transport_audio_fault(error);
}

void bt_ctlr_assert_handle(char *name, int type)
{
    /*
     * Controller state is no longer trustworthy. Cut microphone power
     * directly, leave the recording indicator conservatively lit, and enter
     * Zephyr's fatal path instead of returning to corrupt streaming state.
     */
    mic_emergency_power_off();
    (void)set_led_blue(true);
    LOG_ERR("Bluetooth controller assertion: %s (type %d)",
            name ? name : "NULL", type);
    k_panic();
}

static int boot_led_sequence(void)
{
    int err = set_led_red(true);
    if (err != 0) {
        return err;
    }
    k_msleep(BOOT_BLINK_DURATION_MS);
    if (set_led_red(false) != 0) {
        return -EIO;
    }
    k_msleep(BOOT_PAUSE_DURATION_MS);

    if (set_led_green(true) != 0) {
        return -EIO;
    }
    k_msleep(BOOT_BLINK_DURATION_MS);
    if (set_led_green(false) != 0) {
        return -EIO;
    }
    k_msleep(BOOT_PAUSE_DURATION_MS);

    if (set_led_blue(true) != 0) {
        return -EIO;
    }
    k_msleep(BOOT_BLINK_DURATION_MS);
    if (set_led_blue(false) != 0) {
        return -EIO;
    }
    k_msleep(BOOT_PAUSE_DURATION_MS);

    if (set_led_red(true) != 0 ||
        set_led_green(true) != 0 ||
        set_led_blue(true) != 0) {
        return -EIO;
    }
    k_msleep(BOOT_BLINK_DURATION_MS);
    if (set_led_red(false) != 0 ||
        set_led_green(false) != 0 ||
        set_led_blue(false) != 0) {
        return -EIO;
    }
    return 0;
}

static void show_startup_failure(void)
{
    for (int index = 0; index < 5; index++) {
        set_led_red(true);
        k_msleep(200);
        set_led_red(false);
        k_msleep(200);
    }
}

int main(void)
{
    /*
     * RECOVERY FIRST -- BEFORE ANY GATE THAT CAN RETURN EARLY.
     *
     * This call used to sit after led_start() and boot_led_sequence(), both
     * of which return from main() on failure. Because
     * CONFIG_USB_DEVICE_INITIALIZE_AT_BOOT=n, usb_enable() only ever runs
     * from inside recovery_usb_start(); nothing else brings the CDC endpoint
     * up. A dead or mis-wired LED therefore took the ONLY cable route into
     * the bootloader down with it, on a device whose RESET button cannot be
     * pressed. The recovery surface must not depend on any peripheral it
     * does not itself need.
     *
     * Failure here stays non-fatal for the same reason it always was: USB
     * recovery is a maintenance path, not a recording precondition, so BLE
     * (including the legacy DFU hatch in transport.c) must still come up if
     * the host has no data connection or USB cannot enumerate.
     */
    int err = recovery_usb_start();
    if (err != 0) {
        LOG_WRN("Cable recovery unavailable: %d", err);
    }

    err = led_start();
    if (err != 0) {
        /*
         * The LEDs are the only physical recording indicator. Refuse to
         * initialize the microphone or advertise when they are unavailable.
         * Cable recovery above is already live, so this early return no
         * longer strands the device.
         */
        LOG_ERR("Recording indicator unavailable: %d", err);
        return err;
    }
    err = boot_led_sequence();
    if (err != 0) {
        LOG_ERR("Recording indicator self-test failed: %d", err);
        return err;
    }

    set_codec_callback(codec_handler);
    set_codec_error_callback(handle_mic_error);
    err = codec_start();
    if (err != 0) {
        LOG_ERR("Failed to initialize codec: %d", err);
        show_startup_failure();
        return err;
    }

    set_mic_callback(handle_mic_samples);
    set_mic_error_callback(handle_mic_error);
    err = mic_init();
    if (err != 0) {
        LOG_ERR("Failed to initialize microphone: %d", err);
        show_startup_failure();
        return err;
    }

    /*
     * Advertising is the startup commit. The codec, microphone, and physical
     * indicator are ready before an iPhone can discover codec ID 20.
     */
    err = transport_start();
    if (err != 0) {
        LOG_ERR("Failed to start transport: %d", err);
        show_startup_failure();
        return err;
    }

    /*
     * Arm the watchdog LAST, after every gate above that can return from
     * main(). An armed watchdog whose feeder has exited would reset the SoC
     * straight back into the same failing initialization forever, and each
     * reset tears down the USB CDC endpoint that the 1200-baud recovery touch
     * needs to stay up long enough to arm. On a pendant with no reset button
     * a boot loop is strictly worse than a hang, so the watchdog is only
     * armed once reaching the feeding loop below is guaranteed.
     *
     * Non-fatal on failure: losing hang recovery is bad, exiting main() and
     * killing both recovery hatches is worse.
     */
    int watchdog_error = watchdog_start();
    if (watchdog_error != 0) {
        LOG_WRN("Watchdog unavailable; hang recovery disabled: %d",
                watchdog_error);
    }

    LOG_INF("Anticipy live-stream firmware initialized");
    while (true) {
        watchdog_feed();
        k_sleep(K_MSEC(WATCHDOG_FEED_INTERVAL_MS));
    }
}
