#!/usr/bin/env python3
"""Deterministic source checks for the Anticipy Unit 001 live core.

These checks intentionally cover only contracts visible in source. They do
not prove compilation, board behavior, battery safety, radio performance, or
enclosure fit.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parent


def read(relative: str) -> str:
    return (ROOT / relative).read_text()


def check_charge_current_contract() -> None:
    main = read("src/main.c")
    battery = read("src/lib/battery/battery.c")

    assert "#define GPIO_BATTERY_CHARGE_CURRENT 13" in battery
    assert "GPIO_BATTERY_CHARGE_CURRENT, GPIO_OUTPUT_HIGH" in battery
    assert "GPIO_BATTERY_CHARGE_CURRENT, 1" in battery
    assert "GPIO_BATTERY_CHARGE_CURRENT, 0" in battery
    assert "GPIO_BATTERY_READ_ENABLE, GPIO_OUTPUT_LOW" in battery
    assert "GPIO_BATTERY_READ_ENABLE, 0" in battery

    # The application must remove its deliberate three-second LED delay from
    # the unsafe side of charge-current initialization.
    assert main.index("err = battery_init();") < main.index("boot_led_sequence();")
    assert "factory bootloader still runs" in main


def check_friday_feature_contract() -> None:
    conf = read("prj_xiao_ble_sense_devkitv2-adafruit.conf")
    cmake = read("CMakeLists.txt")
    main = read("src/main.c")
    transport = read("src/transport.c")

    assert 'CONFIG_BT_DEVICE_NAME="Anticipy Friday Core"' in conf
    assert 'CONFIG_BT_DIS_FW_REV_STR="0.9.2-friday-core"' in conf
    assert "CONFIG_OMI_ENABLE_BATTERY=y" in conf
    assert "CONFIG_OMI_ENABLE_OFFLINE_STORAGE=n" in conf
    assert "CONFIG_OMI_ENABLE_BUTTON=n" in conf
    assert "CONFIG_OMI_ENABLE_HAPTIC=n" in conf
    assert "CONFIG_OMI_ENABLE_USB=n" in conf
    assert "CONFIG_DISK_ACCESS=n" in conf
    assert "CONFIG_FILE_SYSTEM=n" in conf
    assert "CONFIG_FAT_FILESYSTEM_ELM=n" in conf
    assert "#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE" in main
    assert "#ifdef CONFIG_OMI_ENABLE_BUTTON" in main
    assert "#ifdef CONFIG_OMI_ENABLE_HAPTIC" in main
    assert "if(CONFIG_OMI_ENABLE_OFFLINE_STORAGE)" in cmake
    assert "target_sources(app PRIVATE src/storage.c)" in cmake
    assert "if(CONFIG_OMI_OFFLINE_STORAGE_QSPI)" in cmake
    assert "target_sources(app PRIVATE src/qspi_backlog.c)" in cmake
    assert "target_sources(app PRIVATE src/sdcard.c)" in cmake
    assert (
        "target_sources_ifdef(CONFIG_OMI_ENABLE_BUTTON app PRIVATE\n"
        "    src/button.c\n"
        ")"
    ) in cmake
    assert (
        "target_sources_ifdef(CONFIG_OMI_ENABLE_HAPTIC app PRIVATE\n"
        "    src/haptic.c\n"
        ")"
    ) in cmake

    # Every storage-service registration must sit inside the offline feature's
    # compile-time guard, not merely behind a runtime flag.
    guard_stack: list[str] = []
    registration_count = 0
    for line in transport.splitlines():
        stripped = line.strip()
        if stripped.startswith("#ifdef "):
            guard_stack.append(stripped.removeprefix("#ifdef "))
        elif stripped == "#endif":
            assert guard_stack
            guard_stack.pop()
        if "bt_gatt_service_register(&storage_service)" in line:
            registration_count += 1
            assert "CONFIG_OMI_ENABLE_OFFLINE_STORAGE" in guard_stack
    assert registration_count == 2


def check_runtime_hardening_contract() -> None:
    conf = read("prj_xiao_ble_sense_devkitv2-adafruit.conf")
    cmake = read("CMakeLists.txt")
    main = read("src/main.c")
    transport = read("src/transport.c")
    watchdog = read("src/wdog_facade.c")

    assert "#define WATCHDOG_TIMEOUT_MS 900000U" in watchdog
    assert "static bool watchdog_running;" in watchdog
    assert main.index("err = watchdog_init();") > main.index("err = mic_start();")
    assert main.index("err = watchdog_init();") < main.index("while (1)")
    assert "CONFIG_BT_CTLR_ASSERT_HANDLER=y" in conf
    assert "CONFIG_REBOOT=y" in conf
    assert "sys_reboot(SYS_REBOOT_COLD);" in main

    assert "K_SEM_DEFINE(tx_data_ready, 0, NETWORK_RING_BUF_SIZE);" in transport
    assert "k_sem_take(&tx_data_ready, K_FOREVER)" in transport
    assert "k_sem_give(&tx_data_ready);" in transport
    assert "k_yield();" not in transport
    assert "k_work_cancel_delayable(&battery_work)" in transport
    assert "Failed to restart advertising" in transport
    assert "Drop every frame whose ready token predates" in transport
    assert "k_sem_take(&tx_data_ready, K_NO_WAIT)" in transport

    # Feed immediately before either jump into the inherited bootloader.
    assert transport.count("watchdog_feed();") == 2
    assert transport.count("watchdog_feed();\n        NRF_POWER->GPREGRET = 0xA8;") == 2

    # USB recovery was intentionally not pulled into the Friday image.  The
    # encrypted BLE DFU service remains its only software recovery hatch.
    assert "CONFIG_USB_DEVICE_STACK=n" in conf
    assert "CONFIG_SERIAL=n" in conf
    assert "recovery_usb" not in cmake
    assert "recovery_touch" not in cmake


def check_audio_and_ble_contract() -> None:
    conf = read("prj_xiao_ble_sense_devkitv2-adafruit.conf")
    config_h = read("src/config.h")
    transport = read("src/transport.c")
    ios_client = read("ios_test_client/AnticipyBLEClient.swift")

    assert "CONFIG_OMI_CODEC_OPUS=y" in conf
    assert "#define CODEC_OPUS_BITRATE 16000" in config_h
    assert "#define CODEC_OPUS_VBR 0" in config_h
    assert "#define CODEC_ID 20" in config_h
    assert "CONFIG_BT_SMP=y" in conf
    assert "CONFIG_BT_SMP_SC_PAIR_ONLY=y" in conf
    assert "CONFIG_BT_SETTINGS=y" in conf
    assert "bt_conn_set_security(conn, BT_SECURITY_L2)" in transport
    assert "settings_load()" in transport
    assert "BT_GATT_PERM_READ_ENCRYPT" in transport
    assert "BT_GATT_PERM_WRITE_ENCRYPT" in transport
    assert "bt_gatt_notify(conn, &audio_service.attrs[2]" in transport
    assert "bt_gatt_is_subscribed(conn, &audio_service.attrs[2]" in transport
    assert "&audio_service.attrs[1]" not in transport
    assert "19B10000-E8F2-537E-4F6C-D104768A1214" in ios_client
    assert "19B10001-E8F2-537E-4F6C-D104768A1214" in ios_client
    assert "19B10002-E8F2-537E-4F6C-D104768A1214" in ios_client


def main() -> None:
    check_charge_current_contract()
    check_friday_feature_contract()
    check_audio_and_ble_contract()
    check_runtime_hardening_contract()
    print("PASS: P0.13 is configured HIGH before the deliberate LED delay")
    print("PASS: battery divider remains LOW-enabled for ADC reads")
    print("PASS: Friday storage is excluded at compile time; button, haptic, and USB are disabled")
    print("PASS: BLE name, version, L2 encryption, optional bonding, and Opus codec contracts match")
    print("PASS: pusher blocks, reconnect advertising restarts, and stale audio is dropped")
    print("PASS: watchdog/BT assert recovery contracts are source-verified")
    print("HARDWARE GATE: measure charge current from USB insertion through steady state")
    print("HARDWARE GATE: validate battery rating, polarity, finished size, and qualification fit")


if __name__ == "__main__":
    main()
