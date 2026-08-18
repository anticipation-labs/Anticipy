#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include <hal/nrf_power.h>
#include <soc.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/services/bas.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/settings/settings.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/ring_buffer.h>

#include "battery_smoother.h"
#include "codec.h"
#include "config.h"
#include "led.h"
#include "lib/battery/battery.h"
#include "mic.h"
#include "transport.h"
#include "transport_safety.h"
#include "watchdog.h"

LOG_MODULE_REGISTER(transport, CONFIG_LOG_DEFAULT_LEVEL);

#define BATTERY_REFRESH_INTERVAL 15000
#define AUDIO_VALUE_ATTRIBUTE_INDEX 2u
#define AUDIO_NOTIFY_RETRY_LIMIT 8u
#define AUDIO_NOTIFY_RETRY_DELAY_MS 1u
#define ADVERTISING_RESTART_RETRY_LIMIT 8u
#define ADVERTISING_RESTART_DELAY_MS 100u
#define ADVERTISING_RECOVERY_DELAY_MS 5000u
#define TX_RECORD_HEADER_BYTES 2u

/*
 * Adafruit nRF52 bootloader GPREGRET magic. 0xA8 (DFU_MAGIC_OTA_RESET) asks
 * the installed bootloader for BLE-OTA mode only: it does NOT enumerate the
 * UF2 mass-storage volume or a CDC endpoint, and it has NO inactivity
 * timeout, so the device stays in OTA mode until it is reflashed or power
 * cycled. The complementary cable hatch in recovery_usb.c uses 0x57
 * (DFU_MAGIC_UF2_RESET), which mounts UF2 + CDC and self-heals back to the
 * application in roughly three seconds if nothing is written.
 */
#define ADAFRUIT_OTA_RESET_MAGIC 0xA8u

#define DFU_CONTROL_POINT_ENTER_BOOTLOADER 0x06u
#define DFU_CONTROL_POINT_START_DFU 0x01u
#define DFU_CONTROL_POINT_RESPONSE_OK 0x10u

/*
 * Give the controller a brief window to put the acknowledgement notification
 * on air before the SoC is reset out from under the link. The reset happens
 * unconditionally afterwards, so a dropped notification only costs the
 * central its confirmation, never the hatch itself.
 */
#define DFU_RESET_NOTIFY_FLUSH_MS 120u

static struct bt_conn *current_connection;
static struct k_spinlock connection_lock;
static atomic_t audio_stream_active;
static atomic_t audio_epoch;
static atomic_t pending_audio_error;
static atomic_t requested_audio_state;
static atomic_t audio_request_epoch;
static struct k_spinlock audio_request_lock;
static atomic_t fresh_audio_ccc_authorized;
static struct bt_conn *fresh_audio_ccc_connection;
static atomic_t transport_ready;
static atomic_t advertising_restart_attempts;

static struct bt_uuid_128 audio_service_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(
        0x19B10000, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));
static struct bt_uuid_128 audio_characteristic_data_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(
        0x19B10001, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));
static struct bt_uuid_128 audio_characteristic_format_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(
        0x19B10002, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));

static void audio_ccc_config_changed_handler(
    const struct bt_gatt_attr *attr,
    uint16_t value);
static ssize_t audio_ccc_authorize_write(
    struct bt_conn *conn,
    const struct bt_gatt_attr *attr,
    uint16_t value);
static bool audio_ccc_authorized_match(
    struct bt_conn *conn,
    const struct bt_gatt_attr *attr);
static ssize_t audio_data_read_characteristic(
    struct bt_conn *conn,
    const struct bt_gatt_attr *attr,
    void *buf,
    uint16_t len,
    uint16_t offset);
static ssize_t audio_codec_read_characteristic(
    struct bt_conn *conn,
    const struct bt_gatt_attr *attr,
    void *buf,
    uint16_t len,
    uint16_t offset);

static void dfu_ccc_config_changed_handler(
    const struct bt_gatt_attr *attr,
    uint16_t value);
static ssize_t dfu_control_point_write_handler(
    struct bt_conn *conn,
    const struct bt_gatt_attr *attr,
    const void *buf,
    uint16_t len,
    uint16_t offset,
    uint8_t flags);

static struct _bt_gatt_ccc audio_ccc =
    BT_GATT_CCC_INITIALIZER(
        audio_ccc_config_changed_handler,
        audio_ccc_authorize_write,
        audio_ccc_authorized_match);

/*
 * These encrypted permissions create a bonded link before codec reads or
 * audio subscription. This is not owner authentication: without a physical
 * enrollment/erase gesture, the first nearby central can still become the
 * sole stored bond.
 */
static struct bt_gatt_attr audio_service_attr[] = {
    BT_GATT_PRIMARY_SERVICE(&audio_service_uuid),
    BT_GATT_CHARACTERISTIC(
        &audio_characteristic_data_uuid.uuid,
        BT_GATT_CHRC_READ | BT_GATT_CHRC_NOTIFY,
        BT_GATT_PERM_READ_ENCRYPT,
        audio_data_read_characteristic,
        NULL,
        NULL),
    BT_GATT_CCC_MANAGED(
        &audio_ccc,
        BT_GATT_PERM_READ_ENCRYPT | BT_GATT_PERM_WRITE_ENCRYPT),
    BT_GATT_CHARACTERISTIC(
        &audio_characteristic_format_uuid.uuid,
        BT_GATT_CHRC_READ,
        BT_GATT_PERM_READ_ENCRYPT,
        audio_codec_read_characteristic,
        NULL,
        NULL),
};

static struct bt_gatt_service audio_service =
    BT_GATT_SERVICE(audio_service_attr);

/*
 * Nordic Legacy DFU service 00001530-1212-EFDE-1523-785FEABCD123 with control
 * point 00001531-1212-EFDE-1523-785FEABCD123. This is the wireless half of
 * the dual recovery surface and is the SAME service exposed by the image
 * currently running on the pendant, so it is a proven escape hatch rather
 * than a new one. It is restored here because the previous live-stream
 * candidate removed it, which would have traded the only proven route into
 * the bootloader for an unproven one in a single irreversible step.
 */
static struct bt_uuid_128 dfu_service_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(
        0x00001530, 0x1212, 0xEFDE, 0x1523, 0x785FEABCD123));
static struct bt_uuid_128 dfu_control_point_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(
        0x00001531, 0x1212, 0xEFDE, 0x1523, 0x785FEABCD123));

/*
 * DELIBERATELY OPEN IN THIS BRIDGE IMAGE.
 *
 * The control point uses BT_GATT_PERM_WRITE (no encryption, no bonding)
 * rather than BT_GATT_PERM_WRITE_ENCRYPT. An open door we can reach beats a
 * locked door we cannot: this pendant has no usable RESET button, so a
 * recovery surface that is unreachable because bonding is broken, the bond
 * was lost, or the peer cannot pair is equivalent to no recovery surface at
 * all. The audio path above stays encryption-gated and is unaffected.
 *
 * SECURITY DEBT: anyone in radio range can write 0x06 here and force the
 * pendant into the bootloader (denial of service; it cannot read audio or
 * exfiltrate data this way, but it can take the device off the air until it
 * is reflashed or power cycled). This MUST be tightened to
 * BT_GATT_PERM_WRITE_ENCRYPT once a real bonding/enrollment gesture exists
 * and a second independent recovery route has been physically confirmed on
 * the hardware. Do not ship a general-availability image with this open.
 */
static struct bt_gatt_attr dfu_service_attr[] = {
    BT_GATT_PRIMARY_SERVICE(&dfu_service_uuid),
    BT_GATT_CHARACTERISTIC(
        &dfu_control_point_uuid.uuid,
        BT_GATT_CHRC_WRITE | BT_GATT_CHRC_NOTIFY,
        BT_GATT_PERM_WRITE,
        NULL,
        dfu_control_point_write_handler,
        NULL),
    BT_GATT_CCC(
        dfu_ccc_config_changed_handler,
        BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
};

static struct bt_gatt_service dfu_service =
    BT_GATT_SERVICE(dfu_service_attr);

static const struct bt_data advertising_data[] = {
    BT_DATA_BYTES(BT_DATA_FLAGS,
                  BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR),
    BT_DATA(BT_DATA_UUID128_ALL, audio_service_uuid.val,
            sizeof(audio_service_uuid.val)),
    BT_DATA(BT_DATA_NAME_COMPLETE, CONFIG_BT_DEVICE_NAME,
            sizeof(CONFIG_BT_DEVICE_NAME) - 1u),
};

/*
 * The DFU service UUID rides in the SCAN RESPONSE, not the advertisement, for
 * two reasons: the 31-byte advertisement is already full (flags 3 + audio
 * UUID128 18 + complete name 10 = 31 for "Anticipy"), and this mirrors the
 * upstream layout that Nordic's nRF Connect / nRF Device Manager DFU tools
 * expect when they scan for a recoverable device.
 *
 * Scan-response budget: UUID16 pair 2 + 4 = 6 bytes, DFU UUID128 2 + 16 = 18
 * bytes, total 24 of the 31 available.
 */
static const struct bt_data scan_response_data[] = {
    BT_DATA_BYTES(
        BT_DATA_UUID16_ALL,
        BT_UUID_16_ENCODE(BT_UUID_BAS_VAL),
        BT_UUID_16_ENCODE(BT_UUID_DIS_VAL)),
    BT_DATA(BT_DATA_UUID128_ALL, dfu_service_uuid.val,
            sizeof(dfu_service_uuid.val)),
};

static struct bt_conn *acquire_current_connection(void)
{
    k_spinlock_key_t key = k_spin_lock(&connection_lock);
    struct bt_conn *conn = current_connection;
    if (conn != NULL) {
        conn = bt_conn_ref(conn);
    }
    k_spin_unlock(&connection_lock, key);
    return conn;
}

static bool connection_is_current(struct bt_conn *conn)
{
    k_spinlock_key_t key = k_spin_lock(&connection_lock);
    bool current =
        conn != NULL && current_connection == conn;
    k_spin_unlock(&connection_lock, key);
    return current;
}

static void clear_fresh_audio_authorization(void)
{
    k_spinlock_key_t key = k_spin_lock(&connection_lock);
    fresh_audio_ccc_connection = NULL;
    atomic_clear(&fresh_audio_ccc_authorized);
    k_spin_unlock(&connection_lock, key);
}

static bool bind_fresh_audio_authorization(struct bt_conn *conn)
{
    k_spinlock_key_t key = k_spin_lock(&connection_lock);
    bool authorized =
        conn != NULL && current_connection == conn;
    fresh_audio_ccc_connection = authorized ? conn : NULL;
    atomic_set(&fresh_audio_ccc_authorized, authorized ? 1 : 0);
    k_spin_unlock(&connection_lock, key);
    return authorized;
}

static bool connection_has_fresh_audio_authorization(
    struct bt_conn *conn)
{
    k_spinlock_key_t key = k_spin_lock(&connection_lock);
    bool authorized =
        conn != NULL &&
        current_connection == conn &&
        fresh_audio_ccc_connection == conn &&
        atomic_get(&fresh_audio_ccc_authorized) != 0;
    k_spin_unlock(&connection_lock, key);
    return authorized;
}

static bool audio_capture_authorized(struct bt_conn *conn)
{
    return connection_has_fresh_audio_authorization(conn) &&
           bt_gatt_is_subscribed(
               conn,
               &audio_service.attrs[AUDIO_VALUE_ATTRIBUTE_INDEX],
               BT_GATT_CCC_NOTIFY);
}

static void restart_advertising(struct k_work *work_item);
K_WORK_DELAYABLE_DEFINE(advertising_restart_work, restart_advertising);

static void restart_advertising(struct k_work *work_item)
{
    ARG_UNUSED(work_item);
    if (!atomic_get(&transport_ready)) {
        return;
    }

    struct bt_conn *conn = acquire_current_connection();
    if (conn != NULL) {
        bt_conn_unref(conn);
        return;
    }

    int err = bt_le_adv_start(
        BT_LE_ADV_CONN,
        advertising_data,
        ARRAY_SIZE(advertising_data),
        scan_response_data,
        ARRAY_SIZE(scan_response_data));
    if (err == 0 || err == -EALREADY) {
        atomic_clear(&advertising_restart_attempts);
        LOG_INF("Connectable advertising restored");
        return;
    }

    atomic_val_t attempt =
        atomic_inc(&advertising_restart_attempts) + 1;
    if (attempt < ADVERTISING_RESTART_RETRY_LIMIT) {
        LOG_WRN("Advertising restart attempt %d failed: %d",
                (int)attempt, err);
        (void)k_work_reschedule(
            &advertising_restart_work,
            K_MSEC(ADVERTISING_RESTART_DELAY_MS));
    } else {
        LOG_ERR("Advertising restart exhausted after %d attempts: %d",
                (int)attempt, err);
        /*
         * Bound each fast retry burst without permanently stranding the
         * device after a transient controller/resource fault.
         */
        atomic_clear(&advertising_restart_attempts);
        (void)k_work_reschedule(
            &advertising_restart_work,
            K_MSEC(ADVERTISING_RECOVERY_DELAY_MS));
    }
}

static uint8_t tx_queue[
    NETWORK_RING_BUF_SIZE *
    (CODEC_OUTPUT_MAX_BYTES + TX_RECORD_HEADER_BYTES)];
static struct ring_buf tx_ring_buf;
static struct k_spinlock tx_ring_lock;
K_SEM_DEFINE(tx_data_ready, 0, 1);

static void reset_audio_queues(void)
{
    atomic_clear(&audio_stream_active);
    codec_reset();

    k_spinlock_key_t key = k_spin_lock(&tx_ring_lock);
    ring_buf_reset(&tx_ring_buf);
    memset(tx_queue, 0, sizeof(tx_queue));
    atomic_inc(&audio_epoch);
    k_spin_unlock(&tx_ring_lock, key);
    k_sem_give(&tx_data_ready);
}

static int stop_audio_pipeline(void)
{
    atomic_clear(&audio_stream_active);
    int mic_error = mic_stop();
    reset_audio_queues();
    if (mic_error != 0) {
        /*
         * Keep the recording indicator lit if hardware stop is unconfirmed.
         */
        return mic_error;
    }
    return set_led_blue(false);
}

static int start_audio_pipeline(struct bt_conn *authorized_connection)
{
    int err = stop_audio_pipeline();
    if (err != 0) {
        return err;
    }
    err = set_led_blue(true);
    if (err != 0) {
        return err;
    }
    /*
     * Revalidate the same current connection and its fresh CCC write at the
     * last possible point before powering PDM. Subscription state alone is
     * insufficient because a restored CCC or replacement connection can
     * otherwise race an already queued start request.
     */
    if (!audio_capture_authorized(authorized_connection)) {
        (void)set_led_blue(false);
        return -EACCES;
    }
    err = mic_start();
    if (err != 0) {
        (void)set_led_blue(false);
        reset_audio_queues();
        return err;
    }
    return 0;
}

bool transport_audio_is_active(void)
{
    return atomic_get(&audio_stream_active) != 0;
}

K_SEM_DEFINE(audio_control_event, 0, 1);
K_THREAD_STACK_DEFINE(audio_control_stack, 2048);
static struct k_thread audio_control_thread;

static void request_audio_state(bool enabled, int error)
{
    k_spinlock_key_t key = k_spin_lock(&audio_request_lock);
    if (!enabled) {
        atomic_clear(&audio_stream_active);
    }
    atomic_set(&requested_audio_state, enabled ? 1 : 0);
    atomic_inc(&audio_request_epoch);
    k_spin_unlock(&audio_request_lock, key);
    if (error != 0) {
        atomic_set(&pending_audio_error, error);
    }
    k_sem_give(&audio_control_event);
}

static ssize_t audio_ccc_authorize_write(
    struct bt_conn *conn,
    const struct bt_gatt_attr *attr,
    uint16_t value)
{
    ARG_UNUSED(attr);
    if (value != 0u && value != BT_GATT_CCC_NOTIFY) {
        return BT_GATT_ERR(BT_ATT_ERR_VALUE_NOT_ALLOWED);
    }

    bool authorized =
        value == BT_GATT_CCC_NOTIFY &&
        bind_fresh_audio_authorization(conn);
    if (!authorized) {
        clear_fresh_audio_authorization();
    }
    /*
     * This callback runs only for an actual CCC write from the current
     * encrypted connection. Restored bonded CCC state never reaches it. If
     * the stored CCC was already NOTIFY, cfg_changed will not run again, so
     * explicitly authorize that already-committed value here.
     */
    if (!authorized) {
        request_audio_state(false, value == 0u ? 0 : -EACCES);
    } else if (bt_gatt_is_subscribed(
                   conn,
                   &audio_service.attrs[AUDIO_VALUE_ATTRIBUTE_INDEX],
                   BT_GATT_CCC_NOTIFY)) {
        request_audio_state(true, 0);
    }
    return sizeof(value);
}

static bool audio_ccc_authorized_match(
    struct bt_conn *conn,
    const struct bt_gatt_attr *attr)
{
    ARG_UNUSED(attr);
    return connection_has_fresh_audio_authorization(conn);
}

static void audio_control(
    void *unused1,
    void *unused2,
    void *unused3)
{
    ARG_UNUSED(unused1);
    ARG_UNUSED(unused2);
    ARG_UNUSED(unused3);

    while (true) {
        (void)k_sem_take(&audio_control_event, K_FOREVER);
        int pending_error =
            (int)atomic_set(&pending_audio_error, 0);
        if (pending_error != 0) {
            LOG_ERR("Audio pipeline faulted: %d", pending_error);
        }

        k_spinlock_key_t key =
            k_spin_lock(&audio_request_lock);
        bool requested =
            atomic_get(&requested_audio_state) != 0;
        atomic_val_t request_epoch =
            atomic_get(&audio_request_epoch);
        k_spin_unlock(&audio_request_lock, key);

        if (!requested) {
            int stop_error = stop_audio_pipeline();
            if (stop_error != 0) {
                LOG_ERR("Audio pipeline stop failed: %d", stop_error);
            }
            continue;
        }

        struct bt_conn *conn = acquire_current_connection();
        if (!audio_capture_authorized(conn)) {
            if (conn != NULL) {
                bt_conn_unref(conn);
            }
            request_audio_state(false, -EACCES);
            continue;
        }

        int start_error = start_audio_pipeline(conn);
        if (start_error != 0) {
            bt_conn_unref(conn);
            request_audio_state(false, start_error);
            continue;
        }

        key = k_spin_lock(&audio_request_lock);
        bool commit =
            atomic_get(&requested_audio_state) != 0 &&
            atomic_get(&audio_request_epoch) == request_epoch &&
            audio_capture_authorized(conn);
        if (commit) {
            atomic_set(&audio_stream_active, 1);
        }
        k_spin_unlock(&audio_request_lock, key);
        bt_conn_unref(conn);
        if (commit) {
            LOG_INF("Encrypted audio capture started");
        } else {
            int stop_error = stop_audio_pipeline();
            if (stop_error != 0) {
                LOG_ERR("Superseded audio start could not stop: %d",
                        stop_error);
            }
        }
    }
}

void transport_audio_fault(int error)
{
    request_audio_state(false, error != 0 ? error : -EIO);
}

static ssize_t audio_data_read_characteristic(
    struct bt_conn *conn,
    const struct bt_gatt_attr *attr,
    void *buf,
    uint16_t len,
    uint16_t offset)
{
    return bt_gatt_attr_read(conn, attr, buf, len, offset, NULL, 0);
}

static ssize_t audio_codec_read_characteristic(
    struct bt_conn *conn,
    const struct bt_gatt_attr *attr,
    void *buf,
    uint16_t len,
    uint16_t offset)
{
    const uint8_t codec_id = CODEC_ID;
    return bt_gatt_attr_read(
        conn, attr, buf, len, offset, &codec_id, sizeof(codec_id));
}

static void audio_ccc_config_changed_handler(
    const struct bt_gatt_attr *attr,
    uint16_t value)
{
    ARG_UNUSED(attr);
    if (value == BT_GATT_CCC_NOTIFY) {
        struct bt_conn *conn = acquire_current_connection();
        bool authorized =
            connection_has_fresh_audio_authorization(conn);
        if (conn != NULL) {
            bt_conn_unref(conn);
        }
        if (authorized) {
            request_audio_state(true, 0);
        } else {
            /*
             * BT_SETTINGS may restore a bonded peer's old CCC. Restoration
             * is not fresh per-connection consent and must never start PDM.
             */
            request_audio_state(false, -EACCES);
        }
        return;
    }

    clear_fresh_audio_authorization();
    request_audio_state(false, 0);
    if (value == 0u) {
        LOG_INF("Audio capture stop requested");
    } else {
        LOG_ERR("Unsupported audio CCC value: %u", value);
    }
}

/*
 * Legacy DFU control point.
 *
 * Never returns on a recognised bootloader request. Both accepted encodings
 * end in NVIC_SystemReset() after arming GPREGRET, exactly as the image
 * currently on the pendant does, so the installed Adafruit bootloader sees
 * the request it already knows how to honour.
 */
static void enter_ota_bootloader(void)
{
    /*
     * The nRF52 watchdog keeps running across a soft reset and cannot be
     * stopped once started, so the bootloader inherits it. Feed it one last
     * time here to hand the bootloader a full, fresh timeout window for the
     * OTA transfer. See watchdog.h for why that window is deliberately long.
     */
    watchdog_feed();
    nrf_power_gpregret_set(NRF_POWER, ADAFRUIT_OTA_RESET_MAGIC);
    __DSB();
    NVIC_SystemReset();
}

static void dfu_ccc_config_changed_handler(
    const struct bt_gatt_attr *attr,
    uint16_t value)
{
    ARG_UNUSED(attr);
    if (value == BT_GATT_CCC_NOTIFY) {
        LOG_INF("DFU control point notifications enabled");
    } else if (value == 0u) {
        LOG_INF("DFU control point notifications disabled");
    } else {
        LOG_WRN("Unsupported DFU CCC value: %u", value);
    }
}

static ssize_t dfu_control_point_write_handler(
    struct bt_conn *conn,
    const struct bt_gatt_attr *attr,
    const void *buf,
    uint16_t len,
    uint16_t offset,
    uint8_t flags)
{
    ARG_UNUSED(offset);
    ARG_UNUSED(flags);

    if (buf == NULL) {
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN);
    }

    const uint8_t *request = (const uint8_t *)buf;

    if (len == 1u &&
        request[0] == DFU_CONTROL_POINT_ENTER_BOOTLOADER) {
        LOG_WRN("DFU 0x06 accepted; resetting into OTA bootloader");
        enter_ota_bootloader();
        /* Unreachable. */
        return len;
    }

    if (len == 2u && request[0] == DFU_CONTROL_POINT_START_DFU) {
        /*
         * Nordic's legacy "start DFU" opcode. Acknowledge before resetting so
         * a central that waits for the response does not report a failure,
         * then take the same route as 0x06.
         */
        uint8_t response = DFU_CONTROL_POINT_RESPONSE_OK;
        int err = bt_gatt_notify(conn, attr, &response, sizeof(response));
        if (err != 0) {
            LOG_WRN("DFU acknowledgement not queued: %d", err);
        }
        k_sleep(K_MSEC(DFU_RESET_NOTIFY_FLUSH_MS));
        LOG_WRN("DFU 0x01 accepted; resetting into OTA bootloader");
        enter_ota_bootloader();
        /* Unreachable. */
        return len;
    }

    LOG_WRN("Ignoring unrecognised DFU control point write (len %u)", len);
    return len;
}

static struct battery_smoother battery_percentage_smoother;
static bool battery_ready;
static K_MUTEX_DEFINE(battery_smoother_lock);
static atomic_t battery_epoch;
static void broadcast_battery_level(struct k_work *work_item);
K_WORK_DELAYABLE_DEFINE(battery_work, broadcast_battery_level);

static void broadcast_battery_level(struct k_work *work_item)
{
    ARG_UNUSED(work_item);
    if (!battery_ready) {
        return;
    }

    struct bt_conn *conn = acquire_current_connection();
    if (conn == NULL) {
        return;
    }
    atomic_val_t measurement_epoch = atomic_get(&battery_epoch);
    uint16_t battery_millivolt;
    uint8_t raw_battery_percentage;
    int voltage_error = battery_get_millivolt(&battery_millivolt);
    int percentage_error =
        voltage_error == 0
            ? battery_get_percentage(
                  &raw_battery_percentage, battery_millivolt)
            : voltage_error;
    if (percentage_error == 0) {
        k_mutex_lock(&battery_smoother_lock, K_FOREVER);
        bool current =
            measurement_epoch == atomic_get(&battery_epoch) &&
            connection_is_current(conn);
        uint8_t battery_percentage = 0u;
        if (current) {
            battery_percentage =
                battery_smoother_update(
                    &battery_percentage_smoother,
                    raw_battery_percentage);
        }
        k_mutex_unlock(&battery_smoother_lock);

        if (current &&
            measurement_epoch == atomic_get(&battery_epoch) &&
            connection_is_current(conn)) {
            int err =
                bt_bas_set_battery_level(battery_percentage);
            if (err != 0) {
                LOG_ERR("Battery notification failed: %d", err);
            }
        }
    } else {
        LOG_ERR("Battery measurement failed: %d", percentage_error);
        /*
         * BAS has no unknown/stale sentinel. Disconnect instead of leaving
         * a normal-looking stale percentage or misrepresenting "unknown" as
         * 0%. Startup measurement failure remains fatal before advertising.
         */
        k_mutex_lock(&battery_smoother_lock, K_FOREVER);
        battery_smoother_reset(&battery_percentage_smoother);
        k_mutex_unlock(&battery_smoother_lock);
        if (measurement_epoch == atomic_get(&battery_epoch) &&
            connection_is_current(conn)) {
            int err = bt_conn_disconnect(
                conn, BT_HCI_ERR_REMOTE_USER_TERM_CONN);
            if (err != 0) {
                LOG_ERR("Battery fault disconnect failed: %d", err);
            }
        }
    }

    if (percentage_error == 0 &&
        measurement_epoch == atomic_get(&battery_epoch) &&
        connection_is_current(conn)) {
        k_work_reschedule(
            &battery_work, K_MSEC(BATTERY_REFRESH_INTERVAL));
    }
    bt_conn_unref(conn);
}

static void transport_connected(struct bt_conn *conn, uint8_t err)
{
    if (err != 0) {
        LOG_ERR("Bluetooth connection failed: %u", err);
        return;
    }

    /*
     * Track every successful connection before optional diagnostic queries.
     * Missing LE data-length/PHY fields must not create an untracked live link.
     */
    struct bt_conn *new_connection = bt_conn_ref(conn);
    k_spinlock_key_t key = k_spin_lock(&connection_lock);
    struct bt_conn *old_connection = current_connection;
    current_connection = new_connection;
    fresh_audio_ccc_connection = NULL;
    atomic_clear(&fresh_audio_ccc_authorized);
    k_spin_unlock(&connection_lock, key);
    if (old_connection != NULL) {
        bt_conn_unref(old_connection);
    }
    (void)k_work_cancel_delayable(&advertising_restart_work);
    atomic_clear(&advertising_restart_attempts);

    request_audio_state(false, 0);
    atomic_inc(&battery_epoch);
    if (battery_ready) {
        k_mutex_lock(&battery_smoother_lock, K_FOREVER);
        battery_smoother_reset(&battery_percentage_smoother);
        k_mutex_unlock(&battery_smoother_lock);
        (void)k_work_reschedule(&battery_work, K_NO_WAIT);
    }

    struct bt_conn_info info = {0};
    int info_error = bt_conn_get_info(conn, &info);
    if (info_error != 0) {
        LOG_WRN("Connection diagnostics unavailable: %d", info_error);
    } else if (info.type == BT_CONN_TYPE_LE) {
        if (info.le.phy != NULL) {
            LOG_DBG("LE PHY TX %u RX %u",
                    (unsigned int)info.le.phy->tx_phy,
                    (unsigned int)info.le.phy->rx_phy);
        }
        if (info.le.data_len != NULL) {
            LOG_DBG("LE data length TX %u RX %u",
                    (unsigned int)info.le.data_len->tx_max_len,
                    (unsigned int)info.le.data_len->rx_max_len);
        }
    }
    LOG_INF("Bluetooth connected; capture remains off until CCC subscribe");
}

static void transport_disconnected(
    struct bt_conn *conn,
    uint8_t reason)
{
    LOG_INF("Bluetooth disconnected: %u", reason);

    k_spinlock_key_t key = k_spin_lock(&connection_lock);
    struct bt_conn *old_connection = NULL;
    if (current_connection == conn) {
        old_connection = current_connection;
        current_connection = NULL;
        fresh_audio_ccc_connection = NULL;
        atomic_clear(&fresh_audio_ccc_authorized);
    }
    k_spin_unlock(&connection_lock, key);

    if (old_connection != NULL) {
        atomic_inc(&battery_epoch);
        request_audio_state(false, 0);
        (void)k_work_cancel_delayable(&battery_work);
        bt_conn_unref(old_connection);
        atomic_clear(&advertising_restart_attempts);
        (void)k_work_reschedule(
            &advertising_restart_work, K_NO_WAIT);
    }
}

static bool le_param_req(
    struct bt_conn *conn,
    struct bt_le_conn_param *param)
{
    ARG_UNUSED(conn);
    ARG_UNUSED(param);
    return true;
}

static struct bt_conn_cb connection_callbacks = {
    .connected = transport_connected,
    .disconnected = transport_disconnected,
    .le_param_req = le_param_req,
};

static bool write_to_tx_queue(const uint8_t *data, size_t size)
{
    if (data == NULL || size == 0u ||
        size > CODEC_OUTPUT_MAX_BYTES) {
        return false;
    }

    uint8_t record[
        CODEC_OUTPUT_MAX_BYTES + TX_RECORD_HEADER_BYTES] = {0};
    record[0] = (uint8_t)(size & 0xffu);
    record[1] = (uint8_t)((size >> 8u) & 0xffu);
    memcpy(record + TX_RECORD_HEADER_BYTES, data, size);

    k_spinlock_key_t key = k_spin_lock(&tx_ring_lock);
    if (ring_buf_space_get(&tx_ring_buf) < sizeof(record)) {
        k_spin_unlock(&tx_ring_lock, key);
        return false;
    }
    uint32_t written =
        ring_buf_put(&tx_ring_buf, record, sizeof(record));
    k_spin_unlock(&tx_ring_lock, key);
    if (written != sizeof(record)) {
        return false;
    }
    k_sem_give(&tx_data_ready);
    return true;
}

static bool read_from_tx_queue(
    uint8_t *frame,
    uint32_t *frame_size)
{
    uint8_t record[
        CODEC_OUTPUT_MAX_BYTES + TX_RECORD_HEADER_BYTES];
    k_spinlock_key_t key = k_spin_lock(&tx_ring_lock);
    uint32_t bytes_read =
        ring_buf_get(&tx_ring_buf, record, sizeof(record));
    k_spin_unlock(&tx_ring_lock, key);
    if (bytes_read == 0u) {
        return false;
    }
    if (bytes_read != sizeof(record)) {
        LOG_ERR("Audio queue returned a partial record: %u",
                (unsigned int)bytes_read);
        return false;
    }

    uint32_t size =
        (uint32_t)record[0] |
        ((uint32_t)record[1] << 8u);
    if (size == 0u || size > CODEC_OUTPUT_MAX_BYTES) {
        LOG_ERR("Audio queue contained invalid frame size: %u",
                (unsigned int)size);
        return false;
    }
    memcpy(frame, record + TX_RECORD_HEADER_BYTES, size);
    *frame_size = size;
    return true;
}

static int notify_with_bounded_retry(
    struct bt_conn *conn,
    const void *data,
    uint16_t len)
{
    int err = -ENOTCONN;
    for (uint8_t attempt = 0u;
         attempt < AUDIO_NOTIFY_RETRY_LIMIT;
         attempt++) {
        /*
         * Pinned Zephyr's explicit-connection notify path does not consult
         * the managed CCC match callback. Recheck current-connection identity,
         * fresh per-connection consent, and live subscription at every send
         * attempt so revocation cannot leak a retry notification.
         */
        if (!transport_audio_is_active()) {
            return -ECANCELED;
        }
        if (!audio_capture_authorized(conn)) {
            return -EACCES;
        }

        err = bt_gatt_notify(
            conn,
            &audio_service.attrs[AUDIO_VALUE_ATTRIBUTE_INDEX],
            data,
            len);
        if (err == 0) {
            return 0;
        }
        if (err != -EAGAIN && err != -ENOMEM) {
            return err;
        }
        if (attempt + 1u < AUDIO_NOTIFY_RETRY_LIMIT) {
            k_sleep(K_MSEC(AUDIO_NOTIFY_RETRY_DELAY_MS));
        }
    }
    return err;
}

struct audio_tx_state {
    bool pending;
    uint32_t frame_size;
    uint8_t frame[CODEC_OUTPUT_MAX_BYTES];
    struct transport_fragment_state fragment;
    atomic_val_t epoch;
};

static void reset_local_tx_state(
    struct audio_tx_state *state,
    atomic_val_t epoch)
{
    state->pending = false;
    state->frame_size = 0u;
    state->fragment.offset = 0u;
    state->fragment.fragment_index = 0u;
    state->epoch = epoch;
    memset(state->frame, 0, sizeof(state->frame));
}

static int send_next_fragment(
    struct bt_conn *conn,
    struct audio_tx_state *state)
{
    if (!audio_capture_authorized(conn)) {
        return -EACCES;
    }

    uint16_t att_mtu = bt_gatt_get_mtu(conn);
    size_t payload_bytes;
    int err = transport_fragment_plan(
        att_mtu,
        state->frame_size,
        &state->fragment,
        &payload_bytes);
    if (err != 0) {
        return err;
    }

    uint8_t notification[
        CODEC_OUTPUT_MAX_BYTES + TRANSPORT_AUDIO_HEADER_BYTES];
    notification[0] =
        (uint8_t)(state->fragment.sequence & 0xffu);
    notification[1] =
        (uint8_t)((state->fragment.sequence >> 8u) & 0xffu);
    notification[2] = state->fragment.fragment_index;
    memcpy(
        notification + TRANSPORT_AUDIO_HEADER_BYTES,
        state->frame + state->fragment.offset,
        payload_bytes);

    size_t notification_bytes =
        payload_bytes + TRANSPORT_AUDIO_HEADER_BYTES;
    err = notify_with_bounded_retry(
        conn, notification, (uint16_t)notification_bytes);

    struct transport_fragment_state next;
    int commit_error = transport_fragment_commit(
        &state->fragment, payload_bytes, err, &next);
    if (commit_error != 0) {
        return commit_error;
    }
    state->fragment = next;
    if (state->fragment.offset == state->frame_size) {
        state->pending = false;
        state->frame_size = 0u;
        state->fragment.offset = 0u;
        state->fragment.fragment_index = 0u;
        memset(state->frame, 0, sizeof(state->frame));
    }
    return 0;
}

K_THREAD_STACK_DEFINE(pusher_stack, 4096);
static struct k_thread pusher_thread;

static void pusher(void *unused1, void *unused2, void *unused3)
{
    ARG_UNUSED(unused1);
    ARG_UNUSED(unused2);
    ARG_UNUSED(unused3);

    struct audio_tx_state state = {0};
    state.epoch = atomic_get(&audio_epoch);

    while (true) {
        (void)k_sem_take(&tx_data_ready, K_FOREVER);
        atomic_val_t wake_epoch = atomic_get(&audio_epoch);
        if (state.epoch != wake_epoch) {
            reset_local_tx_state(&state, wake_epoch);
        }
        while (transport_audio_is_active()) {
            atomic_val_t epoch = atomic_get(&audio_epoch);
            if (state.epoch != epoch) {
                reset_local_tx_state(&state, epoch);
            }
            if (!state.pending) {
                if (!read_from_tx_queue(
                        state.frame, &state.frame_size)) {
                    break;
                }
                state.pending = true;
            }

            struct bt_conn *conn = acquire_current_connection();
            if (conn == NULL) {
                break;
            }
            if (!audio_capture_authorized(conn)) {
                bt_conn_unref(conn);
                transport_audio_fault(-EACCES);
                break;
            }

            int err = send_next_fragment(conn, &state);
            bt_conn_unref(conn);
            if (err != 0) {
                /*
                 * send_next_fragment commits offset/sequence only after a
                 * successful notification. A fatal or exhausted retry stops
                 * capture and zeroes both queues.
                 */
                transport_audio_fault(err);
                break;
            }
        }
    }
}

int broadcast_audio_packets(uint8_t *buffer, size_t size)
{
    if (!transport_audio_is_active()) {
        return -ECANCELED;
    }
    if (!write_to_tx_queue(buffer, size)) {
        return -ENOSPC;
    }
    return 0;
}

static int initialize_battery_service(void)
{
    int err = battery_init();
    if (err != 0) {
        return err;
    }
    err = battery_charge_start();
    if (err != 0) {
        return err;
    }

    uint16_t battery_millivolt;
    uint8_t battery_percentage;
    err = battery_get_millivolt(&battery_millivolt);
    if (err != 0) {
        return err;
    }
    err = battery_get_percentage(
        &battery_percentage, battery_millivolt);
    if (err != 0) {
        return err;
    }
    return bt_bas_set_battery_level(battery_percentage);
}

int transport_start(void)
{
    ring_buf_init(&tx_ring_buf, sizeof(tx_queue), tx_queue);
    k_thread_create(
        &audio_control_thread,
        audio_control_stack,
        K_THREAD_STACK_SIZEOF(audio_control_stack),
        audio_control,
        NULL,
        NULL,
        NULL,
        K_PRIO_PREEMPT(6),
        0,
        K_NO_WAIT);
    k_thread_create(
        &pusher_thread,
        pusher_stack,
        K_THREAD_STACK_SIZEOF(pusher_stack),
        pusher,
        NULL,
        NULL,
        NULL,
        K_PRIO_PREEMPT(7),
        0,
        K_NO_WAIT);

    bt_conn_cb_register(&connection_callbacks);

    /*
     * Pinned Zephyr permits a dynamic service registration before bt_enable,
     * or after settings_load, but not between them. Register first so its CCC
     * slots exist when persistent settings are loaded.
     */
    int err = bt_gatt_service_register(&audio_service);
    if (err != 0) {
        LOG_ERR("Audio service registration failed: %d", err);
        return err;
    }

    /*
     * Register the legacy DFU service inside the same pre-bt_enable window as
     * the audio service, for the same pinned-Zephyr reason: dynamic service
     * registration is permitted before bt_enable or after settings_load, but
     * not between them, and its CCC slot must exist before settings_load runs.
     *
     * A failure here is NOT fatal. The wireless hatch is one of two; the cable
     * hatch (recovery_usb.c, GPREGRET 0x57) is already running by this point.
     * Refusing to boot would remove both hatches at once, which is precisely
     * the lockout this image exists to prevent.
     */
    int dfu_error = bt_gatt_service_register(&dfu_service);
    if (dfu_error != 0) {
        LOG_ERR("Legacy DFU service registration failed; wireless recovery "
                "unavailable, cable recovery unaffected: %d", dfu_error);
    } else {
        LOG_INF("Legacy DFU service registered (control point is open)");
    }

    err = bt_enable(NULL);
    if (err != 0) {
        LOG_ERR("Bluetooth initialization failed: %d", err);
        return err;
    }

    err = settings_load();
    if (err != 0) {
        LOG_ERR("Bond/settings load failed: %d", err);
        return err;
    }

    battery_ready = false;
    err = initialize_battery_service();
    if (err != 0) {
        LOG_ERR("Battery service initialization failed: %d", err);
        return err;
    }
    battery_ready = true;

    /*
     * All startup gates have passed. Publish readiness before the controller
     * starts advertising so an immediate connect/disconnect callback cannot
     * lose its restart request.
     */
    atomic_set(&transport_ready, 1);
    err = bt_le_adv_start(
        BT_LE_ADV_CONN,
        advertising_data,
        ARRAY_SIZE(advertising_data),
        scan_response_data,
        ARRAY_SIZE(scan_response_data));
    if (err != 0) {
        /*
         * Report startup failure to the caller, but keep the fully initialized
         * transport eligible for the same indefinite recovery used after a
         * disconnect. Exiting main does not stop Zephyr system workqueues.
         */
        LOG_ERR("Initial advertising failed; recovery scheduled: %d", err);
        atomic_clear(&advertising_restart_attempts);
        (void)k_work_reschedule(
            &advertising_restart_work,
            K_MSEC(ADVERTISING_RESTART_DELAY_MS));
        return err;
    }

    LOG_INF("Advertising live audio + Battery Service");
    return 0;
}
