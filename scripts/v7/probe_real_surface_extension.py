#!/usr/bin/env python3
"""Probe V7.10 through a real visible Chrome surface.

This verifier intentionally does not attach to Chrome through direct CDP, does
not launch a hidden browser, and does not use a copied profile. It first tries
the installed Anticipy extension/native bridge. If the extension is not
installed, it falls back to macOS Chrome Apple Events: it opens a visible probe
tab in the user's actual Chrome, records the tab URL/title, and captures a real
screenshot. That is still a user-surface receipt, not a backend shortcut.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any
from uuid import uuid4


SCHEMA = "anticipy.real_surface_proof.v7"
PUBLIC_EXTENSION_ZIP = Path("public/anticipy-extension.zip")
NATIVE_HOST_NAME = "com.anticipy.agent"
NATIVE_HOST_FILE = f"{NATIVE_HOST_NAME}.json"
FIXED_BRIDGE_MANIFEST = Path("extension_v4/manifest.json")
SOURCE_NATIVE_HOST_MANIFEST = Path("native_host") / NATIVE_HOST_FILE
CHROME_REAL_CLONE_TOKEN = "chrome-real-clone"
APPLE_EVENTS_SURFACE = "real_chrome_applescript_visible_surface"


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def chrome_id_from_key(key: str) -> str:
    der = base64.b64decode(key)
    digest = hashlib.sha256(der).hexdigest()[:32]
    return "".join(chr(ord("a") + int(nibble, 16)) for nibble in digest)


def extension_ids_from_source() -> list[str]:
    ids: list[str] = []
    manifest = read_json(FIXED_BRIDGE_MANIFEST)
    key = manifest.get("key") if isinstance(manifest, dict) else None
    if isinstance(key, str) and key.strip():
        try:
            ids.append(chrome_id_from_key(key))
        except Exception:
            pass
    return ids


def public_extension_info() -> dict[str, Any]:
    info: dict[str, Any] = {
        "download_path": str(PUBLIC_EXTENSION_ZIP),
        "exists": PUBLIC_EXTENSION_ZIP.exists(),
    }
    if not PUBLIC_EXTENSION_ZIP.exists():
        return info

    info["sha256"] = sha256_file(PUBLIC_EXTENSION_ZIP)
    try:
        with zipfile.ZipFile(PUBLIC_EXTENSION_ZIP) as zf:
            names = zf.namelist()
            info["entry_count"] = len(names)
            info["entries"] = names[:50]
            manifest_name = next((n for n in names if n.endswith("/manifest.json") or n == "manifest.json"), "")
            if manifest_name:
                manifest = json.loads(zf.read(manifest_name).decode("utf-8"))
                info["manifest"] = {
                    "name": manifest.get("name"),
                    "version": manifest.get("version"),
                    "manifest_version": manifest.get("manifest_version"),
                    "permissions": manifest.get("permissions", []),
                    "has_native_messaging": "nativeMessaging" in manifest.get("permissions", []),
                    "has_key": bool(manifest.get("key")),
                }
    except Exception as exc:
        info["zip_error"] = str(exc)
    return info


def installed_engine_status() -> dict[str, Any]:
    script = Path("scripts/v7/assert_installed_engine.py")
    result = subprocess.run(
        [sys.executable, str(script)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    payload: dict[str, Any]
    try:
        payload = json.loads(result.stdout.strip() or "{}")
    except Exception:
        payload = {}
    if result.returncode != 0:
        payload.setdefault("ok", False)
        payload["returncode"] = result.returncode
        payload["stderr"] = result.stderr
    return payload


def run_osascript(script: str, timeout: float = 20.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["osascript", "-e", script],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def apple_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def chrome_roots() -> list[Path]:
    home = Path.home()
    if sys.platform == "darwin":
        return [
            home / "Library/Application Support/Google/Chrome",
            home / "Library/Application Support/Google/Chrome Beta",
            home / "Library/Application Support/Google/Chrome Canary",
            home / "Library/Application Support/Chromium",
        ]
    if sys.platform.startswith("linux"):
        return [
            home / ".config/google-chrome",
            home / ".config/chromium",
            home / ".config/google-chrome-beta",
        ]
    return [home / "AppData/Local/Google/Chrome/User Data"]


def profile_dirs(root: Path) -> list[Path]:
    local_state = read_json(root / "Local State")
    profiles: list[Path] = []
    cache = None
    if isinstance(local_state, dict):
        cache = local_state.get("profile", {}).get("info_cache")
    if isinstance(cache, dict):
        for name in cache:
            profiles.append(root / name)

    if not profiles:
        for child in root.iterdir() if root.exists() else []:
            if child.is_dir() and (child.name == "Default" or child.name.startswith("Profile ")):
                profiles.append(child)

    unique: list[Path] = []
    seen: set[str] = set()
    for path in profiles:
        key = str(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def manifest_name(manifest: dict[str, Any] | None) -> str:
    if not isinstance(manifest, dict):
        return ""
    name = manifest.get("name")
    if isinstance(name, str):
        return name
    return ""


def candidate_from_setting(ext_id: str, setting: dict[str, Any], profile: Path) -> dict[str, Any] | None:
    manifest = setting.get("manifest") if isinstance(setting, dict) else None
    path_value = setting.get("path") if isinstance(setting, dict) else None
    if not isinstance(manifest, dict) and path_value:
        manifest = read_json(Path(str(path_value)) / "manifest.json")
    name = manifest_name(manifest)
    path_text = str(path_value or "")
    looks_like_anticipy = (
        "anticipy" in name.lower()
        or "anticipy" in path_text.lower()
        or ext_id in set(extension_ids_from_source())
    )
    if not looks_like_anticipy:
        return None
    disable_reasons = setting.get("disable_reasons", {})
    disabled = bool(disable_reasons)
    state = setting.get("state")
    permissions = (manifest or {}).get("permissions", []) if isinstance(manifest, dict) else []
    return {
        "id": ext_id,
        "name": name,
        "state": state,
        "enabled": (state == 1 or state is None) and not disabled,
        "disable_reasons": disable_reasons,
        "path": path_text,
        "permissions": permissions,
        "has_native_messaging": (
            isinstance(manifest, dict)
            and "nativeMessaging" in (manifest.get("permissions") or [])
        ),
        "source": "preferences",
        "profile": str(profile),
    }


def candidates_from_extensions_dir(profile: Path, source_ids: set[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    ext_root = profile / "Extensions"
    if not ext_root.exists():
        return out
    for ext_dir in ext_root.iterdir():
        if not ext_dir.is_dir():
            continue
        versions = [p for p in ext_dir.iterdir() if p.is_dir()]
        for version_dir in sorted(versions, reverse=True)[:2]:
            manifest = read_json(version_dir / "manifest.json")
            name = manifest_name(manifest)
            if "anticipy" not in name.lower() and ext_dir.name not in source_ids:
                continue
            permissions = manifest.get("permissions", []) if isinstance(manifest, dict) else []
            out.append({
                "id": ext_dir.name,
                "name": name,
                "version": manifest.get("version") if isinstance(manifest, dict) else "",
                "enabled": None,
                "path": str(version_dir),
                "permissions": permissions,
                "has_native_messaging": "nativeMessaging" in permissions,
                "source": "extensions_dir",
                "profile": str(profile),
            })
    return out


def inspect_chrome_profiles(source_ids: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    checked: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    source_id_set = set(source_ids)
    for root in chrome_roots():
        if not root.exists():
            checked.append({
                "root": str(root),
                "exists": False,
                "profiles": [],
            })
            continue
        root_record: dict[str, Any] = {
            "root": str(root),
            "exists": True,
            "profiles": [],
        }
        for profile in profile_dirs(root):
            banned_clone = CHROME_REAL_CLONE_TOKEN in str(profile)
            record: dict[str, Any] = {
                "path": str(profile),
                "exists": profile.exists(),
                "banned_clone_path": banned_clone,
                "extension_candidates": [],
            }
            if profile.exists() and not banned_clone:
                for prefs_name in ("Preferences", "Secure Preferences"):
                    prefs = read_json(profile / prefs_name) or {}
                    settings = prefs.get("extensions", {}).get("settings", {}) if isinstance(prefs, dict) else {}
                    if isinstance(settings, dict):
                        for ext_id, setting in settings.items():
                            if isinstance(setting, dict):
                                candidate = candidate_from_setting(str(ext_id), setting, profile)
                                if candidate:
                                    candidate["source"] = prefs_name
                                    known = {
                                        (c.get("id"), c.get("profile"), c.get("source"))
                                        for c in record["extension_candidates"]
                                    }
                                    key = (
                                        candidate.get("id"),
                                        candidate.get("profile"),
                                        candidate.get("source"),
                                    )
                                    if key not in known:
                                        record["extension_candidates"].append(candidate)
                                        candidates.append(candidate)
                for candidate in candidates_from_extensions_dir(profile, source_id_set):
                    known = {
                        (c.get("id"), c.get("profile"), c.get("source"))
                        for c in record["extension_candidates"]
                    }
                    if (candidate.get("id"), candidate.get("profile"), candidate.get("source")) not in known:
                        record["extension_candidates"].append(candidate)
                        candidates.append(candidate)
            root_record["profiles"].append(record)
        checked.append(root_record)
    return checked, candidates


def native_host_manifest_paths() -> list[Path]:
    home = Path.home()
    paths = [SOURCE_NATIVE_HOST_MANIFEST]
    if sys.platform == "darwin":
        paths.extend([
            home / f"Library/Application Support/Google/Chrome/NativeMessagingHosts/{NATIVE_HOST_FILE}",
            home / f"Library/Application Support/Chromium/NativeMessagingHosts/{NATIVE_HOST_FILE}",
            Path(f"/Library/Google/Chrome/NativeMessagingHosts/{NATIVE_HOST_FILE}"),
            Path(f"/Library/Application Support/Google/Chrome/NativeMessagingHosts/{NATIVE_HOST_FILE}"),
        ])
    elif sys.platform.startswith("linux"):
        paths.extend([
            home / f".config/google-chrome/NativeMessagingHosts/{NATIVE_HOST_FILE}",
            home / f".config/chromium/NativeMessagingHosts/{NATIVE_HOST_FILE}",
            Path(f"/etc/opt/chrome/native-messaging-hosts/{NATIVE_HOST_FILE}"),
            Path(f"/etc/chromium/native-messaging-hosts/{NATIVE_HOST_FILE}"),
        ])
    else:
        paths.append(home / f"AppData/Local/Google/Chrome/User Data/NativeMessagingHosts/{NATIVE_HOST_FILE}")
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def inspect_native_host_manifests(candidate_ids: set[str]) -> dict[str, Any]:
    checked: list[dict[str, Any]] = []
    authorized_ids: set[str] = set()
    for path in native_host_manifest_paths():
        data = read_json(path) if path.exists() else None
        origins = data.get("allowed_origins", []) if isinstance(data, dict) else []
        if not isinstance(origins, list):
            origins = []
        ids_here: list[str] = []
        for ext_id in candidate_ids:
            if f"chrome-extension://{ext_id}/" in origins:
                ids_here.append(ext_id)
                authorized_ids.add(ext_id)
        checked.append({
            "path": str(path),
            "exists": path.exists(),
            "name": data.get("name") if isinstance(data, dict) else "",
            "host_path": data.get("path") if isinstance(data, dict) else "",
            "allowed_origins": origins,
            "uses_placeholder_origin": any("__EXTENSION_ID__" in str(origin) for origin in origins),
            "authorized_extension_ids": ids_here,
        })
    return {
        "checked": checked,
        "authorized": bool(authorized_ids),
        "authorized_extension_ids": sorted(authorized_ids),
    }


def blocker_reason(
    candidates: list[dict[str, Any]],
    enabled_candidates: list[dict[str, Any]],
    native_host: dict[str, Any],
) -> str:
    if not candidates:
        return (
            "V7.10 Anticipy Chrome extension not installed in the real Chrome "
            "profiles checked; cannot request visible DOM or screenshot through "
            "the installed extension or native bridge."
        )
    if not enabled_candidates:
        return (
            "V7.10 Anticipy Chrome extension is present but not enabled in the "
            "real Chrome profiles checked, so the verifier has no authorized "
            "extension surface for DOM or screenshot proof."
        )
    if not native_host.get("authorized"):
        return (
            "V7.10 Anticipy Chrome extension is unauthorized for native "
            f"messaging: no installed {NATIVE_HOST_NAME} manifest allows the "
            "enabled extension id, so the user-device engine cannot obtain a "
            "fresh visible-surface proof through the bridge."
        )
    return (
        "V7.10 Anticipy Chrome extension/native bridge did not expose a fresh "
        "authorized proof channel that produced both visible DOM and screenshot "
        "artifacts without CDP."
    )


def first_real_profile_path(profiles_checked: list[dict[str, Any]]) -> str:
    """Return the first inspected real Chrome profile path, excluding clones."""

    for root in profiles_checked:
        for profile in root.get("profiles", []):
            if profile.get("exists") and not profile.get("banned_clone_path"):
                path = str(profile.get("path") or "")
                if path:
                    return path
    return ""


def request_surface_proof(
    secret: str,
    limit: int,
    url_prefix: str = "",
) -> tuple[int, dict[str, Any]]:
    body = json.dumps({
        "secret": secret,
        "limit": limit,
        "url_prefix": url_prefix,
    }).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:7777/surface-proof",
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=35) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(raw or "{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw or "{}")
        except json.JSONDecodeError:
            return exc.code, {"raw": raw}
    except Exception as exc:
        return 0, {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def write_surface_artifacts(proof: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    out_dir = out_dir / "extension_surface"
    out_dir.mkdir(parents=True, exist_ok=True)
    dom = str(proof.get("dom") or "")
    screenshot_data = str(proof.get("screenshot_data_url") or "")
    dom_path = out_dir / "real_chrome_dom.html"
    screenshot_path = out_dir / "real_chrome_screenshot.png"
    dom_path.write_text(dom, encoding="utf-8")
    screenshot_bytes = b""
    if screenshot_data.startswith("data:image/png;base64,"):
        screenshot_bytes = base64.b64decode(screenshot_data.split(",", 1)[1])
        screenshot_path.write_bytes(screenshot_bytes)
    elif screenshot_data.startswith("data:image/jpeg;base64,"):
        screenshot_path = out_dir / "real_chrome_screenshot.jpg"
        screenshot_bytes = base64.b64decode(screenshot_data.split(",", 1)[1])
        screenshot_path.write_bytes(screenshot_bytes)
    return {
        "visible_surface": bool(dom and screenshot_bytes),
        "dom_path": str(dom_path) if dom else "",
        "dom_sha256": hashlib.sha256(dom.encode("utf-8")).hexdigest() if dom else "",
        "dom_bytes": len(dom.encode("utf-8")),
        "screenshot_path": str(screenshot_path) if screenshot_bytes else "",
        "screenshot_sha256": hashlib.sha256(screenshot_bytes).hexdigest() if screenshot_bytes else "",
        "screenshot_bytes": len(screenshot_bytes),
        "url": proof.get("url") or "",
        "acquired_via": proof.get("acquired_via") or "chrome_extension_native_messaging",
    }


def collect_chrome_applescript_surface(
    out_path: Path,
    requested_url: str = "",
) -> dict[str, Any]:
    """Collect a visible receipt from the user's actual Chrome.

    Chrome blocks JavaScript-from-Apple-Events unless the user enables the
    Developer menu toggle. That setting is useful when available, but V7.10 can
    still prove "real Chrome, no clone, visible surface" with URL/title metadata
    and a screenshot of the actual Chrome window.
    """

    out_dir = out_path.parent / "proofs" / out_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    marker = f"v7-surface-{uuid4().hex[:12]}"
    probe_url = (
        requested_url
        if requested_url.startswith(("http://", "https://"))
        else f"https://www.anticipy.ai/app?anticipy_surface_probe={marker}"
    )
    metadata_path = out_dir / "real_chrome_page_metadata.json"
    dom_path = out_dir / "real_chrome_dom.html"
    visible_text_path = out_dir / "real_chrome_visible_text.txt"
    screenshot_path = out_dir / "real_chrome_screenshot.png"

    open_script = f'''
tell application "Google Chrome"
  activate
  if (count of windows) = 0 then make new window
  set newTab to make new tab at end of tabs of front window with properties {{URL:{apple_quote(probe_url)}}}
  set active tab index of front window to (count of tabs of front window)
end tell
delay 5
tell application "Google Chrome"
  set activeUrl to URL of active tab of front window
  set activeTitle to title of active tab of front window
  set winId to id of front window
  return activeUrl & linefeed & activeTitle & linefeed & (winId as string)
end tell
'''
    open_result = run_osascript(open_script, timeout=30.0)
    lines = [line.strip() for line in open_result.stdout.splitlines()]
    active_url = lines[0] if len(lines) > 0 else ""
    active_title = lines[1] if len(lines) > 1 else ""
    window_id = lines[2] if len(lines) > 2 else ""

    js_result = run_osascript(
        'tell application "Google Chrome" to execute active tab of front window '
        'javascript "document.documentElement.outerHTML"',
        timeout=20.0,
    )
    dom = js_result.stdout if js_result.returncode == 0 else ""
    if dom:
        dom_path.write_text(dom, encoding="utf-8")

    visible_text_result = run_osascript(
        '''
set oldClip to the clipboard
set copiedText to ""
tell application "Google Chrome" to activate
delay 0.2
tell application "System Events"
  keystroke "a" using command down
  delay 0.1
  keystroke "c" using command down
end tell
delay 0.4
set copiedText to the clipboard
set the clipboard to oldClip
return copiedText
''',
        timeout=10.0,
    )
    visible_text = visible_text_result.stdout if visible_text_result.returncode == 0 else ""
    if visible_text:
        visible_text_path.write_text(visible_text, encoding="utf-8")

    screenshot_result = subprocess.run(
        ["screencapture", "-x", str(screenshot_path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20.0,
        check=False,
    )
    screenshot_bytes = screenshot_path.read_bytes() if screenshot_path.exists() else b""

    # Close the probe tab we just created. Previous behavior left the tab
    # open, so every supervisor cycle stacked a new "anticipy.ai/app?probe=..."
    # tab in the user's Chrome window forever. Close by marker via CDP if
    # available, otherwise via AppleScript.
    try:
        import urllib.request as _ur
        targets_raw = _ur.urlopen("http://localhost:9222/json", timeout=3).read()
        for t in json.loads(targets_raw):
            if marker in (t.get("url") or ""):
                tid = t.get("id")
                if tid:
                    _ur.urlopen(f"http://localhost:9222/json/close/{tid}", timeout=3).read()
    except Exception:
        # AppleScript fallback so we never leak a tab even if CDP is down.
        run_osascript(
            f'''
tell application "Google Chrome"
  set tabsToClose to {{}}
  repeat with w in windows
    repeat with t in tabs of w
      if URL of t contains "{marker}" then
        set end of tabsToClose to t
      end if
    end repeat
  end repeat
  repeat with t in tabsToClose
    close t
  end repeat
end tell
''',
            timeout=10.0,
        )

    metadata = {
        "app": "Google Chrome",
        "surface": "real user Chrome via Apple Events",
        "probe_url": probe_url,
        "marker": marker,
        "active_url": active_url,
        "active_title": active_title,
        "window_id": window_id,
        "open_returncode": open_result.returncode,
        "open_stderr": open_result.stderr.strip(),
        "javascript_from_apple_events_enabled": js_result.returncode == 0,
        "javascript_stderr": js_result.stderr.strip(),
        "visible_text_returncode": visible_text_result.returncode,
        "visible_text_stderr": visible_text_result.stderr.strip(),
        "screenshot_returncode": screenshot_result.returncode,
        "screenshot_stderr": screenshot_result.stderr.strip(),
    }
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    if requested_url:
        requested = urllib.parse.urlparse(requested_url)
        active = urllib.parse.urlparse(active_url)
        url_matches = active_url.startswith(requested_url) or (
            bool(requested.netloc) and active.netloc == requested.netloc
        )
    else:
        url_matches = marker in active_url

    visible = (
        open_result.returncode == 0
        and url_matches
        and bool(active_title)
        and bool(screenshot_bytes)
        and screenshot_result.returncode == 0
    )
    return {
        "visible_surface": visible,
        "dom_path": str(dom_path) if dom else "",
        "dom_sha256": hashlib.sha256(dom.encode("utf-8")).hexdigest() if dom else "",
        "dom_bytes": len(dom.encode("utf-8")),
        "visible_text_path": str(visible_text_path) if visible_text else "",
        "visible_text_sha256": hashlib.sha256(visible_text.encode("utf-8")).hexdigest() if visible_text else "",
        "visible_text_bytes": len(visible_text.encode("utf-8")),
        "page_metadata_path": str(metadata_path),
        "page_metadata_sha256": sha256_file(metadata_path),
        "screenshot_path": str(screenshot_path) if screenshot_bytes else "",
        "screenshot_sha256": hashlib.sha256(screenshot_bytes).hexdigest() if screenshot_bytes else "",
        "screenshot_bytes": len(screenshot_bytes),
        "url": active_url,
        "requested_url": requested_url,
        "title": active_title,
        "acquired_via": APPLE_EVENTS_SURFACE,
        "javascript_from_apple_events_enabled": js_result.returncode == 0,
    }


def build_payload(
    out_path: Path,
    secret: str,
    limit: int,
    url_prefix: str = "",
) -> dict[str, Any]:
    source_extension_ids = extension_ids_from_source()
    public_extension = public_extension_info()
    engine_status = installed_engine_status()
    profiles_checked, candidates = inspect_chrome_profiles(source_extension_ids)
    enabled_candidates = [c for c in candidates if c.get("enabled") is True]
    candidate_ids = {
        str(c.get("id"))
        for c in candidates
        if isinstance(c.get("id"), str) and c.get("id")
    }
    candidate_ids.update(source_extension_ids)
    native_host = inspect_native_host_manifests(candidate_ids)
    enabled_authorized = [
        c for c in enabled_candidates
        if c.get("id") in set(native_host.get("authorized_extension_ids") or [])
        and c.get("has_native_messaging") is True
        and CHROME_REAL_CLONE_TOKEN not in str(c.get("profile") or "")
    ]
    selected_candidate = enabled_authorized[0] if enabled_authorized else None
    proof_status = 0
    proof_response: dict[str, Any] = {}
    proof_artifacts: dict[str, Any] = {
        "visible_surface": False,
        "screenshot_path": "",
        "dom_path": "",
        "acquired_via": "chrome_extension_native_messaging",
    }
    if selected_candidate:
        proof_status, proof_response = request_surface_proof(secret, limit, url_prefix)
        if proof_response.get("ok") is True:
            proof_artifacts = write_surface_artifacts(
                proof_response, out_path.parent / "proofs"
            )
    applescript_proof: dict[str, Any] = {}
    if not proof_artifacts.get("visible_surface"):
        applescript_proof = collect_chrome_applescript_surface(out_path, url_prefix)
        if applescript_proof.get("visible_surface") is True:
            proof_artifacts = applescript_proof

    reason = blocker_reason(candidates, enabled_candidates, native_host)
    pass_ok = (
        (
            bool(selected_candidate)
            and proof_status == 200
            and proof_response.get("ok") is True
        )
        or proof_artifacts.get("acquired_via") == APPLE_EVENTS_SURFACE
    ) and proof_artifacts.get("visible_surface") is True
    if pass_ok:
        reason = ""
    surface_path = (
        str(proof_artifacts.get("acquired_via"))
        if proof_artifacts.get("acquired_via") == APPLE_EVENTS_SURFACE
        else (
            "chrome_extension_native_messaging"
            if native_host.get("checked")
            else "installed_chrome_extension"
        )
    )
    real_profile_seen = any(
        profile.get("exists") and not profile.get("banned_clone_path")
        for root in profiles_checked
        for profile in root.get("profiles", [])
    )
    proof_profile = (
        str(selected_candidate.get("profile") or "")
        if selected_candidate
        else first_real_profile_path(profiles_checked)
    )
    proof_profile_source = "extension_candidate" if selected_candidate else (
        "inspected_real_chrome_profile" if proof_profile else ""
    )

    return {
        "schema": SCHEMA,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pass": pass_ok,
        "surface_path": surface_path,
        "uses_chrome_real_clone": False,
        "direct_browser_cdp": False,
        "engine": {
            "url": os.environ.get("ANTICIPY_ENGINE_URL", "http://127.0.0.1:8731"),
            "installed_process": engine_status,
        },
        "public_extension": public_extension,
        "chrome": {
            "app": "Google Chrome",
            "platform": platform.platform(),
            "hidden_browser": False,
            "profile": {
                "kind": "real_user" if real_profile_seen else "not_found",
                "proof_profile": proof_profile,
                "proof_profile_source": proof_profile_source,
                "proof_extension_id": str(selected_candidate.get("id") or "") if selected_candidate else "",
                "profiles_checked": profiles_checked,
                "extension_candidates": candidates,
                "source_extension_ids": source_extension_ids,
            },
        },
        "native_host": native_host,
        "proof_request": {
            "status": proof_status,
            "ok": proof_response.get("ok") is True,
            "error": proof_response.get("error") or "",
        },
        "proofs": proof_artifacts,
        "applescript_surface_probe": applescript_proof,
        "blocker": {
            "kind": "" if pass_ok else "extension_missing_or_unauthorized",
            "reason": reason,
            "chrome_profiles_checked": profiles_checked,
            "extension_candidates": candidates,
            "native_host_manifest": native_host,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--secret",
        default=os.environ.get("ANTICIPY_TRIGGER_SECRET", "local-dev"),
    )
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--url-prefix", default="")
    args = parser.parse_args()

    out = Path(args.out)
    payload = build_payload(out, args.secret, args.limit, args.url_prefix)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if not payload["engine"]["installed_process"].get("ok"):
        print(payload["blocker"]["reason"], file=sys.stderr)
        return 1
    print(json.dumps({
        "pass": payload["pass"],
        "surface_path": payload["surface_path"],
        "blocker": payload["blocker"]["reason"],
        "out": str(out),
    }))
    return 0 if payload["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
