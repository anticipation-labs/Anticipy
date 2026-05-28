#!/usr/bin/env python3
"""Drive a transcript-paste stranger through the installed visible product.

This is a bounded deterministic driver for V7 transcript-paste moments. It
does not use a backend credential shortcut. It opens the user's visible Chrome
to the installed user-device engine, delivers the transcript at the same
post-ASR boundary as the UI's "Run transcript" action, then captures the real
Chrome surface through the Anticipy extension/native bridge.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib import request
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def find_transcript(script: dict[str, Any]) -> str:
    for moment in script.get("moments") or []:
        if isinstance(moment, dict) and str(moment.get("kind") or "").lower() in {
            "transcript_paste",
            "transcript_upload",
            "upload_transcript",
            "text_transcript_upload",
        }:
            for key in (
                "transcript_reference_text",
                "text_reference",
                "content",
                "text",
                "transcript",
            ):
                value = moment.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
    raise SystemExit("script has no transcript paste/upload text")


def iter_script_strings(value: Any) -> list[str]:
    strings: list[str] = []
    if isinstance(value, dict):
        for child in value.values():
            strings.extend(iter_script_strings(child))
    elif isinstance(value, list):
        for child in value:
            strings.extend(iter_script_strings(child))
    elif isinstance(value, str):
        strings.append(value)
    return strings


def service_precheck_urls(script: dict[str, Any]) -> list[dict[str, str]]:
    """Return real user-surface URLs implied by the generated script.

    These prechecks are proof collection only. They do not claim the task is
    done; they give the evaluator a real service surface to pair with an act,
    ask, or competent decline.
    """

    haystack = "\n".join(iter_script_strings(script)).lower()
    candidates: list[dict[str, str]] = []
    if "canva" in haystack:
        candidates.append(
            {
                "surface": "canvas_design",
                "service": "canva",
                "url": "https://www.canva.com/",
                "proof_text": "Canva",
            }
        )
    if "figma" in haystack:
        candidates.append(
            {
                "surface": "canvas_design",
                "service": "figma",
                "url": "https://www.figma.com/files/",
                "proof_text": "Figma",
            }
        )
    if "salesforce" in haystack:
        candidates.append(
            {
                "surface": "crm",
                "service": "salesforce",
                "url": "https://login.salesforce.com/",
                "proof_text": "Salesforce",
            }
        )
    if "hubspot" in haystack:
        candidates.append(
            {
                "surface": "crm",
                "service": "hubspot",
                "url": "https://app.hubspot.com/",
                "proof_text": "HubSpot",
            }
        )
    if "amazon" in haystack:
        candidates.append(
            {
                "surface": "commerce",
                "service": "amazon",
                "url": "https://www.amazon.com/",
                "proof_text": "Amazon",
            }
        )
    return candidates


def post_json(url: str, payload: dict[str, Any], timeout: float = 45.0) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_json(url: str, timeout: float = 10.0) -> dict[str, Any]:
    with request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def open_visible_chrome(url: str) -> None:
    subprocess.run(
        ["open", "-a", "Google Chrome", url],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def url_with_view(public_url: str, view: str) -> str:
    parsed = urlparse(public_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["view"] = view
    return urlunparse(parsed._replace(query=urlencode(query)))


def run_best_effort(cmd: list[str], timeout: float = 20.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False,
    )


def apple_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def front_chrome_url_title() -> dict[str, str]:
    script = """
tell application "Google Chrome"
  set activeUrl to URL of active tab of front window
  set activeTitle to title of active tab of front window
  return activeUrl & linefeed & activeTitle
end tell
"""
    proc = run_best_effort(["osascript", "-e", script], timeout=10)
    lines = proc.stdout.splitlines()
    return {
        "url": lines[0].strip() if len(lines) > 0 else "",
        "title": lines[1].strip() if len(lines) > 1 else "",
        "stderr": proc.stderr.strip(),
        "returncode": str(proc.returncode),
    }


def set_chrome_bounds() -> None:
    script = """
tell application "Google Chrome"
  activate
  if (count of windows) = 0 then make new window
  set bounds of front window to {0, 0, 1258, 763}
end tell
"""
    run_best_effort(["osascript", "-e", script], timeout=10)


def surface_command(command: str, **kwargs: Any) -> dict[str, Any]:
    payload = {
        "secret": os.environ.get("ANTICIPY_TRIGGER_SECRET", "local-dev"),
        "command": command,
        **kwargs,
    }
    return post_json("http://127.0.0.1:7777/surface-command", payload, timeout=45.0)


def wait_for_dom_text(
    text: str,
    proof_path: Path,
    timeout_s: float = 25.0,
    url_prefix: str = "",
) -> tuple[bool, dict[str, Any]]:
    deadline = time.time() + timeout_s
    latest: dict[str, Any] = {}
    while time.time() < deadline:
        run_surface_probe(proof_path, url_prefix=url_prefix)
        latest = read_json(proof_path) if proof_path.exists() else {}
        if text in proof_text(latest):
            return True, latest
        time.sleep(1.0)
    return False, latest


def proof_text(proof: dict[str, Any]) -> str:
    proofs = proof.get("proofs") if isinstance(proof.get("proofs"), dict) else {}
    chunks: list[str] = []
    for key in ("dom_path", "visible_text_path"):
        value = proofs.get(key)
        if isinstance(value, str) and value:
            path = Path(value)
            if path.is_file():
                chunks.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(chunks)


def proof_dom_contains(proof: dict[str, Any], text: str) -> bool:
    return text in proof_text(proof)


def drive_public_transcript_ui(public_url: str, transcript: str, stranger_dir: Path) -> dict[str, Any]:
    """Submit transcript through the public /app UI in the visible Chrome.

    This intentionally uses the same user-visible public app a stranger uses.
    It targets the current active Chrome tab through the installed
    extension/native bridge, clicks the real Listen nav, types into the real
    transcript textarea, and clicks the real Run transcript button. The bridge
    then captures the visible resulting surface.
    """

    listen_url = url_with_view(public_url, "listen")
    open_visible_chrome(listen_url)
    time.sleep(4.0)
    set_chrome_bounds()

    before = front_chrome_url_title()
    ready_proof = stranger_dir / "screenshots" / "public_app_before_submit_proof.json"
    ready_ok, ready_payload = wait_for_dom_text(
        "Download for macOS",
        ready_proof,
        timeout_s=10.0,
        url_prefix=public_url,
    )

    commands: list[dict[str, Any]] = []
    if proof_dom_contains(ready_payload, "Run transcript"):
        commands.append(
            {
                "ok": True,
                "skipped": True,
                "reason": "already on Listen view via view=listen deep link",
            }
        )
    elif proof_dom_contains(ready_payload, "Listen again"):
        commands.append(
            surface_command(
                "click",
                selector="main button:last-of-type",
                url_prefix=public_url,
            )
        )
    else:
        commands.append(
            surface_command(
                "click",
                selector="nav button:first-of-type",
                url_prefix=public_url,
            )
        )
    time.sleep(2.0)
    listen_proof = stranger_dir / "screenshots" / "public_app_listen_ready_proof.json"
    listen_ok, listen_payload = wait_for_dom_text(
        "Run transcript",
        listen_proof,
        timeout_s=20.0,
        url_prefix=public_url,
    )
    if not listen_ok:
        return {
            "ok": False,
            "phase": "listen-ui-not-ready",
            "before": before,
            "ready_ok": ready_ok,
            "ready_payload": ready_payload,
            "listen_payload": listen_payload,
        }

    commands.append(
        surface_command(
            "type",
            selector='textarea[aria-label="Transcript"]',
            text=transcript,
            url_prefix=public_url,
        )
    )
    time.sleep(0.5)
    commands.append(
        surface_command(
            "click",
            selector='textarea[aria-label="Transcript"] + div button',
            url_prefix=public_url,
        )
    )
    decline_proof = stranger_dir / "screenshots" / "after_public_app_transcript_decline_proof.json"
    decline_ok, decline_payload = wait_for_dom_text(
        "Cannot safely act",
        decline_proof,
        timeout_s=45.0,
        url_prefix=public_url,
    )
    after = front_chrome_url_title()
    return {
        "ok": decline_ok,
        "phase": "complete" if decline_ok else "decline-not-visible",
        "public_url": public_url,
        "before": before,
        "after": after,
        "ready_ok": ready_ok,
        "listen_ok": listen_ok,
        "ready_proof_path": str(ready_proof),
        "listen_proof_path": str(listen_proof),
        "decline_proof_path": str(decline_proof),
        "surface_commands": commands,
        "decline_payload": decline_payload,
    }


def capture_service_prechecks(script: dict[str, Any], stranger_dir: Path) -> list[dict[str, Any]]:
    surfaces: list[dict[str, Any]] = []
    for index, item in enumerate(service_precheck_urls(script), start=1):
        proof_path = (
            stranger_dir
            / "screenshots"
            / f"service_precheck_{index}_{item['service']}_proof.json"
        )
        open_visible_chrome(item["url"])
        time.sleep(5.0)
        set_chrome_bounds()
        rc, stdout, stderr = run_surface_probe(proof_path, url_prefix=item["url"])
        proof = read_json(proof_path) if proof_path.exists() else {}
        text = proof_text(proof) if isinstance(proof, dict) else ""
        surfaces.append(
            {
                **item,
                "proof_path": str(proof_path),
                "probe_exit_code": rc,
                "probe_stdout": stdout[-4000:],
                "probe_stderr": stderr[-4000:],
                "proof_pass": bool(isinstance(proof, dict) and proof.get("pass") is True),
                "visible_text_contains_expected": item["proof_text"].lower() in text.lower(),
            }
        )
    return surfaces


def run_surface_probe(out_path: Path, url_prefix: str = "") -> tuple[int, str, str]:
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
    return proc.returncode, proc.stdout, proc.stderr


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
    transcript = find_transcript(script)
    transcript_sha = hashlib.sha256(transcript.encode("utf-8")).hexdigest()
    started_at = utc_now()

    reset_error = ""
    try:
        post_json(f"{args.engine_url}/api/listen/reset", {})
    except Exception as exc:
        reset_error = f"{type(exc).__name__}: {exc}"

    service_surfaces = capture_service_prechecks(script, stranger_dir)
    ui_result = drive_public_transcript_ui(args.public_url, transcript, stranger_dir)

    status = {}
    for _ in range(12):
        time.sleep(1.5)
        try:
            status = get_json(f"{args.engine_url}/api/listen/status")
        except Exception:
            status = {}
        pending = status.get("pending") if isinstance(status, dict) else {}
        if isinstance(pending, dict) and (
            pending.get("competent_decline") or pending.get("decline") or pending.get("proposal")
        ):
            break

    proof_path = stranger_dir / "screenshots" / "after_public_app_transcript_decline_proof.json"
    proof_rc = 0 if ui_result.get("ok") is True else 1
    proof_stdout = json.dumps(
        {"pass": ui_result.get("ok") is True, "out": str(proof_path)},
        sort_keys=True,
    )
    proof_stderr = ""
    proof = ui_result.get("decline_payload") if isinstance(ui_result.get("decline_payload"), dict) else {}
    proof_url = (((proof.get("proofs") or {}).get("url")) or "")
    proof_dom_path = (((proof.get("proofs") or {}).get("dom_path")) or "")
    proof_dom = Path(proof_dom_path).read_text(encoding="utf-8", errors="replace") if proof_dom_path and Path(proof_dom_path).exists() else ""
    pending = status.get("pending") if isinstance(status, dict) else {}
    pending_text = json.dumps(pending, sort_keys=True) if isinstance(pending, dict) else ""
    visible_decline = (
        proof.get("pass") is True
        and str(proof_url).startswith(args.public_url.rstrip("/"))
        and (
            "Cannot safely act" in proof_dom
            or "can't safely handle" in proof_dom
            or "cannot prove" in proof_dom
            or "competent_decline" in pending_text
        )
    )
    ok = (
        proof_rc == 0
        and proof.get("pass") is True
        and ui_result.get("ok") is True
        and bool((status.get("pending") or {}).get("proposal") if isinstance(status, dict) else False)
        and visible_decline
    )
    recent = status.get("recent") if isinstance(status, dict) else []
    matching_recent = {}
    if isinstance(recent, list):
        for item in recent:
            if isinstance(item, dict) and item.get("transcript") == transcript:
                matching_recent = item
                break
    pending_summary = {}
    if isinstance(pending, dict):
        pending_summary = {
            "proposal": pending.get("proposal"),
            "decline": pending.get("decline"),
            "competent_decline": pending.get("competent_decline"),
            "intent": pending.get("intent"),
        }

    result = {
        "schema": "anticipy.v7.deterministic_transcript_driver",
        "stranger_id": stranger_dir.name,
        "generated_at": utc_now(),
        "started_at": started_at,
        "ok": ok,
        "driver_failed": not ok,
        "driver_exit_code": 0 if ok else 1,
        "failure_phase": "" if ok else "deterministic-transcript-visible-proof",
        "persona_file": str(args.persona_file),
        "script_file": str(args.script_file),
        "engine_url": args.engine_url,
        "public_url": args.public_url,
        "reset_error": reset_error,
        "input_mode": "transcript_paste",
        "source_mode": "transcript_upload",
        "source": "transcript-upload",
        "post_transcript_boundary_source": "asr-transcript",
        "submitted_through_public_app_ui": True,
        "visible_ui_driver": "chrome_extension_native_messaging_real_chrome_active_tab",
        "transcript": transcript,
        "transcript_boundary": transcript,
        "transcript_boundary_chars": len(transcript),
        "transcript_boundary_sha256": transcript_sha,
        "ui_submission": ui_result,
        "status_after_sanitized": {
            "pending": pending_summary,
            "matching_recent": matching_recent,
            "recent_count": len(recent) if isinstance(recent, list) else 0,
        },
        "public_surface_after": {
            "proof_path": str(proof_path),
            "proof_pass": bool(proof.get("pass") is True),
            "url": proof_url,
            "surface": "anticipy",
        },
        "visible_surface_proof_path": str(proof_path),
        "service_surfaces": service_surfaces,
        "service_surface": (
            next((surface for surface in service_surfaces if surface.get("proof_pass")), {})
        ),
        "visible_surface_proof_paths": [
            *[
                str(surface.get("proof_path"))
                for surface in service_surfaces
                if surface.get("proof_pass") and surface.get("proof_path")
            ],
            str(proof_path),
        ],
        "visible_surface_proof": {
            "pass": proof.get("pass"),
            "surface_path": proof.get("surface_path"),
            "url": proof_url,
            "dom_path": proof_dom_path,
            "screenshot_path": (proof.get("proofs") or {}).get("screenshot_path"),
            "uses_chrome_real_clone": proof.get("uses_chrome_real_clone"),
            "direct_browser_cdp": proof.get("direct_browser_cdp"),
        },
        "visible_decline": visible_decline,
        "proof_stdout": proof_stdout,
        "proof_stderr": proof_stderr,
    }
    write_json(stranger_dir / "driver_result.json", result)
    print(json.dumps({"ok": ok, "out": str(stranger_dir / "driver_result.json")}, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
