"""Regression proof for the live extension gate's 2026-08-31 false pass.

Both Chrome folders had a current agent_loop.js, so the old one-file gate
passed even though manifest.json and background.js were stale and
setup_bridge.js was absent. Fresh pairing could not work in that state.
"""

from overnight._extension_package import (
    anticipy_record_state,
    compare_package_tree,
)


PACKAGE = {
    "manifest.json": b'{"version":"0.11.1"}',
    "agent_loop.js": b"current loop",
    "background.js": b"current worker",
    "setup_bridge.js": b"current setup bridge",
}


def test_a_current_representative_file_cannot_hide_the_stale_worker(tmp_path):
    (tmp_path / "manifest.json").write_bytes(b'{"version":"0.11.0"}')
    (tmp_path / "agent_loop.js").write_bytes(PACKAGE["agent_loop.js"])
    (tmp_path / "background.js").write_bytes(b"old worker")

    differences = compare_package_tree(PACKAGE, str(tmp_path))

    assert "agent_loop.js" not in differences
    assert "manifest.json" in differences
    assert "background.js" in differences
    assert "missing setup_bridge.js" in differences


def test_every_packaged_file_must_match(tmp_path):
    for name, data in PACKAGE.items():
        (tmp_path / name).write_bytes(data)

    assert compare_package_tree(PACKAGE, str(tmp_path)) == []


def test_an_unreadable_package_fails_closed(tmp_path):
    assert compare_package_tree({}, str(tmp_path)) == [
        "package contains no readable files"
    ]


def test_package_paths_cannot_escape_the_tree(tmp_path):
    assert compare_package_tree({"../outside.js": b"x"}, str(tmp_path)) == [
        "unsafe package path ../outside.js"
    ]


def test_a_removed_chrome_record_is_not_an_installed_agent():
    tombstone = {
        "path": "/Users/person/Desktop/anticipy-extension-0.11",
        "disable_reasons": [1, 16777216],
    }
    assert anticipy_record_state(tombstone) is None


def test_enabled_and_disabled_installs_require_a_real_manifest():
    enabled = {"manifest": {"name": "Anticipy"}, "disable_reasons": []}
    disabled = {"manifest": {"name": "Anticipy"}, "disable_reasons": [1]}
    assert anticipy_record_state(enabled) == "enabled"
    assert anticipy_record_state(disabled) == "disabled"
