#include "mic.h"

#include <haly/nrfy_gpio.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

#include "config.h"
#include "led.h"
#include "nrfx_clock.h"
#include "nrfx_pdm.h"
#include "utils.h"

LOG_MODULE_REGISTER(mic, CONFIG_LOG_DEFAULT_LEVEL);

//
// Port of this code: https://github.com/Seeed-Studio/Seeed_Arduino_Mic/blob/master/src/hardware/nrf52840_adc.cpp
//

static int16_t _buffer_0[MIC_BUFFER_SAMPLES];
static int16_t _buffer_1[MIC_BUFFER_SAMPLES];
static volatile uint8_t _next_buffer_index = 0;
static volatile mix_handler _callback = NULL;
static volatile bool _capture_enabled;
static bool _pdm_initialized;

static void pdm_irq_handler(nrfx_pdm_evt_t const *event)
{
    // Ignore error (how to handle?)
    if (event->error) {
        LOG_ERR("PDM error: %d", event->error);
        return;
    }

    // Assign buffer
    if (event->buffer_requested && _capture_enabled) {
        LOG_DBG("Audio buffer requested");
        if (_next_buffer_index == 0) {
            nrfx_pdm_buffer_set(_buffer_0, MIC_BUFFER_SAMPLES);
            _next_buffer_index = 1;
        } else {
            nrfx_pdm_buffer_set(_buffer_1, MIC_BUFFER_SAMPLES);
            _next_buffer_index = 0;
        }
    }

    // Release buffer
    if (event->buffer_released) {
        LOG_DBG("Audio buffer requested");
        if (_capture_enabled && _callback) {
            _callback(event->buffer_released);
        }
    }
}

int mic_start()
{

    // Start the high frequency clock
    if (!nrf_clock_hf_is_running(NRF_CLOCK, NRF_CLOCK_HFCLK_HIGH_ACCURACY)) {
        nrf_clock_task_trigger(NRF_CLOCK, NRF_CLOCK_TASK_HFCLKSTART);
    }

    // Configure PDM
    nrfx_pdm_config_t pdm_config = NRFX_PDM_DEFAULT_CONFIG(PDM_CLK_PIN, PDM_DIN_PIN);
    pdm_config.gain_l = MIC_GAIN;
    pdm_config.gain_r = MIC_GAIN;
    pdm_config.interrupt_priority = MIC_IRC_PRIORITY;
    pdm_config.clock_freq = NRF_PDM_FREQ_1280K;
    pdm_config.mode = NRF_PDM_MODE_MONO;
    pdm_config.edge = NRF_PDM_EDGE_LEFTFALLING;
    pdm_config.ratio = NRF_PDM_RATIO_80X;
    IRQ_DIRECT_CONNECT(PDM_IRQn, 5, nrfx_pdm_irq_handler, 0); // IMPORTANT!
    if (nrfx_pdm_init(&pdm_config, pdm_irq_handler) != NRFX_SUCCESS) {
        LOG_ERR("Audio unable to initialize PDM");
        return -1;
    }
    _pdm_initialized = true;

    // Power on Mic
    nrfy_gpio_cfg_output(PDM_PWR_PIN);
    nrfy_gpio_pin_set(PDM_PWR_PIN);

    // Start PDM
    _capture_enabled = true;
    if (nrfx_pdm_start() != NRFX_SUCCESS) {
        _capture_enabled = false;
        LOG_ERR("Audio unable to start PDM");
        return -1;
    }

    LOG_INF("Audio microphone started");
    return 0;
}

void set_mic_callback(mix_handler callback)
{
    _callback = callback;
}

void mic_off()
{
    /* Stop the producer before storage is drained/suspended. nrfx may release
     * one final DMA buffer after STOP, so gate the callback first. */
    _capture_enabled = false;
    if (!_pdm_initialized) {
        return;
    }

    nrfx_err_t result = nrfx_pdm_stop();
    if (result != NRFX_SUCCESS && result != NRFX_ERROR_BUSY) {
        LOG_ERR("PDM stop failed: %d", result);
    }
    for (int i = 0; i < 100 && nrfx_pdm_enable_check(); ++i) {
        k_msleep(1);
    }
    nrfy_gpio_pin_clear(PDM_PWR_PIN);
}

void mic_on()
{
    if (!_pdm_initialized) {
        LOG_ERR("PDM restart requested before initialization");
        return;
    }

    nrfy_gpio_pin_set(PDM_PWR_PIN);
    _capture_enabled = true;
    nrfx_err_t result = nrfx_pdm_start();
    if (result != NRFX_SUCCESS) {
        _capture_enabled = false;
        LOG_ERR("PDM restart failed: %d", result);
    }
}
