# SPDX-License-Identifier: Apache-2.0
cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(nrf52840_nordic)
enable_language(C ASM)

target_sources(app PRIVATE
    src/main.c
    src/transport.c
    src/transport_safety.c
    src/recovery_touch.c
    src/recovery_usb.c
    src/watchdog.c
    src/mic.c
    src/led.c
    src/codec.c
    src/lib/battery/battery.c
    src/battery_math.c
    src/battery_smoother.c
)

# The selected firmware contract is CELT-only restricted-low-delay Opus.
# Compiling dormant SILK/Hybrid files previously produced real array-bound
# diagnostics in code that this image must never select.
target_sources_ifdef(CONFIG_CODEC_OPUS app PRIVATE
    src/opus_packet_helpers.c
    src/lib/opus-1.2.1/analysis.c
    src/lib/opus-1.2.1/bands.c
    src/lib/opus-1.2.1/biquad_alt.c
    src/lib/opus-1.2.1/celt.c
    src/lib/opus-1.2.1/celt_decoder.c
    src/lib/opus-1.2.1/celt_encoder.c
    src/lib/opus-1.2.1/celt_lpc.c
    src/lib/opus-1.2.1/cwrs.c
    src/lib/opus-1.2.1/entcode.c
    src/lib/opus-1.2.1/entdec.c
    src/lib/opus-1.2.1/entenc.c
    src/lib/opus-1.2.1/kiss_fft.c
    src/lib/opus-1.2.1/laplace.c
    src/lib/opus-1.2.1/lin2log.c
    src/lib/opus-1.2.1/log2lin.c
    src/lib/opus-1.2.1/mathops.c
    src/lib/opus-1.2.1/mdct.c
    src/lib/opus-1.2.1/mlp.c
    src/lib/opus-1.2.1/mlp_data.c
    src/lib/opus-1.2.1/modes.c
    src/lib/opus-1.2.1/opus.c
    src/lib/opus-1.2.1/opus_encoder.c
    src/lib/opus-1.2.1/pitch.c
    src/lib/opus-1.2.1/quant_bands.c
    src/lib/opus-1.2.1/rate.c
    src/lib/opus-1.2.1/repacketizer.c
    src/lib/opus-1.2.1/vq.c
    src/lib/opus-1.2.1/arm/celt_pitch_xcorr_arm_gcc.s
)

target_compile_options(app PRIVATE
    -Werror=array-bounds=2
    -Werror=bool-compare
    -Werror=discarded-qualifiers
    -Werror=format
    -Werror=implicit-function-declaration
    -Werror=incompatible-pointer-types
    -Werror=logical-not-parentheses
    -Werror=overflow
    -Werror=return-type
    -Werror=stringop-overflow=2
    -Werror=stringop-overread
    -Werror=unused-function
    -Werror=unused-result
    -Werror=unused-variable
    -Werror=use-after-free=2
)

set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DARM_MATH_CM4")
# set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DVAR_ARRAYS")
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DOPUS_ARM_ASM")
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DOPUS_ARM_INLINE_ASM")
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DOPUS_ARM_INLINE_EDSP")
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DOPUS_ARM_INLINE_MEDIA")
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DOPUS_ARM_MAY_HAVE_EDSP")
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DOPUS_ARM_PRESUME_EDSP")
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DOPUS_BUILD")
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DUSE_ALLOCA")
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DFIXED_POINT -DDISABLE_FLOAT_API")
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DHAVE_CONFIG_H")
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DHAVE_ALLOCA_H")
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -fsingle-precision-constant") # A lot of constants are written as doubles
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DHAVE_LRINT -DHAVE_LRINTF")
