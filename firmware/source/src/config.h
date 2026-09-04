#include <haly/nrfy_gpio.h>

// #define SAMPLE_RATE 16000
#define MIC_GAIN 64
#define MIC_IRC_PRIORITY 5
#define MIC_BUFFER_SAMPLES 1600    // 100ms
#define AUDIO_BUFFER_SAMPLES 16000 // 1s
#define NETWORK_RING_BUF_SIZE 32   // number of frames * CODEC_OUTPUT_MAX_BYTES

// THE CAPTURE GEOMETRY, stated once so the asserts below have something to
// check against.
//
// One DMA block is MIC_BUFFER_SAMPLES; one Opus frame is
// CODEC_PACKAGE_SAMPLES. 1600 / 160 = 10 EXACTLY, and that integer ratio is
// the only reason a DMA block boundary and an Opus frame boundary re-align on
// every single block instead of drifting. Nothing in this firmware states
// that, and nothing checked it — so a future tuning pass that made the mic
// buffer 1500 samples would produce audio that still encodes, still transmits
// and is progressively wrong at the seams, with no build failure and no
// runtime error to point at. Omi carries the same ratio (100 ms blocks, 20 ms
// frames, exactly 5) and its own teardown calls it load-bearing and
// undocumented. The asserts live beside the buffers they protect, in codec.c
// and transport.c, because that is where the mistake would be made.
#define MINIMAL_PACKET_SIZE 100    // Less than that doesn't make sence to send anything at all

// PIN definitions
// https://github.com/Seeed-Studio/Adafruit_nRF52_Arduino/blob/5aa3573913449410fd60f76b75673c53855ff2ec/variants/Seeed_XIAO_nRF52840_Sense/variant.cpp#L34
#define PDM_DIN_PIN NRF_GPIO_PIN_MAP(0, 16)
#define PDM_CLK_PIN NRF_GPIO_PIN_MAP(1, 0)
#define PDM_PWR_PIN NRF_GPIO_PIN_MAP(1, 10)

// Codecs
#define CODEC_OPUS 1

#if CODEC_OPUS
#define CODEC_PACKAGE_SAMPLES (160)
// PARENTHESISED, and it was not. This expands into array bounds and into
// divisions, and `A * 2` unparenthesised is only correct where the surrounding
// operator happens to bind more loosely. `sizeof(x) / CODEC_OUTPUT_MAX_BYTES`
// reads as `sizeof(x) / 160 * 2` — four times the intended answer, silently,
// in a size calculation. Nothing in the tree divides by it today, which is
// exactly why this is worth closing now rather than after something does.
#define CODEC_OUTPUT_MAX_BYTES (CODEC_PACKAGE_SAMPLES * 2) // Let's assume that 16bit is enough
#define CODEC_OPUS_APPLICATION OPUS_APPLICATION_RESTRICTED_LOWDELAY
#define CODEC_OPUS_BITRATE 32000
#define CODEC_OPUS_VBR 1 // Or 1
#define CODEC_OPUS_COMPLEXITY 3
#endif
#define CONFIG_OPUS_MODE CONFIG_OPUS_MODE_CELT

// Codec IDs

#ifdef CODEC_OPUS
#define CODEC_ID 20
#endif

// Logs
// #define LOG_DISCARDED