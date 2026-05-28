#!/usr/bin/env python3
"""Drive an uploaded-audio stranger through the public app and installed engine.

The driver uses the visible public app in the user's real Chrome and the macOS
file picker to upload an MP3. It falls back to no endpoint shortcut; if the UI
cannot submit the file, the run fails honestly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


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


def post_bytes(url: str, payload: bytes, content_type: str, timeout: float = 240.0) -> tuple[int, dict[str, Any]]:
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": content_type}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return int(getattr(resp, "status", 200)), json.loads(resp.read().decode("utf-8"))


def get_json(url: str, timeout: float = 10.0) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run(cmd: list[str], timeout: float = 30.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False,
    )


def open_visible_chrome(url: str) -> dict[str, Any]:
    proc = run(["open", "-a", "Google Chrome", url], timeout=20)
    time.sleep(4.0)
    return {"returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr, "url": url}


def find_upload_text(script: dict[str, Any]) -> str:
    for moment in script.get("moments") or []:
        if not isinstance(moment, dict):
            continue
        kind = str(moment.get("kind") or "").lower()
        fidelity = str(moment.get("input_fidelity") or "").lower()
        if kind in {"upload_audio", "audio_upload", "mp3_upload", "uploads_audio"} or fidelity == "uploaded_audio":
            text = str(moment.get("spoken_reference_text") or moment.get("text_reference") or "").strip()
            if text:
                return text
    raise SystemExit("script has no uploaded-audio spoken_reference_text")


def first_surface_url(script: dict[str, Any], fallback: str = "https://app.hubspot.com/contacts") -> str:
    for surface in script.get("real_user_surfaces") or []:
        if not isinstance(surface, dict):
            continue
        value = str(surface.get("surface") or "")
        if "hubspot" in value.lower():
            return fallback
    return fallback


def same_origin_or_prefix(actual: str, requested: str, origin: str) -> bool:
    if actual.startswith(requested):
        return True
    try:
        actual_url = urlparse(actual)
        requested_url = urlparse(requested)
        origin_url = urlparse(origin)
    except Exception:
        return False
    expected_host = requested_url.netloc or origin_url.netloc
    return actual_url.scheme in {"http", "https"} and actual_url.netloc == expected_host


def say_audio(path: Path, text: str) -> dict[str, Any]:
    proc = run(["say", "-v", "Samantha", "-r", "150", "-o", str(path), text], timeout=120)
    return {
        "ok": proc.returncode == 0 and path.exists() and path.stat().st_size > 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
        "path": str(path),
        "bytes": path.stat().st_size if path.exists() else 0,
        "voice": "Samantha",
        "rate": 150,
    }


def make_mp3_audio(audio_dir: Path, text: str) -> dict[str, Any]:
    aiff_path = audio_dir / "uploaded_audio.aiff"
    mp3_path = audio_dir / "uploaded_audio.mp3"
    say = say_audio(aiff_path, text)
    ffmpeg = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
    converted = {"ok": False, "returncode": 127, "stdout": "", "stderr": "ffmpeg not found"}
    if say["ok"] and Path(ffmpeg).exists():
        converted_proc = run(
            [
                ffmpeg,
                "-y",
                "-i",
                str(aiff_path),
                "-codec:a",
                "libmp3lame",
                "-b:a",
                "128k",
                str(mp3_path),
            ],
            timeout=120,
        )
        converted = {
            "ok": converted_proc.returncode == 0 and mp3_path.exists() and mp3_path.stat().st_size > 0,
            "returncode": converted_proc.returncode,
            "stdout": converted_proc.stdout[-4000:],
            "stderr": converted_proc.stderr[-4000:],
        }
    return {
        "ok": bool(say["ok"] and converted.get("ok") and mp3_path.exists()),
        "source_aiff": say,
        "conversion": converted,
        "path": str(mp3_path),
        "bytes": mp3_path.stat().st_size if mp3_path.exists() else 0,
        "content_type": "audio/mpeg",
    }


def run_osascript(script: str, timeout: float = 20.0) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["osascript", "-e", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return subprocess.CompletedProcess(["osascript"], 124, stdout, stderr or f"timed out after {timeout}s")


def apple_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def upload_audio_label_center() -> tuple[int, int] | None:
    proc = run_osascript(
        '''
set out to ""
tell application "System Events"
  tell process "Google Chrome"
    set xs to entire contents of window 1
    repeat with x in xs
      try
        if ((name of x) as text) is "Upload audio" then
          set p to position of x
          set sz to size of x
          set out to ((item 1 of p) + ((item 1 of sz) div 2)) & "," & ((item 2 of p) + ((item 2 of sz) div 2))
          exit repeat
        end if
      end try
    end repeat
  end tell
end tell
return out
''',
        timeout=12,
    )
    if proc.returncode != 0:
        return None
    text = proc.stdout.strip()
    if "," not in text:
        return None
    try:
        x, y = [int(part.strip()) for part in text.split(",", 1)]
    except ValueError:
        return None
    return x, y


def click_upload_audio_label() -> subprocess.CompletedProcess[str]:
    return run_osascript(
        '''
set clicked to false
tell application "System Events"
  tell process "Google Chrome"
    set xs to entire contents of window 1
    repeat with x in xs
      try
        if ((name of x) as text) is "Upload audio" then
          click x
          set clicked to true
          exit repeat
        end if
      end try
    end repeat
  end tell
end tell
return clicked
''',
        timeout=12,
    )


def choose_file_in_visible_public_app(file_path: Path) -> dict[str, Any]:
    """Submit the public app's visible Upload audio control via the file picker."""
    absolute_file = file_path.resolve()

    setup = run_osascript(
        '''
tell application "Google Chrome"
  activate
  if (count of windows) > 0 then set bounds of front window to {0, 34, 1184, 900}
end tell
tell application "System Events"
  key code 53
  delay 0.1
  key code 121
  delay 0.2
end tell
''',
        timeout=10,
    )
    center = upload_audio_label_center()
    click = click_upload_audio_label()
    if click.returncode == 0 and click.stdout.strip().lower() != "true":
        time.sleep(1.0)
        center = center or upload_audio_label_center()
        click = click_upload_audio_label()
    time.sleep(0.8)
    chooser = run_osascript(
        f'''
set oldClip to the clipboard
tell application "Google Chrome" to activate
delay 0.2
tell application "System Events"
  keystroke "g" using {{command down, shift down}}
  delay 0.3
  set the clipboard to {apple_quote(str(absolute_file))}
  keystroke "v" using command down
  delay 0.2
  key code 36
  delay 0.6
  key code 36
end tell
delay 0.2
set the clipboard to oldClip
''',
        timeout=45,
    )
    return {
        "ok": click.returncode == 0 and chooser.returncode == 0,
        "submitted_through_public_app_ui": click.returncode == 0 and chooser.returncode == 0,
        "upload_label_center": {"x": center[0], "y": center[1]} if center is not None else None,
        "file_path": str(absolute_file),
        "window_setup": {
            "returncode": setup.returncode,
            "stdout": setup.stdout.strip(),
            "stderr": setup.stderr.strip(),
        },
        "click": {
            "returncode": click.returncode,
            "stdout": click.stdout.strip(),
            "stderr": click.stderr.strip(),
            "method": "chrome_accessibility_click_upload_audio_label",
        },
        "chooser": {
            "returncode": chooser.returncode,
            "stdout": chooser.stdout.strip(),
            "stderr": chooser.stderr.strip(),
        },
    }


def word_hits(expected: str, observed: str) -> dict[str, Any]:
    import re

    expected_words = {
        w for w in re.findall(r"[a-z0-9]+", expected.lower())
        if len(w) >= 4 and w not in {"this", "that", "with", "after", "before"}
    }
    observed_words = set(re.findall(r"[a-z0-9]+", observed.lower()))
    hits = sorted(expected_words & observed_words)
    required = max(5, min(12, len(expected_words) // 3))
    return {
        "pass": len(hits) >= required,
        "hits": hits,
        "required": required,
        "expected_words": sorted(expected_words),
    }


def run_surface_probe(out_path: Path, url_prefix: str = "") -> dict[str, Any]:
    cmd = ["python3", "scripts/v7/probe_real_surface_extension.py", "--out", str(out_path)]
    if url_prefix:
        cmd.extend(["--url-prefix", url_prefix])
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=70,
        check=False,
    )
    payload = read_json(out_path) if out_path.exists() else {}
    payload["_probe_returncode"] = proc.returncode
    payload["_probe_stdout"] = proc.stdout.strip()
    payload["_probe_stderr"] = proc.stderr.strip()
    return payload


def visible_text_from_probe(probe: dict[str, Any]) -> str:
    path = str((probe.get("proofs") or {}).get("visible_text_path") or "")
    if not path:
        return ""
    text_path = Path(path)
    if not text_path.is_absolute():
        text_path = Path.cwd() / text_path
    try:
        return text_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def has_upload_controls(probe: dict[str, Any]) -> bool:
    text = visible_text_from_probe(probe).lower()
    return "upload audio" in text and "audio source" in text and "engine live" in text


def wait_public_upload_surface(public_url: str, stranger_dir: Path, timeout_s: float = 45.0) -> dict[str, Any]:
    """Wait until the visible public app has routed to the Listen upload UI."""
    deadline = time.time() + timeout_s
    attempts: list[dict[str, Any]] = []
    open_result = open_visible_chrome(public_url)
    while time.time() < deadline:
        attempt_idx = len(attempts) + 1
        proof_path = stranger_dir / "screenshots" / f"public_app_before_audio_upload_attempt_{attempt_idx}.json"
        proof = run_surface_probe(proof_path, url_prefix=public_url)
        text = visible_text_from_probe(proof)
        upload_ready = has_upload_controls(proof)
        attempts.append(
            {
                "proof_path": str(proof_path),
                "proof_pass": proof.get("pass"),
                "url": (proof.get("proofs") or {}).get("url"),
                "visible_text_bytes": len(text.encode("utf-8")),
                "visible_text_preview": text[:500],
                "upload_controls_visible": upload_ready,
            }
        )
        if upload_ready:
            return {
                "ok": True,
                "open": open_result,
                "proof": proof,
                "proof_path": str(proof_path),
                "attempts": attempts,
            }
        time.sleep(2.0)
    return {
        "ok": False,
        "open": open_result,
        "proof": proof if "proof" in locals() else {},
        "proof_path": attempts[-1]["proof_path"] if attempts else "",
        "attempts": attempts,
        "error": "visible public app did not show Engine live / Audio source / Upload audio",
    }


def wait_status(engine_url: str, ingest_id: str = "", timeout_s: float = 30.0, after_ts: float = 0.0) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    latest: dict[str, Any] = {}
    while time.time() < deadline:
        latest = get_json(f"{engine_url}/api/listen/status", timeout=10)
        recent = latest.get("recent") if isinstance(latest, dict) else []
        if isinstance(recent, list):
            for record in recent:
                if not isinstance(record, dict):
                    continue
                if ingest_id and record.get("ingest_id") == ingest_id:
                    return latest
                if (
                    not ingest_id
                    and record.get("source") == "upload-asr"
                    and float(record.get("ts") or 0.0) >= after_ts
                ):
                    return latest
        time.sleep(1.0)
    return latest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stranger-dir", required=True, type=Path)
    parser.add_argument("--script-file", required=True, type=Path)
    parser.add_argument("--persona-file", required=True, type=Path)
    parser.add_argument("--engine-url", default="http://127.0.0.1:8731")
    parser.add_argument("--public-url", default="https://www.anticipy.ai/app")
    args = parser.parse_args()

    stranger_dir = args.stranger_dir.resolve()
    script = read_json(args.script_file)
    reference = find_upload_text(script)
    reference_sha = hashlib.sha256(reference.encode("utf-8")).hexdigest()
    started_at = utc_now()

    audio_dir = stranger_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio = make_mp3_audio(audio_dir, reference)

    reset_error = ""
    try:
        post_json(f"{args.engine_url}/api/listen/reset", {})
    except Exception as exc:
        reset_error = f"{type(exc).__name__}: {exc}"

    public_ready = wait_public_upload_surface(args.public_url, stranger_dir)
    public_open = public_ready.get("open") or {}
    public_before_path = Path(str(public_ready.get("proof_path") or (stranger_dir / "screenshots" / "public_app_before_audio_upload.json")))
    public_before = public_ready.get("proof") if isinstance(public_ready.get("proof"), dict) else {}

    upload_started_at = time.time()
    if not public_ready.get("ok"):
        ui_submit = {
            "ok": False,
            "error": public_ready.get("error") or "public app upload controls not visible",
            "submitted_through_public_app_ui": False,
        }
    elif audio["ok"]:
        ui_submit = choose_file_in_visible_public_app(Path(audio["path"]))
    else:
        ui_submit = {
            "ok": False,
            "error": "MP3 audio artifact was not created",
            "submitted_through_public_app_ui": False,
        }
    status_after = wait_status(args.engine_url, after_ts=upload_started_at, timeout_s=180.0)
    recent = status_after.get("recent") if isinstance(status_after, dict) else []
    matching_recent = {}
    if isinstance(recent, list):
        for record in recent:
            if (
                isinstance(record, dict)
                and record.get("source") == "upload-asr"
                and float(record.get("ts") or 0.0) >= upload_started_at
            ):
                matching_recent = record
                break
    ingest_id = str(matching_recent.get("ingest_id") or "")
    transcript = str(matching_recent.get("transcript") or "")
    upload_status = 200 if ingest_id else 0
    upload_response: dict[str, Any] = matching_recent
    upload_error = "" if ingest_id else "visible public app upload did not produce a new upload-asr record"
    hit = word_hits(reference, transcript)

    service_url = first_surface_url(script)
    service_open = open_visible_chrome(service_url)
    service_proof_path = stranger_dir / "screenshots" / "crm_surface_after_audio_upload.json"
    service_proof = run_surface_probe(service_proof_path, url_prefix="https://app.hubspot.com")

    public_after = open_visible_chrome(args.public_url)
    public_after_path = stranger_dir / "screenshots" / "public_app_after_audio_upload.json"
    public_after_proof = run_surface_probe(public_after_path, url_prefix=args.public_url)

    pending = status_after.get("pending") if isinstance(status_after, dict) else {}
    recent = status_after.get("recent") if isinstance(status_after, dict) else []

    service_proof_url = str((service_proof.get("proofs") or {}).get("url") or "")
    service_visible = (
        isinstance(service_proof, dict)
        and service_proof.get("pass") is True
        and ((service_proof.get("proofs") or {}).get("visible_surface") is True)
        and same_origin_or_prefix(service_proof_url, service_url, "https://app.hubspot.com")
    )
    accepted_audio = (
        upload_status == 200
        and upload_response.get("source") == "upload-asr"
        and ingest_id.startswith("upload-asr-")
        and bool(transcript.strip())
        and hit["pass"] is True
        and ui_submit.get("submitted_through_public_app_ui") is True
    )
    decision_visible = bool(
        isinstance(pending, dict)
        and (
            pending.get("proposal")
            or pending.get("decline")
            or pending.get("competent_decline")
        )
    )
    ok = accepted_audio and service_visible and decision_visible

    result = {
        "schema": "anticipy.v7.deterministic_audio_upload_driver",
        "stranger_id": stranger_dir.name,
        "generated_at": utc_now(),
        "started_at": started_at,
        "ok": ok,
        "driver_failed": not ok,
        "driver_exit_code": 0 if ok else 1,
        "failure_phase": "" if ok else "audio-upload-service-surface-decision-proof",
        "persona_file": str(args.persona_file),
        "script_file": str(args.script_file),
        "engine_url": args.engine_url,
        "public_url": args.public_url,
        "reset_error": reset_error,
        "input_mode": "uploaded_audio",
        "source_mode": "audio_upload",
        "source": "upload-asr",
        "post_transcript_boundary_source": "upload-asr",
        "submitted_through_public_app_ui": bool(ui_submit.get("submitted_through_public_app_ui")),
        "submitted_through_public_product_upload_endpoint": False,
        "visible_ui_driver": "real_chrome_visible_file_picker_upload",
        "ui_submit": ui_submit,
        "audio_artifact": audio,
        "reference_transcript": reference,
        "transcript_boundary": transcript,
        "transcript_boundary_chars": len(transcript),
        "transcript_boundary_sha256": hashlib.sha256(transcript.encode("utf-8")).hexdigest(),
        "reference_sha256": reference_sha,
        "controlled_phrase_match": hit,
        "upload": {
            "status": upload_status,
            "error": upload_error,
            "response": upload_response,
            "content_type": "audio/mpeg",
        },
        "status_after_sanitized": {
            "pending": pending if isinstance(pending, dict) else {},
            "matching_recent": matching_recent,
            "recent_count": len(recent) if isinstance(recent, list) else 0,
        },
        "public_surface_before": {
            "open": public_open,
            "proof_path": str(public_before_path),
            "proof_pass": public_before.get("pass"),
            "upload_surface_ready": public_ready.get("ok"),
            "readiness_attempts": public_ready.get("attempts") or [],
        },
        "service_surface": {
            "open": service_open,
            "proof_path": str(service_proof_path),
            "proof_pass": service_proof.get("pass"),
            "visible_surface": (service_proof.get("proofs") or {}).get("visible_surface"),
            "url": service_proof_url,
            "screenshot_path": (service_proof.get("proofs") or {}).get("screenshot_path"),
            "uses_chrome_real_clone": service_proof.get("uses_chrome_real_clone"),
            "direct_browser_cdp": service_proof.get("direct_browser_cdp"),
        },
        "public_surface_after": {
            "open": public_after,
            "proof_path": str(public_after_path),
            "proof_pass": public_after_proof.get("pass"),
        },
        "visible_surface_proof_path": str(service_proof_path),
        "visible_surface_proof": {
            "pass": service_proof.get("pass"),
            "surface_path": service_proof.get("surface_path"),
            "url": (service_proof.get("proofs") or {}).get("url"),
            "dom_path": (service_proof.get("proofs") or {}).get("dom_path"),
            "page_metadata_path": (service_proof.get("proofs") or {}).get("page_metadata_path"),
            "screenshot_path": (service_proof.get("proofs") or {}).get("screenshot_path"),
            "uses_chrome_real_clone": service_proof.get("uses_chrome_real_clone"),
            "direct_browser_cdp": service_proof.get("direct_browser_cdp"),
        },
        "runtime_model_cost_usd": 0.0,
    }
    write_json(stranger_dir / "driver_result.json", result)
    print(json.dumps({"ok": ok, "out": str(stranger_dir / "driver_result.json")}, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
