#include <zephyr/logging/log.h>
#include <zephyr/drivers/gpio.h>
#include "led.h"
#include "utils.h"

LOG_MODULE_REGISTER(led, CONFIG_LOG_DEFAULT_LEVEL);

int led_start(void)
{
    ASSERT_TRUE(gpio_is_ready_dt(&led_red));
    ASSERT_OK(gpio_pin_configure_dt(&led_red, GPIO_OUTPUT_INACTIVE));
    ASSERT_TRUE(gpio_is_ready_dt(&led_green));
    ASSERT_OK(gpio_pin_configure_dt(&led_green, GPIO_OUTPUT_INACTIVE));
    ASSERT_TRUE(gpio_is_ready_dt(&led_blue));
    ASSERT_OK(gpio_pin_configure_dt(&led_blue, GPIO_OUTPUT_INACTIVE));
    LOG_INF("LEDs started");
    return 0;
}

int set_led_red(bool on)
{
    return gpio_pin_set_dt(&led_red, on);
}

int set_led_green(bool on)
{
    return gpio_pin_set_dt(&led_green, on);
}

int set_led_blue(bool on)
{
    return gpio_pin_set_dt(&led_blue, on);
}
