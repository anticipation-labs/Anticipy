#!/usr/bin/env python3
"""Deterministic source checks for the D7/D0 one-owner live candidate."""

from pathlib import Path


ROOT = Path(__file__).resolve().parent


def read(relative: str) -> str:
    return (ROOT / relative).read_text()


def function_body(source: str, name: str) -> str:
    search_from = 0
    while True:
        start = source.index(name, search_from)
        brace = source.index("{", start)
        semicolon = source.find(";", start, brace)
        if semicolon < 0:
            break
        search_from = semicolon + 1

    depth = 0
    for end in range(brace, len(source)):
        if source[end] == "{":
            depth += 1
        elif source[end] == "}":
            depth -= 1
            if depth == 0:
                return source[start : end + 1]
    raise AssertionError(f"unterminated function: {name}")


def check_candidate_configuration() -> None:
    conf = read("candidate_live_button_haptic.conf")
    assert "CONFIG_BT_FILTER_ACCEPT_LIST=y" in conf
    assert "CONFIG_OMI_ENABLE_BUTTON=y" in conf
    assert "CONFIG_OMI_ENABLE_HAPTIC=y" in conf
    assert "CONFIG_OMI_ENABLE_OFFLINE_STORAGE=n" in conf
    assert "CONFIG_SPI=n" in conf
    assert 'CONFIG_BT_DIS_FW_REV_STR="0.9.3-wed-live-bh-owner2"' in conf


def check_owner_policy() -> None:
    transport = read("src/transport.c")
    button = read("src/button.c")

    for contract in (
        "bt_foreach_bond(BT_ID_DEFAULT",
        "bt_le_filter_accept_list_clear()",
        "bt_le_filter_accept_list_add(&scan.first)",
        "BT_LE_ADV_OPT_FILTER_CONN",
        "bt_conn_auth_info_cb_register(&owner_auth_callbacks)",
        "transport_peer_is_authorized(conn)",
        "OWNER_PROVISIONING_TIMEOUT_SECONDS 120",
        "button_take_factory_reset_request()",
        "button_take_provisioning_request()",
    ):
        assert contract in transport

    pairing = function_body(transport, "static void owner_pairing_complete")
    assert "k_work_submit(&owner_commit_work)" in pairing
    assert "refresh_owner_filter()" not in pairing

    commit = function_body(transport, "static void owner_commit_handler")
    assert "refresh_owner_filter()" in commit
    assert "atomic_set(&advertising_desired, 1)" in commit

    prepare = function_body(transport, "static int prepare_owner_policy")
    assert "atomic_set(&provisioning_open, 1)" in prepare
    assert "Virgin BLE provisioning window opened" in prepare

    assert "OWNER_PROVISION_HOLD_MS 3000" in button
    assert "OWNER_FACTORY_RESET_HOLD_MS 10000" in button
    assert "sample_owner_boot_gesture();" in button
    assert "boot_gesture_consumed" in button


def check_owner_data_boundary() -> None:
    transport = read("src/transport.c")
    button = read("src/button.c")
    haptic = read("src/haptic.c")
    storage = read("src/storage.c")

    assert transport.count("BT_ATT_ERR_AUTHORIZATION") >= 4
    pusher = function_body(transport, "void pusher")
    assert "!transport_peer_is_authorized(conn)" in pusher

    assert "if (!transport_peer_is_authorized(conn))" in button
    assert button.count("&button_service.attrs[2]") == 5
    assert "&button_service.attrs[1]" not in button

    assert "if (!transport_peer_is_authorized(conn))" in haptic
    assert "notify_storage_owner" in storage
    assert "return bt_gatt_notify(conn, &storage_service.attrs[2]" in storage
    assert "bool conn_authorized = transport_peer_is_authorized(conn);" in storage
    assert "if (remaining_length > 0 && conn_authorized)" in storage


def check_shutdown_and_frame_boundary() -> None:
    transport = read("src/transport.c")
    mic = read("src/mic.c")

    assert "data == NULL || size == 0U || size > CODEC_OUTPUT_MAX_BYTES" in transport
    assert "buffer == NULL || size == 0U || size > CODEC_OUTPUT_MAX_BYTES" in transport
    assert "tx_buffer_size == 0U" in transport

    shutdown = function_body(transport, "int bt_off")
    assert shutdown.index("mic_off();") < shutdown.index("k_sem_count_get(&tx_data_ready)")
    assert shutdown.index("flush_partial_storage_record()") < shutdown.index("bt_disable()")
    assert "atomic_get(&pusher_busy)" in shutdown

    assert "_capture_enabled = false;" in mic
    assert "nrfx_pdm_stop()" in mic
    assert "if (!_pdm_initialized)" in mic

    factory = function_body(transport, "static int prepare_owner_policy")
    assert "bt_unpair(BT_ID_DEFAULT, BT_ADDR_LE_ANY)" in factory
    assert "transport_clear_offline_audio()" in factory
    assert "return reset_err;" in factory


def main() -> None:
    check_candidate_configuration()
    check_owner_policy()
    check_owner_data_boundary()
    check_shutdown_and_frame_boundary()
    print("PASS: virgin commissioning plus D7/D0 recovery enables the one-owner controller filter")
    print("PASS: first-bond commit runs outside the Bluetooth pairing callback")
    print("PASS: audio, DFU, button, haptic, and backlog paths require the owner")
    print("PASS: shutdown quiesces PDM/queue before commit and rejects zero frames")
    print("HARDWARE GATE: provision, reboot, reconnect, reject a second phone, then factory-reset")


if __name__ == "__main__":
    main()
