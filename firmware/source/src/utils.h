#ifndef UTILS_H
#define UTILS_H

#include <errno.h>
#include <stdbool.h>
#include <zephyr/logging/log.h>
#include <zephyr/bluetooth/gatt.h>

#define ASSERT_OK(expression)                                            \
    do {                                                                 \
        int _anticipy_result = (expression);                             \
        if (_anticipy_result < 0) {                                      \
            LOG_ERR("Error at %s:%d: %d", __FILE__, __LINE__,           \
                    _anticipy_result);                                   \
            return _anticipy_result;                                     \
        }                                                                \
    } while (false)

#define ASSERT_TRUE(expression)                                          \
    do {                                                                 \
        bool _anticipy_result = (expression);                            \
        if (!_anticipy_result) {                                        \
            LOG_ERR("Assertion failed at %s:%d", __FILE__, __LINE__);   \
            return -EINVAL;                                              \
        }                                                                \
    } while (false)

#endif
