// SPDX-License-Identifier: MIT
//
// HOST STUB, not firmware. src/config.h opens with <haly/nrfy_gpio.h> for one
// macro, so a host compiler cannot read the capture geometry without this. It
// supplies that macro and nothing else, so a test that includes config.h reads
// THE REAL CONSTANTS rather than a transcription of them — which is the whole
// point: a copy of 1600 in a test file proves the copy, not the firmware.
#ifndef ANTICIPY_HOST_STUB_NRFY_GPIO_H
#define ANTICIPY_HOST_STUB_NRFY_GPIO_H

#define NRF_GPIO_PIN_MAP(port, pin) (((port) << 5) | (pin))

#endif
