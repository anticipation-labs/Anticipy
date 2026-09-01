#ifndef TRANSPORT_H
#define TRANSPORT_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

struct bt_conn;

#ifdef CONFIG_OMI_ENABLE_ACCELEROMETER
#include <zephyr/drivers/sensor.h>
typedef struct sensors {

    struct sensor_value a_x;
    struct sensor_value a_y;
    struct sensor_value a_z;
    struct sensor_value g_x;
    struct sensor_value g_y;
    struct sensor_value g_z;
} sensors_t;
#endif
/**
 * @brief Initialize the BLE transport logic
 *
 * Initializes the BLE Logic
 *
 * @return 0 if successful, negative errno code if error
 */
int transport_start();
int broadcast_audio_packets(uint8_t *buffer, size_t size);
/** Return a referenced connection, or NULL.  Caller must bt_conn_unref(). */
struct bt_conn *get_current_connection();
/** True only for the encrypted, policy-approved current BLE peer. */
bool transport_peer_is_authorized(const struct bt_conn *conn);
#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
/** Logically clear the SD backlog and discard any not-yet-flushed RAM tail. */
int transport_clear_offline_audio(void);
#endif
int bt_on();
int bt_off();

void accel_off();
#endif
