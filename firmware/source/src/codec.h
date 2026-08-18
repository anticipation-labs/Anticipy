#ifndef CODEC_H
#define CODEC_H

#include <stddef.h>
#include <stdint.h>

typedef void (*codec_callback)(uint8_t *data, size_t len);
typedef void (*codec_error_callback)(int error);

void set_codec_callback(codec_callback callback);
void set_codec_error_callback(codec_error_callback callback);
int codec_receive_pcm(int16_t *data, size_t len);
int codec_start(void);
void codec_reset(void);

#endif
