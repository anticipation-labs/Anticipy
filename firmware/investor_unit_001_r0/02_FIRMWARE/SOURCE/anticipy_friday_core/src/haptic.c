#include "haptic.h"

#include <errno.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

#include "transport.h"

LOG_MODULE_REGISTER(haptic, CONFIG_LOG_DEFAULT_LEVEL);

#define ANTICIPY_HAPTIC_NODE DT_ALIAS(anticipy_haptic)
#if !DT_NODE_HAS_STATUS(ANTICIPY_HAPTIC_NODE, okay)
#error "Anticipy haptic alias is missing or disabled"
#endif

#define MAX_HAPTIC_DURATION_MS 1000U

static const struct gpio_dt_spec haptic_pin = GPIO_DT_SPEC_GET(ANTICIPY_HAPTIC_NODE, gpios);

static void haptic_timer_handler(struct k_timer *timer);
K_TIMER_DEFINE(haptic_timer, haptic_timer_handler, NULL);

static struct bt_uuid_128 haptic_service_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0xCAB1AB95, 0x2EA5, 0x4F4D, 0xBB56, 0x874B72CFC984));
static struct bt_uuid_128 haptic_command_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0xCAB1AB96, 0x2EA5, 0x4F4D, 0xBB56, 0x874B72CFC984));

static ssize_t haptic_write(struct bt_conn *conn,
                            const struct bt_gatt_attr *attr,
                            const void *buf,
                            uint16_t len,
                            uint16_t offset,
                            uint8_t flags)
{
    if (!transport_peer_is_authorized(conn)) {
        return BT_GATT_ERR(BT_ATT_ERR_AUTHORIZATION);
    }

    if (offset != 0U || len != 1U) {
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN);
    }

    switch (((const uint8_t *) buf)[0]) {
    case 1:
        haptic_play_ms(20U);
        break;
    case 2:
        haptic_play_ms(50U);
        break;
    case 3:
        haptic_play_ms(250U);
        break;
    default:
        return BT_GATT_ERR(BT_ATT_ERR_VALUE_NOT_ALLOWED);
    }

    return len;
}

static struct bt_gatt_attr haptic_attrs[] = {
    BT_GATT_PRIMARY_SERVICE(&haptic_service_uuid),
    BT_GATT_CHARACTERISTIC(&haptic_command_uuid.uuid,
                           BT_GATT_CHRC_WRITE,
                           BT_GATT_PERM_WRITE_ENCRYPT,
                           NULL,
                           haptic_write,
                           NULL),
};

static struct bt_gatt_service haptic_service = BT_GATT_SERVICE(haptic_attrs);

static void haptic_timer_handler(struct k_timer *timer)
{
    ARG_UNUSED(timer);
    (void) gpio_pin_set_dt(&haptic_pin, 0);
}

int haptic_init(void)
{
    if (!gpio_is_ready_dt(&haptic_pin)) {
        return -ENODEV;
    }

    return gpio_pin_configure_dt(&haptic_pin, GPIO_OUTPUT_INACTIVE);
}

void haptic_play_ms(uint32_t duration_ms)
{
    if (duration_ms == 0U || duration_ms > MAX_HAPTIC_DURATION_MS) {
        return;
    }

    (void) gpio_pin_set_dt(&haptic_pin, 1);
    k_timer_start(&haptic_timer, K_MSEC(duration_ms), K_NO_WAIT);
}

void haptic_off(void)
{
    k_timer_stop(&haptic_timer);
    (void) gpio_pin_set_dt(&haptic_pin, 0);
}

void register_haptic_service(void)
{
    bt_gatt_service_register(&haptic_service);
}
