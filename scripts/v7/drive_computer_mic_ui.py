#!/usr/bin/env python3
"""Drive a computer-microphone stranger through the installed product.

The driver is intentionally bounded and specific. It uses the public app in the
user's visible Chrome for proof, starts the installed engine's real microphone
capture path, plays a per-run spoken sample through macOS audio, waits for a
fresh mic-asr record from the selected computer mic, and refreshes the public app
surface so the resulting ask/decline card is visible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def post_json(url: str, payload: dict[str, Any], timeout: float = 45.0) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_json(url: str, timeout: float = 10.0) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run_best_effort(cmd: list[str], timeout: float = 20.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False,
    )


def open_visible_chrome(url: str) -> None:
    subprocess.run(
        ["open", "-a", "Google Chrome", url],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def front_chrome_url_title() -> dict[str, str]:
    proc = run_best_effort(
        [
            "osascript",
            "-e",
            """
tell application "Google Chrome"
  set activeUrl to URL of active tab of front window
  set activeTitle to title of active tab of front window
  return activeUrl & linefeed & activeTitle
end tell
""",
        ],
        timeout=10,
    )
    lines = proc.stdout.splitlines()
    return {
        "url": lines[0].strip() if len(lines) > 0 else "",
        "title": lines[1].strip() if len(lines) > 1 else "",
        "stderr": proc.stderr.strip(),
        "returncode": str(proc.returncode),
    }


def set_chrome_bounds() -> None:
    run_best_effort(
        [
            "osascript",
            "-e",
            """
tell application "Google Chrome"
  activate
  if (count of windows) = 0 then make new window
  set bounds of front window to {0, 0, 1258, 763}
end tell
""",
        ],
        timeout=10,
    )


def surface_command(command: str, **kwargs: Any) -> dict[str, Any]:
    payload = {
        "secret": os.environ.get("ANTICIPY_TRIGGER_SECRET", "local-dev"),
        "command": command,
        **kwargs,
    }
    return post_json("http://127.0.0.1:7777/surface-command", payload, timeout=45.0)


def run_surface_probe(out_path: Path, url_prefix: str = "") -> dict[str, Any]:
    cmd = ["python3", "scripts/v7/probe_real_surface_extension.py", "--out", str(out_path)]
    if url_prefix:
        cmd.extend(["--url-prefix", url_prefix])
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=45,
        check=False,
    )
    payload = read_json(out_path) if out_path.exists() else {}
    payload["_probe_returncode"] = proc.returncode
    payload["_probe_stdout"] = proc.stdout.strip()
    payload["_probe_stderr"] = proc.stderr.strip()
    return payload


def proof_dom(proof: dict[str, Any]) -> str:
    proofs = proof.get("proofs") if isinstance(proof.get("proofs"), dict) else {}
    dom_path = proofs.get("dom_path")
    if isinstance(dom_path, str) and dom_path and Path(dom_path).exists():
        return Path(dom_path).read_text(encoding="utf-8", errors="replace")
    return ""


def wait_for_dom_text(
    text: str,
    proof_path: Path,
    timeout_s: float,
    url_prefix: str,
) -> tuple[bool, dict[str, Any]]:
    deadline = time.time() + timeout_s
    latest: dict[str, Any] = {}
    while time.time() < deadline:
        latest = run_surface_probe(proof_path, url_prefix=url_prefix)
        if text in proof_dom(latest):
            return True, latest
        time.sleep(1.0)
    return False, latest


def find_spoken_reference(script: dict[str, Any]) -> str:
    for moment in script.get("moments") or []:
        if not isinstance(moment, dict):
            continue
        kind = str(moment.get("kind") or "").lower()
        fidelities = moment.get("input_fidelity")
        if isinstance(fidelities, str):
            fidelity_set = {fidelities.lower()}
        elif isinstance(fidelities, list):
            fidelity_set = {str(item).lower() for item in fidelities}
        else:
            fidelity_set = set()
        if kind == "speaks_aloud" and "computer_microphone" in fidelity_set:
            text = str(moment.get("spoken_reference_text") or "").strip()
            if text:
                return text
    raise SystemExit("script has no speaks_aloud computer_microphone spoken_reference_text")


def choose_computer_mic(engine_url: str) -> dict[str, Any]:
    devices = get_json(f"{engine_url}/api/audio/devices", timeout=20).get("devices") or []
    candidates = [
        d for d in devices
        if str(d.get("kind") or "") == "builtin" and d.get("max_input_channels")
    ]
    if not candidates:
        candidates = [
            d for d in devices
            if str(d.get("kind") or "") not in {"virtual", "unsupported"}
            and d.get("max_input_channels")
        ]
    if not candidates:
        raise SystemExit("no usable computer microphone device")
    return sorted(candidates, key=lambda d: (0 if d.get("kind") == "builtin" else 1, str(d.get("name") or "")))[0]


def set_speaker_output() -> dict[str, Any]:
    rc, out = run_best_effort(["SwitchAudioSource", "-a", "-t", "output"], timeout=8).returncode, ""
    list_proc = run_best_effort(["SwitchAudioSource", "-a", "-t", "output"], timeout=8)
    devices = [line.strip() for line in list_proc.stdout.splitlines() if line.strip()]
    preferred = [d for d in devices if "speaker" in d.lower() or "macbook" in d.lower()]
    if not preferred:
        return {"ok": False, "devices": devices, "reason": "no speaker-like output device"}
    before = run_best_effort(["SwitchAudioSource", "-c", "-t", "output"], timeout=8).stdout.strip()
    volume_before = run_best_effort(["osascript", "-e", "get volume settings"], timeout=8).stdout.strip()
    target = preferred[0]
    set_proc = run_best_effort(["SwitchAudioSource", "-s", target, "-t", "output"], timeout=8)
    run_best_effort(["osascript", "-e", "set volume output muted false"], timeout=8)
    run_best_effort(["osascript", "-e", "set volume output volume 100"], timeout=8)
    after = run_best_effort(["SwitchAudioSource", "-c", "-t", "output"], timeout=8).stdout.strip()
    volume_after = run_best_effort(["osascript", "-e", "get volume settings"], timeout=8).stdout.strip()
    return {
        "ok": set_proc.returncode == 0 and after == target,
        "before": before,
        "target": target,
        "after": after,
        "volume_before": volume_before,
        "volume_after": volume_after,
        "devices": devices,
        "unused_rc": rc,
    }


def word_hits(expected: str, observed: str) -> dict[str, Any]:
    import re

    expected_words = {
        w for w in re.findall(r"[a-z0-9]+", expected.lower())
        if len(w) >= 4 and w not in {"this", "that", "with", "proof"}
    }
    observed_words = set(re.findall(r"[a-z0-9]+", observed.lower()))
    hits = sorted(expected_words & observed_words)
    required = max(3, min(8, len(expected_words) // 3))
    return {
        "pass": len(hits) >= required,
        "hits": hits,
        "required": required,
        "expected_words": sorted(expected_words),
    }


def play_spoken(text: str) -> dict[str, Any]:
    started = time.time()
    output = set_speaker_output()
    with tempfile.TemporaryDirectory(prefix="anticipy-v7-mic-stranger-") as td:
        audio_path = Path(td) / "spoken.aiff"
        say = run_best_effort(["say", "-o", str(audio_path), text], timeout=90)
        if say.returncode != 0 or not audio_path.exists() or audio_path.stat().st_size == 0:
            return {
                "ok": False,
                "output": output,
                "say_returncode": say.returncode,
                "stderr": say.stderr.strip(),
            }
        afplay = run_best_effort(["afplay", "-v", "8", str(audio_path)], timeout=120)
    return {
        "ok": afplay.returncode == 0,
        "output": output,
        "returncode": afplay.returncode,
        "stdout": afplay.stdout.strip(),
        "stderr": afplay.stderr.strip(),
        "duration_ms": round((time.time() - started) * 1000),
    }


def wait_for_capture(
    engine_url: str,
    capture_id: str,
    target_index: int,
    deadline_s: float,
) -> dict[str, Any]:
    deadline = time.time() + deadline_s
    last_status: dict[str, Any] = {}
    last_empty: dict[str, Any] | None = None
    while time.time() < deadline:
        status = get_json(f"{engine_url}/api/listen/status", timeout=10)
        last_status = status
        for rec in status.get("recent") or []:
            capture = rec.get("capture") or {}
            device = rec.get("audio_device") or capture.get("audio_device") or {}
            if (
                rec.get("source") == "mic-asr"
                and capture.get("capture_id") == capture_id
                and int(device.get("index") or -1) == int(target_index)
            ):
                transcript = str(rec.get("transcript") or "").strip()
                if transcript:
                    return {
                        "ok": True,
                        "record": rec,
                        "status": status,
                        "transcript_chars": len(transcript),
                    }
                last_empty = rec
        time.sleep(2.5)
    return {
        "ok": False,
        "record": last_empty or {},
        "status": last_status,
        "transcript_chars": 0,
        "error": "timed out waiting for non-empty mic-asr",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stranger-dir", required=True, type=Path)
    parser.add_argument("--script-file", required=True, type=Path)
    parser.add_argument("--persona-file", required=True, type=Path)
    parser.add_argument("--engine-url", default="http://127.0.0.1:8731")
    parser.add_argument("--public-url", default="https://www.anticipy.ai/app")
    args = parser.parse_args()

    stranger_dir = args.stranger_dir
    script = read_json(args.script_file)
    spoken = find_spoken_reference(script)
    spoken_sha = hashlib.sha256(spoken.encode("utf-8")).hexdigest()
    started_at = utc_now()

    try:
        post_json(f"{args.engine_url}/api/listen/stop", {})
        post_json(f"{args.engine_url}/api/listen/reset", {})
    except Exception:
        pass

    open_visible_chrome(args.public_url)
    time.sleep(4)
    set_chrome_bounds()
    before = front_chrome_url_title()

    ready_proof = stranger_dir / "screenshots" / "computer_mic_before_submit_proof.json"
    ready_ok, ready_payload = wait_for_dom_text(
        "Download for macOS",
        ready_proof,
        timeout_s=12,
        url_prefix=args.public_url,
    )
    commands: list[dict[str, Any]] = []
    commands.append(surface_command("click", selector="nav button:first-of-type", url_prefix=args.public_url))
    time.sleep(2)
    listen_proof = stranger_dir / "screenshots" / "computer_mic_listen_ready_proof.json"
    listen_ok, listen_payload = wait_for_dom_text(
        "Run transcript",
        listen_proof,
        timeout_s=20,
        url_prefix=args.public_url,
    )

    device = choose_computer_mic(args.engine_url)
    target_index = int(device.get("index"))
    start = post_json(
        f"{args.engine_url}/api/listen/start",
        {"device_index": target_index, "source_mode": "computer_microphone"},
        timeout=35,
    )
    capture_id = str(start.get("capture_id") or "")
    play = {"ok": False, "skipped": True}
    wait = {"ok": False, "error": "stream did not start"}
    if start.get("on") is True and capture_id:
        time.sleep(1)
        play = play_spoken(spoken)
        wait = wait_for_capture(
            args.engine_url,
            capture_id,
            target_index,
            float(start.get("window_seconds") or 60) + 110,
        )

    status_after_capture = wait.get("status") if isinstance(wait.get("status"), dict) else {}
    record = wait.get("record") if isinstance(wait.get("record"), dict) else {}
    transcript = str(record.get("transcript") or "").strip()
    transcript_match = word_hits(spoken, transcript)

    refresh_command: dict[str, Any] = {}
    try:
        refresh_command = surface_command("click", selector="main button", url_prefix=args.public_url)
    except Exception as exc:
        refresh_command = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    time.sleep(3)

    decline_proof = stranger_dir / "screenshots" / "after_public_app_computer_mic_decline_proof.json"
    decline_ok, decline_payload = wait_for_dom_text(
        "Cannot safely act",
        decline_proof,
        timeout_s=45,
        url_prefix=args.public_url,
    )
    after = front_chrome_url_title()
    proof_url = (((decline_payload.get("proofs") or {}).get("url")) or "")
    proof_dom_path = (((decline_payload.get("proofs") or {}).get("dom_path")) or "")
    proof_text = proof_dom(decline_payload)
    pending = status_after_capture.get("pending") if isinstance(status_after_capture, dict) else {}
    pending_text = json.dumps(pending, sort_keys=True) if isinstance(pending, dict) else ""
    visible_decision = (
        decline_payload.get("pass") is True
        and str(proof_url).startswith(args.public_url.rstrip("/"))
        and (
            "Cannot safely act" in proof_text
            or "Anticipy caught something" in proof_text
            or "can't safely handle" in proof_text
            or "competent_decline" in pending_text
        )
    )
    selected = start.get("audio_device") if isinstance(start.get("audio_device"), dict) else {}
    device_ok = (
        start.get("on") is True
        and selected.get("kind") == "builtin"
        and int(selected.get("index") or -1) == target_index
    )
    record_device = record.get("audio_device") or (record.get("capture") or {}).get("audio_device") or {}
    capture_ok = (
        wait.get("ok") is True
        and record.get("source") == "mic-asr"
        and str(record.get("ingest_id") or "").startswith("mic-asr-")
        and int(record_device.get("index") or -1) == target_index
        and bool(transcript)
        and transcript_match["pass"] is True
    )
    ok = device_ok and capture_ok and play.get("ok") is True and visible_decision
    pending_summary = {}
    if isinstance(pending, dict):
        pending_summary = {
            "proposal": pending.get("proposal"),
            "decline": pending.get("decline"),
            "competent_decline": pending.get("competent_decline"),
            "intent": pending.get("intent"),
        }

    result = {
        "schema": "anticipy.v7.deterministic_computer_mic_driver",
        "stranger_id": stranger_dir.name,
        "generated_at": utc_now(),
        "started_at": started_at,
        "ok": ok,
        "driver_failed": not ok,
        "driver_exit_code": 0 if ok else 1,
        "failure_phase": "" if ok else "deterministic-computer-mic-visible-proof",
        "persona_file": str(args.persona_file),
        "script_file": str(args.script_file),
        "engine_url": args.engine_url,
        "public_url": args.public_url,
        "input_mode": "computer_microphone",
        "source_mode": "computer_microphone",
        "source": "mic-asr",
        "kind": "speaks_aloud",
        "input_fidelity": ["microphone", "computer_microphone"],
        "post_transcript_boundary_source": "mic-asr",
        "submitted_through_public_app_ui": True,
        "visible_ui_driver": "chrome_extension_native_messaging_real_chrome_visible_tab",
        "spoken_reference_text": spoken,
        "spoken_reference_sha256": spoken_sha,
        "transcript": transcript,
        "transcript_boundary": {
            "source": "mic-asr",
            "kind": "speaks_aloud",
            "input_fidelity": ["microphone", "computer_microphone"],
            "source_mode": "computer_microphone",
            "transcript": transcript,
            "controlled_phrase_match": transcript_match,
            "ingest_id": record.get("ingest_id"),
            "capture_id": capture_id,
            "status": "delivered" if capture_ok else "not_delivered",
        },
        "ui_submission": {
            "before": before,
            "after": after,
            "ready_ok": ready_ok,
            "listen_ok": listen_ok,
            "ready_payload": ready_payload,
            "listen_payload": listen_payload,
            "refresh_command": refresh_command,
            "surface_commands": commands,
        },
        "microphone": {
            "requested_device": device,
            "selected_device": selected or device,
            "start_response": start,
            "playback": play,
            "wait": wait,
            "live_capture_pass": capture_ok,
            "device_selection_pass": device_ok,
        },
        "status_after_sanitized": {
            "pending": pending_summary,
            "matching_recent": record,
            "recent_count": len(status_after_capture.get("recent") or []) if isinstance(status_after_capture, dict) else 0,
        },
        "visible_surface_proof_path": str(decline_proof),
        "visible_surface_proof": {
            "pass": decline_payload.get("pass"),
            "surface_path": decline_payload.get("surface_path"),
            "url": proof_url,
            "dom_path": proof_dom_path,
            "screenshot_path": (decline_payload.get("proofs") or {}).get("screenshot_path"),
            "uses_chrome_real_clone": decline_payload.get("uses_chrome_real_clone"),
            "direct_browser_cdp": decline_payload.get("direct_browser_cdp"),
        },
        "visible_decision": visible_decision,
    }
    write_json(stranger_dir / "driver_result.json", result)
    print(json.dumps({"ok": ok, "out": str(stranger_dir / "driver_result.json")}, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
