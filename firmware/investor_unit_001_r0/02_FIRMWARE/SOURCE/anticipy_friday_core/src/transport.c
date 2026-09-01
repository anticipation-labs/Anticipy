#include "transport.h"

#include <errno.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/bluetooth/l2cap.h>
#include <zephyr/bluetooth/services/bas.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/settings/settings.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/ring_buffer.h>

#include "config.h"
#include "utils.h"
// #include "nfc.h"
#include "button.h"
#include "haptic.h"
#include "lib/battery/battery.h"
#include "mic.h"
#include "wdog_facade.h"
#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
#include "sdcard.h"
#include "storage.h"
#endif
// #include "friend.h"
LOG_MODULE_REGISTER(transport, CONFIG_LOG_DEFAULT_LEVEL);

#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
#define MAX_STORAGE_BYTES 0xFFFF0000
#endif
extern bool is_connected;
#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
extern bool storage_is_on;
extern uint8_t file_count;
extern uint32_t file_num_array[2];
#endif
static struct bt_conn *current_connection = NULL;
static struct k_spinlock connection_lock;
static atomic_t advertising_desired;
#ifdef CONFIG_BT_FILTER_ACCEPT_LIST
static bt_addr_le_t owner_addr;
static atomic_t owner_present;
static atomic_t owner_connection_authorized;
static atomic_t provisioning_open;
#endif
uint16_t current_mtu = 0;
uint16_t current_package_index = 0;

bool transport_peer_is_authorized(const struct bt_conn *conn)
{
    if (conn == NULL || bt_conn_get_security(conn) < BT_SECURITY_L2) {
        return false;
    }

#ifdef CONFIG_BT_FILTER_ACCEPT_LIST
    if (!atomic_get(&owner_connection_authorized)) {
        return false;
    }

    bool is_current;
    k_spinlock_key_t key = k_spin_lock(&connection_lock);
    is_current = current_connection == conn;
    k_spin_unlock(&connection_lock, key);
    return is_current;
#else
    return true;
#endif
}

//
// Internal
//

#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
static struct k_mutex write_sdcard_mutex;
#endif

#ifdef CONFIG_OMI_ENABLE_SPEAKER
static ssize_t audio_data_write_handler(struct bt_conn *conn,
                                        const struct bt_gatt_attr *attr,
                                        const void *buf,
                                        uint16_t len,
                                        uint16_t offset,
                                        uint8_t flags);
#endif

static struct bt_conn_cb _callback_references;
static void audio_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value);
static ssize_t audio_data_read_characteristic(struct bt_conn *conn,
                                              const struct bt_gatt_attr *attr,
                                              void *buf,
                                              uint16_t len,
                                              uint16_t offset);
static ssize_t audio_codec_read_characteristic(struct bt_conn *conn,
                                               const struct bt_gatt_attr *attr,
                                               void *buf,
                                               uint16_t len,
                                               uint16_t offset);

static void dfu_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value);
static ssize_t dfu_control_point_write_handler(struct bt_conn *conn,
                                               const struct bt_gatt_attr *attr,
                                               const void *buf,
                                               uint16_t len,
                                               uint16_t offset,
                                               uint8_t flags);

//
// Service and Characteristic
//
// Audio service with UUID 19B10000-E8F2-537E-4F6C-D104768A1214
// exposes following characteristics:
// - Audio data (UUID 19B10001-E8F2-537E-4F6C-D104768A1214) to send audio data (read/notify)
// - Audio codec (UUID 19B10002-E8F2-537E-4F6C-D104768A1214) to send audio codec type (read)
// TODO: The current audio service UUID seems to come from old Intel sample code,
// we should change it to UUID 814b9b7c-25fd-4acd-8604-d28877beee6d
static struct bt_uuid_128 audio_service_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10000, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));
static struct bt_uuid_128 audio_characteristic_data_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10001, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));
static struct bt_uuid_128 audio_characteristic_format_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10002, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));
#ifdef CONFIG_OMI_ENABLE_SPEAKER
static struct bt_uuid_128 audio_characteristic_speaker_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10003, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));
#endif

static struct bt_gatt_attr audio_service_attr[] = {
    BT_GATT_PRIMARY_SERVICE(&audio_service_uuid),
    BT_GATT_CHARACTERISTIC(&audio_characteristic_data_uuid.uuid,
                           BT_GATT_CHRC_READ | BT_GATT_CHRC_NOTIFY,
                           BT_GATT_PERM_READ_ENCRYPT,
                           audio_data_read_characteristic,
                           NULL,
                           NULL),
    BT_GATT_CCC(audio_ccc_config_changed_handler,
                BT_GATT_PERM_READ_ENCRYPT | BT_GATT_PERM_WRITE_ENCRYPT),
    BT_GATT_CHARACTERISTIC(&audio_characteristic_format_uuid.uuid,
                           BT_GATT_CHRC_READ,
                           BT_GATT_PERM_READ_ENCRYPT,
                           audio_codec_read_characteristic,
                           NULL,
                           NULL),
#ifdef CONFIG_OMI_ENABLE_SPEAKER
    BT_GATT_CHARACTERISTIC(&audio_characteristic_speaker_uuid.uuid,
                           BT_GATT_CHRC_WRITE | BT_GATT_CHRC_NOTIFY,
                           BT_GATT_PERM_WRITE_ENCRYPT,
                           NULL,
                           audio_data_write_handler,
                           NULL),
    BT_GATT_CCC(audio_ccc_config_changed_handler,
                BT_GATT_PERM_READ_ENCRYPT | BT_GATT_PERM_WRITE_ENCRYPT),
#endif

};

static struct bt_gatt_service audio_service = BT_GATT_SERVICE(audio_service_attr);

// Nordic Legacy DFU service with UUID 00001530-1212-EFDE-1523-785FEABCD123
// exposes following characteristics:
// - Control point (UUID 00001531-1212-EFDE-1523-785FEABCD123) to start the OTA update process (write/notify)
static struct bt_uuid_128 dfu_service_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x00001530, 0x1212, 0xEFDE, 0x1523, 0x785FEABCD123));
static struct bt_uuid_128 dfu_control_point_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x00001531, 0x1212, 0xEFDE, 0x1523, 0x785FEABCD123));

static struct bt_gatt_attr dfu_service_attr[] = {
    BT_GATT_PRIMARY_SERVICE(&dfu_service_uuid),
    BT_GATT_CHARACTERISTIC(&dfu_control_point_uuid.uuid,
                           BT_GATT_CHRC_WRITE | BT_GATT_CHRC_NOTIFY,
                           BT_GATT_PERM_WRITE_ENCRYPT,
                           NULL,
                           dfu_control_point_write_handler,
                           NULL),
    BT_GATT_CCC(dfu_ccc_config_changed_handler,
                BT_GATT_PERM_READ_ENCRYPT | BT_GATT_PERM_WRITE_ENCRYPT),
};

static struct bt_gatt_service dfu_service = BT_GATT_SERVICE(dfu_service_attr);
#ifdef CONFIG_OMI_ENABLE_ACCELEROMETER
// Acceleration data
// this code activates the onboard accelerometer. some cute ideas may include shaking the necklace to color strobe
//
static struct sensors mega_sensor;
static struct device *lsm6dsl_dev;
// Arbritrary uuid, feel free to change
static struct bt_uuid_128 accel_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x32403790, 0x0000, 0x1000, 0x7450, 0xBF445E5829A2));
static struct bt_uuid_128 accel_uuid_x =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x32403791, 0x0000, 0x1000, 0x7450, 0xBF445E5829A2));

static void accel_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value);
static ssize_t accel_data_read_characteristic(struct bt_conn *conn,
                                              const struct bt_gatt_attr *attr,
                                              void *buf,
                                              uint16_t len,
                                              uint16_t offset);

static struct bt_gatt_attr accel_service_attr[] = {
    BT_GATT_PRIMARY_SERVICE(&accel_uuid), // primary description
    BT_GATT_CHARACTERISTIC(&accel_uuid_x.uuid,
                           BT_GATT_CHRC_READ | BT_GATT_CHRC_NOTIFY,
                           BT_GATT_PERM_READ_ENCRYPT,
                           accel_data_read_characteristic,
                           NULL,
                           NULL),                                                          // data type
    BT_GATT_CCC(accel_ccc_config_changed_handler,
                BT_GATT_PERM_READ_ENCRYPT | BT_GATT_PERM_WRITE_ENCRYPT),
};
static struct bt_gatt_service accel_service = BT_GATT_SERVICE(accel_service_attr);

static ssize_t accel_data_read_characteristic(struct bt_conn *conn,
                                              const struct bt_gatt_attr *attr,
                                              void *buf,
                                              uint16_t len,
                                              uint16_t offset)
{
    LOG_INF("Acceleration data read characteristic");
    int axis_mode = 6; // 3 for accel, 6 for (also) gyro
    return bt_gatt_attr_read(conn, attr, buf, len, offset, &axis_mode, sizeof(axis_mode));
}

#define ACCEL_REFRESH_INTERVAL 1000 // 1.0 seconds

void broadcast_accel(struct k_work *work_item);
K_WORK_DELAYABLE_DEFINE(accel_work, broadcast_accel);

void broadcast_accel(struct k_work *work_item)
{

    sensor_sample_fetch_chan(lsm6dsl_dev, SENSOR_CHAN_ACCEL_XYZ);
    sensor_channel_get(lsm6dsl_dev, SENSOR_CHAN_ACCEL_X, &mega_sensor.a_x);
    sensor_channel_get(lsm6dsl_dev, SENSOR_CHAN_ACCEL_Y, &mega_sensor.a_y);
    sensor_channel_get(lsm6dsl_dev, SENSOR_CHAN_ACCEL_Z, &mega_sensor.a_z);

    sensor_sample_fetch_chan(lsm6dsl_dev, SENSOR_CHAN_GYRO_XYZ);
    sensor_channel_get(lsm6dsl_dev, SENSOR_CHAN_GYRO_X, &mega_sensor.g_x);
    sensor_channel_get(lsm6dsl_dev, SENSOR_CHAN_GYRO_Y, &mega_sensor.g_y);
    sensor_channel_get(lsm6dsl_dev, SENSOR_CHAN_GYRO_Z, &mega_sensor.g_z);

    // only time mega sensor is changed is through here (hopefully),  so no chance of race condition
    int err = bt_gatt_notify(current_connection, &accel_service.attrs[1], &mega_sensor, sizeof(mega_sensor));
    if (err) {
        LOG_ERR("Error updating Accelerometer data");
    }
    k_work_reschedule(&accel_work, K_MSEC(ACCEL_REFRESH_INTERVAL));
}

struct gpio_dt_spec accel_gpio_pin = {.port = DEVICE_DT_GET(DT_NODELABEL(gpio1)),
                                      .pin = 8,
                                      .dt_flags = GPIO_INT_DISABLE};

// use d4,d5
static void accel_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value)
{
    if (value == BT_GATT_CCC_NOTIFY) {
        LOG_INF("Client subscribed for notifications");
    } else if (value == 0) {
        LOG_INF("Client unsubscribed from notifications");
    } else {
        LOG_ERR("Invalid CCC value: %u", value);
    }
}

int accel_start()
{
    struct sensor_value odr_attr;
    lsm6dsl_dev = DEVICE_DT_GET_ONE(st_lsm6dsl);
    k_msleep(50);
    if (lsm6dsl_dev == NULL) {
        LOG_ERR("Could not get LSM6DSL device");
        return 0;
    }
    if (!device_is_ready(lsm6dsl_dev)) {
        LOG_ERR("LSM6DSL: not ready");
        return 0;
    }
    odr_attr.val1 = 10;
    odr_attr.val2 = 0;

    if (gpio_is_ready_dt(&accel_gpio_pin)) {
        LOG_PRINTK("Speaker Pin ready\n");
    } else {
        LOG_PRINTK("Error setting up speaker Pin\n");
        return -1;
    }
    if (gpio_pin_configure_dt(&accel_gpio_pin, GPIO_OUTPUT_INACTIVE) < 0) {
        LOG_PRINTK("Error setting up Haptic Pin\n");
        return -1;
    }
    gpio_pin_set_dt(&accel_gpio_pin, 1);
    if (sensor_attr_set(lsm6dsl_dev, SENSOR_CHAN_ACCEL_XYZ, SENSOR_ATTR_SAMPLING_FREQUENCY, &odr_attr) < 0) {
        LOG_ERR("Cannot set sampling frequency for Accelerometer.");
        return 0;
    }
    if (sensor_attr_set(lsm6dsl_dev, SENSOR_CHAN_GYRO_XYZ, SENSOR_ATTR_SAMPLING_FREQUENCY, &odr_attr) < 0) {
        LOG_ERR("Cannot set sampling frequency for gyro.");
        return 0;
    }
    if (sensor_sample_fetch(lsm6dsl_dev) < 0) {
        LOG_ERR("Sensor sample update error");
        return 0;
    }

    LOG_INF("Accelerometer is ready for use \n");

    return 1;
}
#endif
// Advertisement data
static const struct bt_data bt_ad[] = {
    BT_DATA_BYTES(BT_DATA_FLAGS, (BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR)),
    BT_DATA(BT_DATA_UUID128_ALL, audio_service_uuid.val, sizeof(audio_service_uuid.val)),
    BT_DATA(BT_DATA_NAME_COMPLETE, CONFIG_BT_DEVICE_NAME, sizeof(CONFIG_BT_DEVICE_NAME) - 1),
};

// Scan response data
static const struct bt_data bt_sd[] = {
    BT_DATA_BYTES(BT_DATA_UUID16_ALL, BT_UUID_16_ENCODE(BT_UUID_DIS_VAL)),
    BT_DATA(BT_DATA_UUID128_ALL, dfu_service_uuid.val, sizeof(dfu_service_uuid.val)),
};

static int start_transport_advertising(void);

#ifdef CONFIG_BT_FILTER_ACCEPT_LIST
#define OWNER_PROVISIONING_TIMEOUT_SECONDS 120

struct owner_bond_scan {
    size_t count;
    bt_addr_le_t first;
};

static void owner_provisioning_timeout_handler(struct k_work *work_item);
K_WORK_DELAYABLE_DEFINE(owner_provisioning_timeout_work, owner_provisioning_timeout_handler);
static void owner_commit_handler(struct k_work *work_item);
K_WORK_DEFINE(owner_commit_work, owner_commit_handler);
static void unauthorized_bond_cleanup_handler(struct k_work *work_item);
K_WORK_DEFINE(unauthorized_bond_cleanup_work, unauthorized_bond_cleanup_handler);

static bool owner_connection_matches(const struct bt_conn *conn)
{
    return atomic_get(&owner_present) &&
           bt_addr_le_cmp(bt_conn_get_dst(conn), &owner_addr) == 0;
}

static void owner_bond_scan_callback(const struct bt_bond_info *info, void *user_data)
{
    struct owner_bond_scan *scan = user_data;

    if (scan->count == 0U) {
        bt_addr_le_copy(&scan->first, &info->addr);
    }
    scan->count++;
}

/* Refresh the software owner and the controller filter from persisted bonds.
 * Call only while filter-based advertising is stopped. */
static int refresh_owner_filter(void)
{
    struct owner_bond_scan scan = {0};

    atomic_clear(&owner_present);
    atomic_clear(&owner_connection_authorized);

    bt_foreach_bond(BT_ID_DEFAULT, owner_bond_scan_callback, &scan);
    if (scan.count > 1U) {
        LOG_ERR("More than one BLE bond exists; owner policy is locked");
        return -E2BIG;
    }

    int err = bt_le_filter_accept_list_clear();
    if (err) {
        LOG_ERR("Failed to clear BLE owner filter (err %d)", err);
        return err;
    }

    if (scan.count == 0U) {
        return 0;
    }

    err = bt_le_filter_accept_list_add(&scan.first);
    if (err) {
        LOG_ERR("Failed to install BLE owner filter (err %d)", err);
        return err;
    }

    bt_addr_le_copy(&owner_addr, &scan.first);
    atomic_set(&owner_present, 1);
    LOG_INF("Persisted BLE owner loaded; connection filter enabled");
    return 0;
}

static void reject_owner_connection(struct bt_conn *conn, const char *reason)
{
    atomic_clear(&owner_connection_authorized);
    is_connected = false;
    LOG_WRN("Rejecting BLE peer: %s", reason);
    int err = bt_conn_disconnect(conn, BT_HCI_ERR_AUTH_FAIL);
    if (err && err != -ENOTCONN) {
        LOG_WRN("Failed to disconnect rejected peer (err %d)", err);
    }
}

static void authorize_owner_connection(struct bt_conn *conn)
{
    atomic_set(&owner_connection_authorized, 1);
    is_connected = true;
    LOG_INF("Authenticated owner connection authorized");
}

static void owner_identity_resolved(struct bt_conn *conn,
                                    const bt_addr_le_t *rpa,
                                    const bt_addr_le_t *identity)
{
    ARG_UNUSED(rpa);

    if (!atomic_get(&owner_present)) {
        return;
    }

    if (bt_addr_le_cmp(identity, &owner_addr) != 0) {
        reject_owner_connection(conn, "resolved identity is not the owner");
    } else if (bt_conn_get_security(conn) >= BT_SECURITY_L2) {
        authorize_owner_connection(conn);
    }
}

static void owner_security_changed(struct bt_conn *conn,
                                   bt_security_t level,
                                   enum bt_security_err err)
{
    if (err != BT_SECURITY_ERR_SUCCESS || level < BT_SECURITY_L2) {
        reject_owner_connection(conn, "encrypted owner authentication failed");
        return;
    }

    if (!atomic_get(&owner_present)) {
        /* A physically opened provisioning session is authorized only after
         * pairing_complete confirms that a persistent bond was created. */
        if (!atomic_get(&provisioning_open)) {
            reject_owner_connection(conn, "device is not in provisioning mode");
        }
        return;
    }

    if (owner_connection_matches(conn)) {
        authorize_owner_connection(conn);
        return;
    }

    /* Resolution can complete after encryption on some controller paths.  An
     * RPA remains denied until owner_identity_resolved confirms it. */
    const bt_addr_le_t *peer = bt_conn_get_dst(conn);
    if (bt_addr_le_is_rpa(peer) || peer->type == BT_ADDR_LE_UNRESOLVED) {
        LOG_INF("Waiting for owner private-address resolution");
        return;
    }

    reject_owner_connection(conn, "bonded identity is not the owner");
}

static void owner_pairing_complete(struct bt_conn *conn, bool bonded)
{
    if (!bonded) {
        reject_owner_connection(conn, "pairing did not create a bond");
        return;
    }

    if (atomic_get(&owner_present)) {
        if (owner_connection_matches(conn)) {
            authorize_owner_connection(conn);
        } else {
            reject_owner_connection(conn, "second owner is forbidden");
        }
        return;
    }

    if (!atomic_get(&provisioning_open)) {
        reject_owner_connection(conn, "provisioning window is closed");
        k_work_submit(&unauthorized_bond_cleanup_work);
        return;
    }

    /* Key persistence is complete, but filter-list HCI commands must not run
     * synchronously in the Bluetooth pairing callback.  Pause re-advertising
     * until the system workqueue durably installs the sole new owner. */
    atomic_clear(&provisioning_open);
    atomic_clear(&advertising_desired);
    (void) k_work_cancel_delayable(&owner_provisioning_timeout_work);
    k_work_submit(&owner_commit_work);
}

static void owner_pairing_failed(struct bt_conn *conn, enum bt_security_err reason)
{
    ARG_UNUSED(reason);
    reject_owner_connection(conn, "pairing failed");
}

static void owner_bond_deleted(uint8_t id, const bt_addr_le_t *peer)
{
    if (id == BT_ID_DEFAULT && atomic_get(&owner_present) &&
        bt_addr_le_cmp(peer, &owner_addr) == 0) {
        atomic_clear(&owner_present);
        atomic_clear(&owner_connection_authorized);
        atomic_clear(&advertising_desired);
        atomic_clear(&provisioning_open);
        is_connected = false;
        LOG_WRN("BLE owner bond deleted; physical provisioning is required");
    }
}

static struct bt_conn_auth_info_cb owner_auth_callbacks = {
    .pairing_complete = owner_pairing_complete,
    .pairing_failed = owner_pairing_failed,
    .bond_deleted = owner_bond_deleted,
};

static void owner_provisioning_timeout_handler(struct k_work *work_item)
{
    ARG_UNUSED(work_item);

    if (atomic_get(&owner_present) || !atomic_cas(&provisioning_open, 1, 0)) {
        return;
    }

    atomic_clear(&advertising_desired);
    int err = bt_le_adv_stop();
    if (err && err != -EALREADY) {
        LOG_WRN("Failed to stop expired provisioning advertising (err %d)", err);
    }

    struct bt_conn *conn = get_current_connection();
    if (conn != NULL) {
        if (!transport_peer_is_authorized(conn)) {
            reject_owner_connection(conn, "provisioning window expired");
        }
        bt_conn_unref(conn);
    }
    LOG_WRN("BLE provisioning window expired");
}

static void owner_commit_handler(struct k_work *work_item)
{
    ARG_UNUSED(work_item);

    int err = refresh_owner_filter();
    struct bt_conn *conn = get_current_connection();
    if (err || !atomic_get(&owner_present)) {
        atomic_clear(&advertising_desired);
        if (conn != NULL) {
            reject_owner_connection(conn, "owner filter could not be committed");
            bt_conn_unref(conn);
        }
        return;
    }

    atomic_set(&advertising_desired, 1);
    if (conn != NULL) {
        /* This work is submitted only after the sole first bond completes. */
        if (bt_conn_get_security(conn) >= BT_SECURITY_L2) {
            authorize_owner_connection(conn);
        } else {
            reject_owner_connection(conn, "first-owner link lost encryption");
        }
        bt_conn_unref(conn);
        return;
    }

    err = start_transport_advertising();
    if (err && err != -EALREADY) {
        atomic_clear(&advertising_desired);
        LOG_ERR("Failed to start owner-filtered advertising (err %d)", err);
    }
}

static void unauthorized_bond_cleanup_handler(struct k_work *work_item)
{
    ARG_UNUSED(work_item);

    int err = bt_unpair(BT_ID_DEFAULT, BT_ADDR_LE_ANY);
    if (err) {
        LOG_ERR("Failed to erase unauthorized BLE bond (err %d)", err);
    }
    err = bt_le_filter_accept_list_clear();
    if (err) {
        LOG_ERR("Failed to clear owner filter after rejected pairing (err %d)", err);
    }
    atomic_clear(&owner_present);
    atomic_clear(&owner_connection_authorized);
    atomic_clear(&advertising_desired);
    atomic_clear(&provisioning_open);
    is_connected = false;
}

static int prepare_owner_policy(void)
{
    bool factory_reset_requested = false;
    bool provisioning_requested = false;

#ifdef CONFIG_OMI_ENABLE_BUTTON
    factory_reset_requested = button_take_factory_reset_request();
    provisioning_requested = button_take_provisioning_request();
#endif

    if (factory_reset_requested) {
        int reset_err = bt_unpair(BT_ID_DEFAULT, BT_ADDR_LE_ANY);
        if (reset_err) {
            LOG_ERR("Factory reset could not erase BLE bonds (err %d)", reset_err);
            return reset_err;
        }
#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
        reset_err = transport_clear_offline_audio();
        if (reset_err) {
            LOG_ERR("Factory reset could not durably discard the prior owner's backlog (err %d)",
                    reset_err);
            return reset_err;
        }
#endif
        LOG_WRN("Factory reset erased the BLE owner bond");
    }

    int err = refresh_owner_filter();
    if (err) {
        return err;
    }

    if (atomic_get(&owner_present)) {
        atomic_clear(&provisioning_open);
        return 0;
    }

    /* A genuinely unowned unit must be commissionable even when the optional
     * D7 switch was not fitted.  Open one time-limited window automatically
     * on a virgin settings partition; the first persistent bond then becomes
     * the sole owner.  Once an owner exists, every later boot is filtered.
     * D7 remains the deliberate physical path for reprovisioning/reset. */
    atomic_set(&provisioning_open, 1);
    if (provisioning_requested) {
        LOG_WRN("Physical BLE provisioning window opened for %d seconds",
                OWNER_PROVISIONING_TIMEOUT_SECONDS);
    } else {
        LOG_WRN("Virgin BLE provisioning window opened for %d seconds",
                OWNER_PROVISIONING_TIMEOUT_SECONDS);
    }

    return 0;
}
#endif /* CONFIG_BT_FILTER_ACCEPT_LIST */

static int start_transport_advertising(void)
{
    const struct bt_le_adv_param *params = BT_LE_ADV_CONN;

#ifdef CONFIG_BT_FILTER_ACCEPT_LIST
    static const struct bt_le_adv_param owner_only_params =
        BT_LE_ADV_PARAM_INIT(BT_LE_ADV_OPT_CONNECTABLE | BT_LE_ADV_OPT_FILTER_CONN,
                             BT_GAP_ADV_FAST_INT_MIN_2,
                             BT_GAP_ADV_FAST_INT_MAX_2,
                             NULL);

    if (atomic_get(&owner_present)) {
        params = &owner_only_params;
    } else if (!atomic_get(&provisioning_open)) {
        return -EACCES;
    }
#endif

    return bt_le_adv_start(params, bt_ad, ARRAY_SIZE(bt_ad), bt_sd, ARRAY_SIZE(bt_sd));
}

//
// State and Characteristics
//

static void audio_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value)
{
    if (value == BT_GATT_CCC_NOTIFY) {
        LOG_INF("Client subscribed for notifications");
    } else if (value == 0) {
        LOG_INF("Client unsubscribed from notifications");
    } else {
        LOG_INF("Invalid CCC value: %u", value);
    }
}

static ssize_t audio_data_read_characteristic(struct bt_conn *conn,
                                              const struct bt_gatt_attr *attr,
                                              void *buf,
                                              uint16_t len,
                                              uint16_t offset)
{
    if (!transport_peer_is_authorized(conn)) {
        return BT_GATT_ERR(BT_ATT_ERR_AUTHORIZATION);
    }

    LOG_DBG("audio_data_read_characteristic");
    return bt_gatt_attr_read(conn, attr, buf, len, offset, NULL, 0);
}

static ssize_t audio_codec_read_characteristic(struct bt_conn *conn,
                                               const struct bt_gatt_attr *attr,
                                               void *buf,
                                               uint16_t len,
                                               uint16_t offset)
{
    if (!transport_peer_is_authorized(conn)) {
        return BT_GATT_ERR(BT_ATT_ERR_AUTHORIZATION);
    }

    uint8_t value[1] = {CODEC_ID};
    LOG_DBG("audio_codec_read_characteristic %d", CODEC_ID);
    return bt_gatt_attr_read(conn, attr, buf, len, offset, value, sizeof(value));
}

#ifdef CONFIG_OMI_ENABLE_SPEAKER
static ssize_t audio_data_write_handler(struct bt_conn *conn,
                                        const struct bt_gatt_attr *attr,
                                        const void *buf,
                                        uint16_t len,
                                        uint16_t offset,
                                        uint8_t flags)
{
    if (!transport_peer_is_authorized(conn)) {
        return BT_GATT_ERR(BT_ATT_ERR_AUTHORIZATION);
    }

    uint16_t amount = 400;
    int16_t *int16_buf = (int16_t *) buf;
    uint8_t *data = (uint8_t *) buf;
    bt_gatt_notify(conn, attr, &amount, sizeof(amount));
    amount = speak(len, buf);
    return len;
}
#endif

//
// DFU Service Handlers
//

static void dfu_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value)
{
    if (value == BT_GATT_CCC_NOTIFY) {
        LOG_INF("Client subscribed for notifications");
    } else if (value == 0) {
        LOG_INF("Client unsubscribed from notifications");
    } else {
        LOG_INF("Invalid CCC value: %u", value);
    }
}

static ssize_t dfu_control_point_write_handler(struct bt_conn *conn,
                                               const struct bt_gatt_attr *attr,
                                               const void *buf,
                                               uint16_t len,
                                               uint16_t offset,
                                               uint8_t flags)
{
    if (!transport_peer_is_authorized(conn)) {
        return BT_GATT_ERR(BT_ATT_ERR_AUTHORIZATION);
    }

    LOG_INF("dfu_control_point_write_handler");
    if (len == 1 && ((uint8_t *) buf)[0] == 0x06) {
        watchdog_feed();
        NRF_POWER->GPREGRET = 0xA8;
        NVIC_SystemReset();
    } else if (len == 2 && ((uint8_t *) buf)[0] == 0x01) {
        uint8_t notification_value = 0x10;
        bt_gatt_notify(conn, attr, &notification_value, sizeof(notification_value));

        watchdog_feed();
        NRF_POWER->GPREGRET = 0xA8;
        NVIC_SystemReset();
    }
    return len;
}

//
// Battery Service Handlers
//

#define BATTERY_REFRESH_INTERVAL 15000 // 15 seconds

void broadcast_battery_level(struct k_work *work_item);

K_WORK_DELAYABLE_DEFINE(battery_work, broadcast_battery_level);

void broadcast_battery_level(struct k_work *work_item)
{
    uint16_t battery_millivolt;
    uint8_t battery_percentage;
    if (battery_get_millivolt(&battery_millivolt) == 0 &&
        battery_get_percentage(&battery_percentage, battery_millivolt) == 0) {

        LOG_PRINTK("Battery at %d mV (capacity %d%%)\n", battery_millivolt, battery_percentage);

        // Use the Zephyr BAS function to set (and notify) the battery level
        int err = bt_bas_set_battery_level(battery_percentage);
        if (err) {
            LOG_ERR("Error updating battery level: %d", err);
        }
    } else {
        LOG_ERR("Failed to read battery level");
    }

    k_work_reschedule(&battery_work, K_MSEC(BATTERY_REFRESH_INTERVAL));
}

//
// Connection Callbacks
//

static void _transport_connected(struct bt_conn *conn, uint8_t err)
{
    struct bt_conn_info info = {0};
#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
    /* A BLE link alone does not mean that backlog transfer is active. */
    storage_is_on = false;
#endif

    if (err != 0U) {
        LOG_ERR("Bluetooth connection failed (err %u)", err);
        return;
    }

    LOG_INF("bluetooth activated");

#ifdef CONFIG_BT_FILTER_ACCEPT_LIST
    atomic_clear(&owner_connection_authorized);
    is_connected = false;
#endif

    struct bt_conn *old_connection;
    k_spinlock_key_t key = k_spin_lock(&connection_lock);
    old_connection = current_connection;
    current_connection = bt_conn_ref(conn);
    k_spin_unlock(&connection_lock, key);
    if (old_connection != NULL) {
        bt_conn_unref(old_connection);
    }

    /* Connection-info lookup is diagnostic only.  A transient lookup failure
     * must not leave a real connection untracked and unprotected. */
    int info_err = bt_conn_get_info(conn, &info);
    if (info_err) {
        LOG_WRN("Failed to get connection diagnostics (err %d)", info_err);
    }

    int security_err = bt_conn_set_security(conn, BT_SECURITY_L2);
    if (security_err != 0 && security_err != -EALREADY) {
        LOG_ERR("Failed to start encrypted pairing (err %d)", security_err);
    }
    /* ATT MTU, not the Link Layer data length, limits a GATT notification. */
    current_mtu = bt_gatt_get_mtu(conn);
    LOG_INF("Transport connected");
    if (info_err == 0) {
        LOG_DBG("Interval: %d, latency: %d, timeout: %d", info.le.interval, info.le.latency, info.le.timeout);
        LOG_DBG("TX PHY %u, RX PHY %u", info.le.phy->tx_phy, info.le.phy->rx_phy);
        LOG_DBG("LE data len updated: TX (len: %d time: %d) RX (len: %d time: %d)",
                info.le.data_len->tx_max_len,
                info.le.data_len->tx_max_time,
                info.le.data_len->rx_max_len,
                info.le.data_len->rx_max_time);
    }

    k_work_reschedule(&battery_work, K_MSEC(100));

#ifndef CONFIG_BT_FILTER_ACCEPT_LIST
    is_connected = true;
#endif
}

static void _transport_disconnected(struct bt_conn *conn, uint8_t err)
{
    is_connected = false;
#ifdef CONFIG_BT_FILTER_ACCEPT_LIST
    atomic_clear(&owner_connection_authorized);
#endif
#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
    storage_is_on = false;
#endif
    (void) k_work_cancel_delayable(&battery_work);

    LOG_INF("Transport disconnected");

    struct bt_conn *disconnected_connection = NULL;
    k_spinlock_key_t key = k_spin_lock(&connection_lock);
    if (current_connection == conn) {
        disconnected_connection = current_connection;
        current_connection = NULL;
    }
    k_spin_unlock(&connection_lock, key);
    if (disconnected_connection != NULL) {
        bt_conn_unref(disconnected_connection);
    }
    current_mtu = 0;

    /* Legacy connectable advertising stops when a connection is accepted.
     * Restart it after every disconnect unless bt_off() deliberately disabled
     * the transport. */
    if (atomic_get(&advertising_desired)) {
        int adv_err = start_transport_advertising();
        if (adv_err && adv_err != -EALREADY) {
            LOG_ERR("Failed to restart advertising (err %d)", adv_err);
        }
    }
}

static bool _le_param_req(struct bt_conn *conn, struct bt_le_conn_param *param)
{
    LOG_INF("Transport connection parameters update request received.");
    LOG_DBG("Minimum interval: %d, Maximum interval: %d", param->interval_min, param->interval_max);
    LOG_DBG("Latency: %d, Timeout: %d", param->latency, param->timeout);

    return true;
}

static void _le_param_updated(struct bt_conn *conn, uint16_t interval, uint16_t latency, uint16_t timeout)
{
    LOG_INF("Connection parameters updated.");
    LOG_DBG("[ interval: %d, latency: %d, timeout: %d ]", interval, latency, timeout);
}

static void _le_phy_updated(struct bt_conn *conn, struct bt_conn_le_phy_info *param)
{
    // LOG_DBG("LE PHY updated: TX PHY %s, RX PHY %s",
    //        phy2str(param->tx_phy), phy2str(param->rx_phy));
}

static void _le_data_length_updated(struct bt_conn *conn, struct bt_conn_le_data_len_info *info)
{
    LOG_DBG("LE data len updated: TX (len: %d time: %d)"
            " RX (len: %d time: %d)",
            info->tx_max_len,
            info->tx_max_time,
            info->rx_max_len,
            info->rx_max_time);
    /* Do not copy tx_max_len into current_mtu.  The two values are different
     * protocol-layer limits.  The pusher queries bt_gatt_get_mtu() directly so
     * it also observes a later MTU exchange initiated by iOS. */
}

static struct bt_conn_cb _callback_references = {
    .connected = _transport_connected,
    .disconnected = _transport_disconnected,
    .le_param_req = _le_param_req,
    .le_param_updated = _le_param_updated,
    .le_phy_updated = _le_phy_updated,
    .le_data_len_updated = _le_data_length_updated,
#ifdef CONFIG_BT_FILTER_ACCEPT_LIST
    .identity_resolved = owner_identity_resolved,
    .security_changed = owner_security_changed,
#endif
};

//
// Ring Buffer
//

#define NET_BUFFER_HEADER_SIZE 3
#define RING_BUFFER_HEADER_SIZE 2
static uint8_t tx_queue[NETWORK_RING_BUF_SIZE * (CODEC_OUTPUT_MAX_BYTES + RING_BUFFER_HEADER_SIZE)];
static uint8_t tx_buffer[CODEC_OUTPUT_MAX_BYTES + RING_BUFFER_HEADER_SIZE];
static uint8_t tx_buffer_2[CODEC_OUTPUT_MAX_BYTES + RING_BUFFER_HEADER_SIZE];
static uint32_t tx_buffer_size = 0;
static struct ring_buf ring_buf;
K_SEM_DEFINE(tx_data_ready, 0, NETWORK_RING_BUF_SIZE);
static atomic_t pusher_busy;

static bool write_to_tx_queue(uint8_t *data, size_t size)
{
    /* A zero length is also the on-flash padding terminator.  Never allow an
     * encoder glitch to turn it into a valid live or stored audio frame. */
    if (data == NULL || size == 0U || size > CODEC_OUTPUT_MAX_BYTES) {
        return false;
    }

    // Copy data (TODO: Avoid this copy)
    tx_buffer_2[0] = size & 0xFF;
    tx_buffer_2[1] = (size >> 8) & 0xFF;
    memcpy(tx_buffer_2 + RING_BUFFER_HEADER_SIZE, data, size);

    // Write to ring buffer
    int written =
        ring_buf_put(&ring_buf,
                     tx_buffer_2,
                     (CODEC_OUTPUT_MAX_BYTES + RING_BUFFER_HEADER_SIZE)); // It always fits completely or not at all
    if (written != CODEC_OUTPUT_MAX_BYTES + RING_BUFFER_HEADER_SIZE) {
        return false;
    } else {
        return true;
    }
}

static bool read_from_tx_queue()
{

    // Read from ring buffer
    // memset(tx_buffer, 0, sizeof(tx_buffer));
    tx_buffer_size =
        ring_buf_get(&ring_buf,
                     tx_buffer,
                     (CODEC_OUTPUT_MAX_BYTES + RING_BUFFER_HEADER_SIZE)); // It always fits completely or not at all
    if (tx_buffer_size != (CODEC_OUTPUT_MAX_BYTES + RING_BUFFER_HEADER_SIZE)) {
        LOG_ERR("Failed to read from ring buffer. not enough data %d", tx_buffer_size);
        return false;
    }

    // Adjust size
    tx_buffer_size = tx_buffer[0] + (tx_buffer[1] << 8);
    if (tx_buffer_size == 0U || tx_buffer_size > CODEC_OUTPUT_MAX_BYTES) {
        LOG_ERR("Invalid encoded audio frame length: %u", tx_buffer_size);
        return false;
    }
    // LOG_PRINTK("tx_buffer_size %d\n",tx_buffer_size);

    return true;
}

//
// Pusher
//

// Thread
K_THREAD_STACK_DEFINE(pusher_stack, 4096);
static struct k_thread pusher_thread;
static uint16_t packet_next_index = 0;
static uint8_t pusher_temp_data[CODEC_OUTPUT_MAX_BYTES + NET_BUFFER_HEADER_SIZE];

static bool push_to_gatt(struct bt_conn *conn)
{
    // Read data from ring buffer
    if (!read_from_tx_queue()) {
        return false;
    }

    // Push each frame
    uint8_t *buffer = tx_buffer + RING_BUFFER_HEADER_SIZE;
    const uint16_t att_mtu = bt_gatt_get_mtu(conn);
    const uint16_t notify_capacity = att_mtu > 3U ? att_mtu - 3U : 0U;
    if (notify_capacity <= NET_BUFFER_HEADER_SIZE) {
        LOG_WRN("ATT MTU %u cannot carry the Anticipy audio header", att_mtu);
        return false;
    }

    uint32_t offset = 0;
    uint8_t index = 0;
    int retry_count = 0;
    const int max_retries = 3;

    const uint16_t frame_id = packet_next_index++;
    while (offset < tx_buffer_size) {
        // Recombine packet
        uint32_t packet_size =
            MIN(notify_capacity - NET_BUFFER_HEADER_SIZE, tx_buffer_size - offset);
        pusher_temp_data[0] = frame_id & 0xFF;
        pusher_temp_data[1] = (frame_id >> 8) & 0xFF;
        pusher_temp_data[2] = index;
        memcpy(pusher_temp_data + NET_BUFFER_HEADER_SIZE, buffer + offset, packet_size);

        retry_count = 0;
        while (retry_count < max_retries) {
            // Try send notification
            int err =
                bt_gatt_notify(conn, &audio_service.attrs[2], pusher_temp_data, packet_size + NET_BUFFER_HEADER_SIZE);

            if (err == -EAGAIN || err == -ENOMEM) {
                k_sleep(K_MSEC(2));
                retry_count++;
                continue;
            }

            if (err) {
                LOG_ERR("Audio notify failed (err %d, ATT MTU %u, value %u)",
                        err,
                        att_mtu,
                        packet_size + NET_BUFFER_HEADER_SIZE);
                return false;
            }

            // Break if success
            break;
        }

        if (retry_count >= max_retries) {
            LOG_ERR("Failed to send packet after %d retries", max_retries);
            return false;
        }

        offset += packet_size;
        index++;
    }

    return true;
}
#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
#define OPUS_PREFIX_LENGTH 1
#define OPUS_PADDED_LENGTH 80
#define MAX_WRITE_SIZE 440
static uint8_t storage_temp_data[MAX_WRITE_SIZE];
static uint16_t buffer_offset = 0;
// bool write_to_storage(void)
// {
//     if (!read_from_tx_queue())
//     {
//         return false;
//     }

//     uint8_t *buffer = tx_buffer+2;
//     const uint32_t packet_size = tx_buffer_size;
//     //load into write at 400 bytes at a time. is faster
//     memcpy(storage_temp_data + OPUS_PREFIX_LENGTH + buffer_offset, buffer, packet_size);
//     storage_temp_data[buffer_offset] = (uint8_t)tx_buffer_size;

//     buffer_offset = buffer_offset+OPUS_PADDED_LENGTH;
//     if(buffer_offset >= OPUS_PADDED_LENGTH*5) {
//     uint8_t *write_ptr = (uint8_t*)storage_temp_data;
//     write_to_file(write_ptr,OPUS_PADDED_LENGTH*5);

//     buffer_offset = 0;
//     }

//     return true;
// }
// for improving ble bandwidth
static bool write_current_frame_to_storage(void)
{
    uint8_t *buffer = tx_buffer + 2;
    uint16_t packet_size = (uint16_t) tx_buffer_size + OPUS_PREFIX_LENGTH;

    if (tx_buffer_size == 0U || packet_size > MAX_WRITE_SIZE || tx_buffer_size > UINT8_MAX) {
        LOG_ERR("Encoded frame is too large for offline storage: %u", tx_buffer_size);
        return false;
    }

    /* Flush a zero-padded block before adding a frame that would cross it. */
    if (buffer_offset + packet_size > MAX_WRITE_SIZE) {
        memset(storage_temp_data + buffer_offset, 0, MAX_WRITE_SIZE - buffer_offset);
        int rc = write_to_file(storage_temp_data, MAX_WRITE_SIZE);
        if (rc != MAX_WRITE_SIZE) {
            LOG_ERR("Offline storage write failed: %d", rc);
            return false;
        }
        memset(storage_temp_data, 0, sizeof(storage_temp_data));
        buffer_offset = 0;
    }

    storage_temp_data[buffer_offset] = (uint8_t) tx_buffer_size;
    memcpy(storage_temp_data + buffer_offset + OPUS_PREFIX_LENGTH, buffer, tx_buffer_size);
    buffer_offset += packet_size;

    if (buffer_offset == MAX_WRITE_SIZE) {
        int rc = write_to_file(storage_temp_data, MAX_WRITE_SIZE);
        if (rc != MAX_WRITE_SIZE) {
            LOG_ERR("Offline storage write failed: %d", rc);
            return false;
        }
        memset(storage_temp_data, 0, sizeof(storage_temp_data));
        buffer_offset = 0;
    }

    return true;
}

bool write_to_storage(void)
{
    if (!read_from_tx_queue()) {
        return false;
    }
    return write_current_frame_to_storage();
}

/* A 440-byte SD record can contain a fraction of a second of Opus frames.  If
 * the phone reconnects before that record fills, pad and append it before the
 * phone reads the backlog size.  Otherwise the tail would remain only in RAM
 * and could be stranded indefinitely once live streaming resumes. */
static bool flush_partial_storage_record(void)
{
    if (buffer_offset == 0U) {
        return true;
    }

    memset(storage_temp_data + buffer_offset, 0, MAX_WRITE_SIZE - buffer_offset);
    int rc = write_to_file(storage_temp_data, MAX_WRITE_SIZE);
    if (rc != MAX_WRITE_SIZE) {
        LOG_ERR("Offline tail flush failed: %d", rc);
        return false;
    }

    memset(storage_temp_data, 0, sizeof(storage_temp_data));
    buffer_offset = 0;
    return true;
}

int transport_clear_offline_audio(void)
{
    k_mutex_lock(&write_sdcard_mutex, K_FOREVER);

    /* Do this before truncating the file, otherwise frames captured before an
     * erase command could later be appended back into the empty file. */
    memset(storage_temp_data, 0, sizeof(storage_temp_data));
    buffer_offset = 0;
    int rc = clear_audio_directory();

    k_mutex_unlock(&write_sdcard_mutex);
    return rc;
}

#define MAX_FILES 10
#define MAX_AUDIO_FILE_SIZE 300000
static uint8_t heartbeat_count = 0;
void update_file_size()
{
    file_num_array[0] = get_file_size(1);
    file_num_array[1] = get_offset();
    // LOG_PRINTK("file size for file count %d %d\n",file_count,file_num_array[0]);
    // LOG_PRINTK("offset for file count %d %d\n",file_count,file_num_array[1]);
}
#endif

void pusher(void)
{
    k_msleep(500);
    bool was_valid = false;

    while (1) {
        /* Sleep until the codec has actually queued a frame.  A bare k_yield()
         * immediately reschedules this sole priority-7 thread and burns the
         * battery while idle. */
        (void) k_sem_take(&tx_data_ready, K_FOREVER);
        atomic_set(&pusher_busy, 1);

        //
        // Load current connection
        //
        struct bt_conn *conn = get_current_connection();
#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
        // updating the most recent file size is expensive!
        static bool file_size_updated = true;
        static bool connection_was_true = false;
        if (conn && !connection_was_true) {
            k_msleep(100);
            k_mutex_lock(&write_sdcard_mutex, K_FOREVER);
            if (is_sd_on() && !flush_partial_storage_record()) {
                LOG_ERR("Offline tail could not be finalized before reconnect");
            }
            k_mutex_unlock(&write_sdcard_mutex);
            file_size_updated = false;
            connection_was_true = true;
        } else if (!conn) {
            connection_was_true = false;
        }
        if (!file_size_updated) {
            LOG_PRINTK("updating file size\n");
            update_file_size();

            file_size_updated = true;
        }
#endif
        if (conn) {
            current_mtu = bt_gatt_get_mtu(conn);
        }
        bool valid = true;
        if (current_mtu < MINIMAL_PACKET_SIZE) {
            valid = false;
        } else if (!conn) {
            valid = false;
        } else if (!transport_peer_is_authorized(conn)) {
            valid = false;
        } else {
            valid = bt_gatt_is_subscribed(conn, &audio_service.attrs[2], BT_GATT_CCC_NOTIFY); // Check if subscribed
        }

        if (!valid) {
#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
            bool result = false;
            bool consumed = false;
            if (file_num_array[0] < MAX_STORAGE_BYTES) {
                k_mutex_lock(&write_sdcard_mutex, K_FOREVER);
                if (is_sd_on()) {
                    result = write_to_storage();
                    consumed = true;
                }
                k_mutex_unlock(&write_sdcard_mutex);
            }
            if (!consumed) {
                (void) read_from_tx_queue();
            }
            if (result) {
                heartbeat_count++;
                if (heartbeat_count == 255) {
                    update_file_size();
                    heartbeat_count = 0;
                    LOG_PRINTK("drawing\n");
                }
            }
#else
            /* Friday Core is live-stream only.  Consume and discard frames
             * until an encrypted subscriber is ready. */
            (void) read_from_tx_queue();
#endif
            was_valid = false;
        }
        if (valid) {
            if (!was_valid) {
                /* Drop every frame whose ready token predates the first valid
                 * encrypted subscription.  This prevents pre-subscription
                 * microphone audio from leaking after pairing completes. */
                do {
                    (void) read_from_tx_queue();
                } while (k_sem_take(&tx_data_ready, K_NO_WAIT) == 0);
                was_valid = true;
                if (conn) {
                    bt_conn_unref(conn);
                }
                atomic_clear(&pusher_busy);
                continue;
            }

            bool sent = push_to_gatt(conn);
#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
            if (!sent) {
                /* push_to_gatt has already dequeued this frame.  Preserve it
                 * locally if BLE could not even queue the notification. */
                k_mutex_lock(&write_sdcard_mutex, K_FOREVER);
                if (is_sd_on() && !write_current_frame_to_storage()) {
                    LOG_ERR("Failed to preserve unsent live frame on SD");
                }
                k_mutex_unlock(&write_sdcard_mutex);
            }
#else
            ARG_UNUSED(sent);
#endif
        }
        if (conn) {
            bt_conn_unref(conn);
        }
        atomic_clear(&pusher_busy);
    }
}
#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
extern struct bt_gatt_service storage_service;
#endif
//
// Public functions
//
int bt_off()
{
    atomic_clear(&advertising_desired);
#ifdef CONFIG_BT_FILTER_ACCEPT_LIST
    atomic_clear(&provisioning_open);
    atomic_clear(&owner_connection_authorized);
    (void) k_work_cancel_delayable(&owner_provisioning_timeout_work);
#endif

    /* Stop PDM/codec input first, then allow the pusher to account for every
     * frame already accepted into the queue before storage is committed and
     * suspended. */
    mic_off();
    int64_t drain_deadline = k_uptime_get() + 1000;
    while ((k_sem_count_get(&tx_data_ready) != 0U ||
            atomic_get(&pusher_busy) != 0) &&
           k_uptime_get() < drain_deadline) {
        k_msleep(2);
    }
    if (k_sem_count_get(&tx_data_ready) != 0U || atomic_get(&pusher_busy) != 0) {
        LOG_ERR("Audio queue did not drain before shutdown");
    }

    // First disconnect any active connections
    struct bt_conn *conn = get_current_connection();
    if (conn != NULL) {
        bt_conn_disconnect(conn, BT_HCI_ERR_REMOTE_USER_TERM_CONN);
        bt_conn_unref(conn);
    }

    // Stop advertising
    int err = bt_le_adv_stop();
    if (err && err != -EALREADY) {
        LOG_ERR("Failed to stop Bluetooth advertising %d", err);
    }

    /* Commit persistent storage after the audio producer and consumer are
     * quiescent, but before its backend can be suspended or powered down. */
#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
    k_mutex_lock(&write_sdcard_mutex, K_FOREVER);
    if (is_sd_on() && !flush_partial_storage_record()) {
        LOG_ERR("Offline tail could not be finalized before shutdown");
    }
    sd_off();
    k_mutex_unlock(&write_sdcard_mutex);
#endif

    // Disable Bluetooth after disconnect and the final storage commit.
    err = bt_disable();
    if (err) {
        LOG_ERR("Failed to disable Bluetooth %d", err);
    }
    // Ensure all Bluetooth resources are cleaned up
    is_connected = false;
#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
    storage_is_on = false;
#endif
    current_mtu = 0;

    return 0;
}
int bt_on()
{
    int err = bt_enable(NULL);
    if (err) {
        return err;
    }

    err = settings_load();
    if (err) {
        return err;
    }

#ifdef CONFIG_BT_FILTER_ACCEPT_LIST
    err = refresh_owner_filter();
    if (err) {
        return err;
    }
#endif

    err = start_transport_advertising();
    if (err && err != -EACCES) {
        return err;
    }
#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
    bt_gatt_service_register(&storage_service);
    sd_on();
#endif
    mic_on();
    atomic_set(&advertising_desired, err == 0);

    return 0;
}

// periodic advertising
int transport_start()
{
    int err;

#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
    k_mutex_init(&write_sdcard_mutex);
#endif

    // Configure callbacks
    bt_conn_cb_register(&_callback_references);
#ifdef CONFIG_BT_FILTER_ACCEPT_LIST
    err = bt_conn_auth_info_cb_register(&owner_auth_callbacks);
    if (err) {
        LOG_ERR("Failed to register BLE owner callbacks (err %d)", err);
        return err;
    }
#endif

    // Enable Bluetooth
    err = bt_enable(NULL);
    if (err) {
        LOG_ERR("Transport bluetooth init failed (err %d)", err);
        return err;
    }
    LOG_INF("Transport bluetooth initialized");

    err = settings_load();
    if (err) {
        LOG_ERR("Failed to load Bluetooth bonds (err %d)", err);
        return err;
    }

#ifdef CONFIG_BT_FILTER_ACCEPT_LIST
    err = prepare_owner_policy();
    if (err) {
        LOG_ERR("Failed to prepare BLE owner policy (err %d)", err);
        return err;
    }
#endif

    //  Enable button
#ifdef CONFIG_OMI_ENABLE_BUTTON
    register_button_service();
#endif

#ifdef CONFIG_OMI_ENABLE_SPEAKER
    register_speaker_service();
#endif

#ifdef CONFIG_OMI_ENABLE_HAPTIC
    register_haptic_service();
#endif

    // Start advertising
#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
    memset(storage_temp_data, 0, OPUS_PADDED_LENGTH * 4);
    bt_gatt_service_register(&storage_service);
#endif
    bt_gatt_service_register(&audio_service);
    bt_gatt_service_register(&dfu_service);
    err = start_transport_advertising();
    if (err == -EACCES) {
        LOG_WRN("BLE remains locked until a physical provisioning boot");
        atomic_clear(&advertising_desired);
    } else if (err) {
        LOG_ERR("Transport advertising failed to start (err %d)", err);
        return err;
    } else {
        LOG_INF("Advertising successfully started");
        atomic_set(&advertising_desired, 1);
#ifdef CONFIG_BT_FILTER_ACCEPT_LIST
        if (!atomic_get(&owner_present)) {
            k_work_schedule(&owner_provisioning_timeout_work,
                            K_SECONDS(OWNER_PROVISIONING_TIMEOUT_SECONDS));
        }
#endif
    }

    // Start pusher
    ring_buf_init(&ring_buf, sizeof(tx_queue), tx_queue);
    k_thread_create(&pusher_thread,
                    pusher_stack,
                    K_THREAD_STACK_SIZEOF(pusher_stack),
                    (k_thread_entry_t) pusher,
                    NULL,
                    NULL,
                    NULL,
                    K_PRIO_PREEMPT(7),
                    0,
                    K_NO_WAIT);

    return 0;
}

struct bt_conn *get_current_connection()
{
    struct bt_conn *conn;
    k_spinlock_key_t key = k_spin_lock(&connection_lock);
    conn = current_connection;
    if (conn != NULL) {
        bt_conn_ref(conn);
    }
    k_spin_unlock(&connection_lock, key);
    return conn;
}

int broadcast_audio_packets(uint8_t *buffer, size_t size)
{
    if (buffer == NULL || size == 0U || size > CODEC_OUTPUT_MAX_BYTES) {
        LOG_ERR("Rejected invalid encoded audio frame length: %u", (unsigned int) size);
        return -EINVAL;
    }

    int retry_count = 0;
    const int max_retries = 3;

    while (retry_count < max_retries && !write_to_tx_queue(buffer, size)) {
        k_sleep(K_MSEC(1));
        retry_count++;
    }

    if (retry_count >= max_retries) {
        LOG_ERR("Failed to write to tx queue after %d retries", max_retries);
        return -1;
    }

    k_sem_give(&tx_data_ready);
    return 0;
}

void accel_off()
{
#ifdef CONFIG_OMI_ENABLE_ACCELEROMETER
    gpio_pin_set_dt(&accel_gpio_pin, 0);
#endif
}
