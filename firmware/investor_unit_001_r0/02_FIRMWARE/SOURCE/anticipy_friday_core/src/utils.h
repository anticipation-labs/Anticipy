#ifndef UTILS_H
#define UTILS_H

#include <zephyr/bluetooth/gatt.h>
#include <zephyr/logging/log.h>

#define ASSERT_OK(result)                                                                                              \
    do {                                                                                                               \
        int _assert_result = (result);                                                                                 \
        if (_assert_result < 0) {                                                                                      \
            LOG_ERR("Error at %s:%d:%d", __FILE__, __LINE__, _assert_result);                                         \
            return _assert_result;                                                                                     \
        }                                                                                                              \
    } while (0)

#define ASSERT_TRUE(result)                                                                                            \
    do {                                                                                                               \
        if (!(result)) {                                                                                               \
            LOG_ERR("Assertion failed at %s:%d", __FILE__, __LINE__);                                                 \
            return -1;                                                                                                 \
        }                                                                                                              \
    } while (0)

#endif
