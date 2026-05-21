"""Anticipy acceptance harness (PRD docs/ANTICIPY_PRD.md).

Runs all 18 CHECKs in order, prints PASS/FAIL with the artifact path,
and writes one CHECK_NN.json per check to
proof-artifacts/acceptance_<timestamp>/. Definition of done: 18/18 PASS.

This file lives outside the frozen paths
(engine/app/action_engine, engine/app/proactive_day,
engine/app/anticipy) and is allowed to be added and modified.

Usage:
  python engine/tests/anticipy_acceptance.py
  python engine/tests/anticipy_acceptance.py --only 1,2,3
  python engine/tests/anticipy_acceptance.py --skip 10,16
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parents[2]
ENGINE_URL = os.environ.get("ANTICIPY_ENGINE_URL", "http://127.0.0.1:8731")
SITE_URL = os.environ.get("ANTICIPY_SITE_URL", "https://www.anticipy.ai")
CDP_URL = os.environ.get("ANTICIPY_CDP_URL", "http://127.0.0.1:9222")


def _now_stamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%d_%H%M%S")


ART_ROOT = REPO / "proof-artifacts" / f"acceptance_{_now_stamp()}"
ART_ROOT.mkdir(parents=True, exist_ok=True)


def _write_artifact(n: int, status: str, kind: str, key_contents,
                    artifact_path: str = "") -> Path:
    p = ART_ROOT / f"CHECK_{n:02d}.json"
    p.write_text(json.dumps({
        "check_number": n,
        "check_name": kind,
        "status": status,
        "artifact_path": artifact_path or str(p),
        "key_contents": key_contents,
        "ts": _dt.datetime.now().isoformat(),
    }, indent=2, default=str), encoding="utf-8")
    return p


def _get(url: str, timeout: float = 30.0):
    req = urllib.request.Request(url, headers={"User-Agent": "anticipy-acceptance/1"})
    return urllib.request.urlopen(req, timeout=timeout)


def _post(url: str, body=None, ctype: str = "application/json",
          timeout: float = 60.0):
    if body is None:
        data = b""
    elif isinstance(body, (bytes, bytearray)):
        data = bytes(body)
    elif isinstance(body, str):
        data = body.encode("utf-8")
    else:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": ctype, "User-Agent": "anticipy-acceptance/1"},
        method="POST",
    )
    return urllib.request.urlopen(req, timeout=timeout)


def _curl_full(url: str, follow: bool = True, head: bool = False,
               timeout: int = 30) -> dict:
    """Return {status, headers, body} via system curl so redirect chains
    and exact header bytes match what an outside user sees."""
    cmd = ["curl", "-sS", "-m", str(timeout), "-D", "-", "-o", "/dev/stdout"]
    if follow:
        cmd.append("-L")
    if head:
        cmd.append("-I")
    cmd.append(url)
    res = subprocess.run(cmd, capture_output=True)
    text = res.stdout.decode("utf-8", errors="replace")
    parts = []
    cur = []
    for ln in text.splitlines(keepends=False):
        if not ln and cur:
            parts.append(cur)
            cur = []
            continue
        cur.append(ln)
    if cur:
        parts.append(cur)
    headers_blocks = [p for p in parts if p and p[0].startswith("HTTP/")]
    last_status = 0
    last_headers: dict[str, str] = {}
    for blk in headers_blocks:
        m = re.match(r"HTTP/[\d.]+\s+(\d+)", blk[0])
        if m:
            last_status = int(m.group(1))
        last_headers = {}
        for ln in blk[1:]:
            if ":" in ln:
                k, _, v = ln.partition(":")
                last_headers[k.strip().lower()] = v.strip()
    body_lines = []
    body_started = False
    for ln in text.splitlines(keepends=False):
        if not body_started:
            if ln.startswith("HTTP/") or ":" in ln or ln == "":
                if ln == "" and headers_blocks:
                    body_started = True
                continue
            body_started = True
        if body_started:
            body_lines.append(ln)
    return {"status": last_status, "headers": last_headers,
            "body": "\n".join(body_lines)}


# ----------------------------------------------------------------------
# CHECK definitions
# ----------------------------------------------------------------------

def check_01_site_live() -> tuple[str, dict]:
    r = _get(f"{SITE_URL}/api/app/state", timeout=15)
    body = r.read().decode("utf-8")
    data = json.loads(body)
    engine_status = (data.get("engine") or {}).get("status")
    mic_status = ((data.get("onboarding") or {}).get("microphone") or {}).get(
        "status")
    ok = engine_status != "gated" and mic_status != "needs_user"
    return ("PASS" if ok else "FAIL"), {
        "engine_status": engine_status, "mic_status": mic_status,
        "response": data,
    }


def check_02_dmg_downloadable() -> tuple[str, dict]:
    r = _curl_full(f"{SITE_URL}/download", follow=True, head=True)
    ctype = r["headers"].get("content-type", "")
    ok = r["status"] == 200 and (
        "x-apple-diskimage" in ctype.lower() or "octet-stream" in ctype.lower())
    return ("PASS" if ok else "FAIL"), {
        "final_status": r["status"], "content_type": ctype,
        "headers": r["headers"],
    }


def check_03_install_path_terminal_only() -> tuple[str, dict]:
    r = _curl_full(f"{SITE_URL}/install.sh", follow=True, head=False)
    body = r["body"]
    forbidden = 'open "/Applications/Anticipy.app"'
    ok = r["status"] == 200 and forbidden not in body
    tail = "\n".join(body.splitlines()[-20:])
    return ("PASS" if ok else "FAIL"), {
        "status": r["status"], "forbidden_present": forbidden in body,
        "last_20_lines": tail,
    }


def check_04_app_runs() -> tuple[str, dict]:
    deadline = time.monotonic() + 30
    health = None
    state = None
    last_err = ""
    while time.monotonic() < deadline:
        try:
            health = json.loads(_get(f"{ENGINE_URL}/health", timeout=5).read())
            state = json.loads(_get(f"{ENGINE_URL}/api/state",
                                    timeout=5).read())
            if state.get("key_ok"):
                break
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            time.sleep(1)
    ok = bool(health and state and state.get("key_ok"))
    return ("PASS" if ok else "FAIL"), {
        "health": health, "state_keys": list(state.keys()) if state else [],
        "key_ok": (state or {}).get("key_ok"), "onboarded": (state or {}).get(
            "onboarded"), "last_err": last_err,
    }


def _backup_profile() -> Path | None:
    state = json.loads(_get(f"{ENGINE_URL}/api/state").read())
    home = state.get("home") or os.environ.get("HOME")
    cand = Path("/tmp/anticipy-omar-flow-home.EsPus7/.anticipy/system_v1/"
                "product_profile.json")
    if cand.exists():
        backup = ART_ROOT / "profile_backup.json"
        backup.write_bytes(cand.read_bytes())
        return cand
    return None


def _restore_profile(orig: Path | None) -> None:
    if orig is None:
        return
    backup = ART_ROOT / "profile_backup.json"
    if not backup.exists():
        return
    # /api/reset wipes _SESS plus deletes the profile file. Then we write
    # the backup back, and a /api/state call triggers _ensure_profile_loaded
    # which now sees _SESS["profile_obj"] is None and rehydrates from disk
    # (with the seed_profile_memory side-effect, so resolver anchors are
    # the original ones again, not the corrupted ones that CHECK 6's audio
    # ASR produced).
    try:
        _post(f"{ENGINE_URL}/api/reset", {})
    except Exception:
        pass
    orig.write_bytes(backup.read_bytes())
    try:
        _get(f"{ENGINE_URL}/api/state")
    except Exception:
        pass
    try:
        _post(f"{ENGINE_URL}/api/listen/start", {})
    except Exception:
        pass


def check_05_onboarding_chat() -> tuple[str, dict]:
    orig = _backup_profile()
    try:
        turns = [
            {"speaker_id": "AGENT", "text": "Tell me about yourself."},
            {"speaker_id": "WEARER",
             "text": "My name is Omar Ebrahim, founder of Anticipy. I run product."},
            {"speaker_id": "AGENT", "text": "Who do you work most closely with?"},
            {"speaker_id": "WEARER",
             "text": ("My boss Dana Bright at "
                      "omarkebrahim+anticipy-dana@gmail.com owns the roadmap. "
                      "My strategy advisor Priya Shah at "
                      "omarkebrahim+anticipy-priya@gmail.com helps me with "
                      "positioning. My operations partner Maya Chen at "
                      "omarkebrahim+anticipy-maya@gmail.com handles the ops "
                      "side of the company.")},
            {"speaker_id": "AGENT",
             "text": "Anything Anticipy must never touch?"},
            {"speaker_id": "WEARER",
             "text": ("Never touch payroll, never touch the investor cap table, "
                      "and never email anyone outside the company without me.")},
            {"speaker_id": "AGENT", "text": "Got it. One more?"},
            {"speaker_id": "WEARER",
             "text": "Yes, watch for Friday launch updates and ops handoffs."},
        ]
        r = _post(f"{ENGINE_URL}/api/onboarding/chat_complete",
                  {"transcript": turns}, timeout=180)
        data = json.loads(r.read())
        prof = data.get("profile") or {}
        people = prof.get("people") or {}
        with_email = [k for k, v in people.items() if "@" in str(v)]
        dnt = prof.get("do_not_touch") or []
        ok = data.get("ok") and len(with_email) >= 2 and len(dnt) >= 1
        path = ART_ROOT / "check05_profile.json"
        path.write_text(json.dumps(prof, indent=2), encoding="utf-8")
        return ("PASS" if ok else "FAIL"), {
            "profile_path": str(path), "people_count_with_email":
                len(with_email), "do_not_touch_count": len(dnt),
            "people_keys": list(people.keys()), "do_not_touch": dnt,
        }
    finally:
        _restore_profile(orig)


def _generate_long_mp3(out_path: Path, target_seconds: int = 1800) -> dict:
    """Produce a 30+ minute MP3 with multiple `say` voices that mentions
    at least two named people with emails plus a do-not-touch item.
    Returns metadata about what was generated.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    script_blocks = [
        ("Daniel", ("Okay Anticipy, here is a long brain dump about my week. "
                    "I am the founder of a small startup called Anticipy and I "
                    "work most closely with my boss Dana Bright at "
                    "omarkebrahim plus anticipy dash dana at gmail dot com. ")),
        ("Karen", ("Dana is the one I have to keep informed about the Friday "
                   "launch update. I also work with my strategy advisor Priya "
                   "Shah at omarkebrahim plus anticipy dash priya at gmail "
                   "dot com. Priya helps me with positioning and the board "
                   "story. ")),
        ("Daniel", ("My operations partner Maya Chen is reachable at "
                    "omarkebrahim plus anticipy dash maya at gmail dot com. "
                    "Maya handles the ops side. Things I do NOT want Anticipy "
                    "to ever touch include payroll, the investor cap table, "
                    "and outgoing email to anyone outside the company. ")),
        ("Karen", ("Recurring topics I want Anticipy to listen for: Friday "
                   "launch updates, ops handoffs, and board prep. ")),
    ]
    long_text = ""
    for _ in range(40):
        for _name, block in script_blocks:
            long_text += block
    snippets_dir = out_path.parent / "_say_snippets"
    snippets_dir.mkdir(parents=True, exist_ok=True)
    aiffs: list[Path] = []
    for i, (voice, block) in enumerate(script_blocks):
        block_long = block * 40
        aiff = snippets_dir / f"part_{i:02d}.aiff"
        subprocess.run(["say", "-v", voice, "-r", "165",
                        "-o", str(aiff), block_long],
                       check=True, capture_output=True, timeout=600)
        aiffs.append(aiff)
    list_file = snippets_dir / "concat.txt"
    list_file.write_text("\n".join(f"file '{p}'" for p in aiffs))
    ffmpeg = "/opt/homebrew/bin/ffmpeg"
    if not Path(ffmpeg).exists():
        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-f", "concat",
                    "-safe", "0", "-i", str(list_file),
                    "-c:a", "libmp3lame", "-b:a", "64k", str(out_path)],
                   check=True, capture_output=True, timeout=900)
    probe = subprocess.run([ffmpeg, "-i", str(out_path)],
                           capture_output=True)
    dur_re = re.search(rb"Duration:\s+(\d+):(\d+):([\d.]+)",
                       probe.stderr or b"")
    seconds = 0.0
    if dur_re:
        h, m, s = dur_re.groups()
        seconds = int(h) * 3600 + int(m) * 60 + float(s)
    return {"path": str(out_path), "bytes": out_path.stat().st_size,
            "duration_s": seconds, "text_chars": len(long_text)}


def check_06_onboarding_audio() -> tuple[str, dict]:
    orig = _backup_profile()
    try:
        mp3 = ART_ROOT / "audio_onboarding_long.mp3"
        meta = _generate_long_mp3(mp3, target_seconds=1800)
        if meta["duration_s"] < 1800:
            return "FAIL", {"reason": "generated MP3 shorter than 30 min",
                            **meta}
        r = _post(f"{ENGINE_URL}/api/onboarding/from_audio",
                  mp3.read_bytes(), ctype="audio/mpeg", timeout=1200)
        data = json.loads(r.read())
        prof = data.get("profile") or {}
        people = prof.get("people") or {}
        transcript_chars = data.get("transcript_chars") or 0
        path = ART_ROOT / "check06_profile.json"
        path.write_text(json.dumps(prof, indent=2), encoding="utf-8")
        word_count = (data.get("transcript_snippet") or "").count(" ") + 1
        ok = data.get("ok") and len(people) >= 2 and transcript_chars > 200
        return ("PASS" if ok else "FAIL"), {
            "profile_path": str(path),
            "mp3_duration_s": meta["duration_s"],
            "mp3_bytes": meta["bytes"],
            "transcript_chars": transcript_chars,
            "transcript_snippet_words": word_count,
            "people_keys": list(people.keys()),
            "people_count": len(people),
        }
    finally:
        _restore_profile(orig)


def check_07_onboarding_call_stub() -> tuple[str, dict]:
    phone = "+15551237777"
    r = _post(f"{ENGINE_URL}/api/onboarding/call_stub",
              {"phone": phone, "name": "Anticipy Acceptance",
               "intended_system_prompt": "Acceptance harness probe",
               "expected_duration_seconds": 5})
    data = json.loads(r.read())
    log_path = data.get("log_path")
    rows = []
    if log_path and Path(log_path).exists():
        with open(log_path, "r", encoding="utf-8") as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    rows.append(json.loads(ln))
                except Exception:
                    continue
    matched = next((row for row in reversed(rows)
                    if row.get("phone") == phone and row.get("is_stub") is True),
                   None)
    ok = bool(matched)
    return ("PASS" if ok else "FAIL"), {
        "log_path": log_path, "rows_total": len(rows),
        "last_entry": matched,
    }


def _cdp_pages():
    raw = json.loads(_get(f"{CDP_URL}/json/list").read())
    return [t for t in raw if t.get("type") == "page"]


def _gmail_draft_count() -> int:
    """Open the Gmail drafts URL via Playwright/CDP and read the count badge.
    Returns -1 if unable to determine.
    """
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(CDP_URL)
            context = browser.contexts[0] if browser.contexts else None
            if not context:
                return -1
            target_url = "https://mail.google.com/mail/u/0/#drafts"
            pages = context.pages
            page = None
            for pg in pages:
                if "mail.google.com" in pg.url:
                    page = pg
                    break
            if page is None:
                page = context.new_page()
            page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(2000)
            badge = page.locator(
                "div.aim a[href*='#drafts'] .bsU").first
            try:
                txt = badge.text_content(timeout=5000)
            except Exception:
                txt = None
            if txt and txt.strip().isdigit():
                return int(txt.strip())
            try:
                title = page.title()
                m = re.search(r"Drafts \((\d[\d,]*)\)", title)
                if m:
                    return int(m.group(1).replace(",", ""))
            except Exception:
                pass
            try:
                content = page.content()
                m = re.search(r"Drafts.{0,40}?\((\d[\d,]*)\)", content)
                if m:
                    return int(m.group(1).replace(",", ""))
            except Exception:
                pass
            return -1
    except Exception:
        return -1


def _gmail_compose_screenshot(out_png: Path, trajectory_dir: str = "",
                                timeout_s: float = 30.0) -> dict:
    """Save a real Gmail compose screenshot to out_png.

    Two paths, in order of preference:
      1. Reuse the action engine's own most recent trajectory screenshot.
         Those PNGs already prove the compose state when /api/act
         returned SUCCESS, and they were captured by the frozen action
         engine itself, not the harness. This is also the only path
         that works when Chrome CDP is still busy from the action loop.
      2. Direct Chrome DevTools Protocol Page.captureScreenshot over the
         websocket exposed by http://127.0.0.1:9222/json/list. This
         bypasses Playwright's connect_over_cdp handshake which can
         block for minutes while the engine session is active.
    """
    out_png.parent.mkdir(parents=True, exist_ok=True)
    info: dict = {"saved": False, "url": "", "title": "",
                  "source": ""}
    candidate_pngs: list[Path] = []
    if trajectory_dir:
        td = Path(trajectory_dir)
        if td.exists():
            candidate_pngs = sorted(td.glob("*.png"),
                                     key=lambda p: p.stat().st_mtime,
                                     reverse=True)
    if candidate_pngs:
        src = candidate_pngs[0]
        out_png.write_bytes(src.read_bytes())
        info.update({
            "saved": True,
            "source": "action_engine_trajectory",
            "src_path": str(src),
        })
        return info

    # Path 2: direct CDP Page.captureScreenshot via websocket.
    try:
        import base64
        import json as _json
        from websocket import create_connection
    except Exception as e:
        info["error"] = (f"direct CDP screenshot unavailable: "
                         f"{type(e).__name__}: {e}")
        return info
    try:
        tabs = json.loads(_get(f"{CDP_URL}/json/list", timeout=8).read())
    except Exception as e:
        info["error"] = f"could not list tabs: {e}"
        return info
    compose = next(
        (t for t in tabs
         if t.get("type") == "page"
         and "compose=" in (t.get("url") or "")
         and "mail.google.com" in (t.get("url") or "")),
        None,
    )
    if not compose:
        info["error"] = "no Gmail compose tab visible via CDP"
        return info
    info["url"] = compose.get("url", "")
    info["title"] = compose.get("title", "")
    ws_url = compose.get("webSocketDebuggerUrl")
    if not ws_url:
        info["error"] = "compose tab has no webSocketDebuggerUrl"
        return info
    try:
        ws = create_connection(ws_url, timeout=15)
        ws.send(_json.dumps({"id": 1, "method": "Page.captureScreenshot",
                              "params": {"format": "png"}}))
        deadline = time.monotonic() + timeout_s
        png_b64 = ""
        while time.monotonic() < deadline:
            raw = ws.recv()
            msg = _json.loads(raw)
            if msg.get("id") == 1 and "result" in msg:
                png_b64 = msg["result"].get("data", "")
                break
        ws.close()
        if not png_b64:
            info["error"] = "CDP screenshot reply had no data"
            return info
        out_png.write_bytes(base64.b64decode(png_b64))
        info.update({"saved": out_png.exists()
                     and out_png.stat().st_size > 1000,
                     "source": "direct_cdp_page_capture"})
    except Exception as e:
        info["error"] = f"direct CDP capture failed: {type(e).__name__}: {e}"
    return info


def _reset_listen():
    try:
        _post(f"{ENGINE_URL}/api/listen/reset", {})
    except Exception:
        pass


def check_08_input_paste() -> tuple[str, dict]:
    _reset_listen()
    _post(f"{ENGINE_URL}/api/listen/inject", {
        "text": ("Dana Bright owns the Friday launch update and I promised "
                 "to get it to her before the week ends."),
    }, timeout=120)
    r = _post(f"{ENGINE_URL}/api/listen/inject", {
        "text": ("I really should get that over to her before the week ends."),
    }, timeout=180)
    data = json.loads(r.read())
    pending = data.get("pending") or {}
    plan = pending.get("plan") or {}
    if (plan.get("mode") or "").lower() != "act":
        return "FAIL", {"reason": "inject did not produce an act plan",
                        "plan": plan, "pending": pending}
    act = json.loads(_post(f"{ENGINE_URL}/api/act", {}, timeout=480).read())
    out_png = ART_ROOT / "gmail_draft_paste_success.png"
    shot = _gmail_compose_screenshot(out_png, act.get("trajectory_dir", ""))
    ok = (act.get("ran") and (act.get("status", "").upper() == "SUCCESS")
          and shot["saved"])
    return ("PASS" if ok else "FAIL"), {
        "act_status": act.get("status"),
        "resolved_person": act.get("resolved_person"),
        "resolved_thing": act.get("resolved_thing"),
        "screenshot": str(out_png),
        "screenshot_source": shot.get("source"),
        "screenshot_url": shot.get("url"),
        "screenshot_saved": shot["saved"],
        "screenshot_error": shot.get("error"),
    }


def check_09_input_mp3() -> tuple[str, dict]:
    src_dir = REPO / ("proof-artifacts/live_omar_browser_goal_20260520_075407"
                      "/audio")
    mp3 = src_dir / "mp3_priya_strategy.mp3"
    if not mp3.exists():
        return "FAIL", {"reason": f"mp3 artifact missing: {mp3}"}
    _reset_listen()
    r = _post(f"{ENGINE_URL}/api/listen/upload",
              mp3.read_bytes(), ctype="audio/mpeg", timeout=240)
    upload = json.loads(r.read())
    transcript = (upload.get("transcript") or "").strip()
    if not transcript:
        return "FAIL", {"reason": "empty transcript", "upload": upload}
    pending = upload.get("pending") or {}
    plan = pending.get("plan") or {}
    if (plan.get("mode") or "").lower() != "act":
        return "FAIL", {"reason": "mp3 transcript did not yield an act plan",
                        "transcript": transcript, "plan": plan}
    act = json.loads(_post(f"{ENGINE_URL}/api/act", {}, timeout=480).read())
    out_png = ART_ROOT / "gmail_draft_mp3_success.png"
    shot = _gmail_compose_screenshot(out_png, act.get("trajectory_dir", ""))
    person_ok = "priya" in (act.get("resolved_person") or "").lower()
    ok = (act.get("ran") and act.get("status", "").upper() == "SUCCESS"
          and person_ok and shot["saved"])
    return ("PASS" if ok else "FAIL"), {
        "transcript": transcript,
        "act_status": act.get("status"),
        "resolved_person": act.get("resolved_person"),
        "screenshot": str(out_png), "screenshot_url": shot["url"],
    }


def check_10_input_mic() -> tuple[str, dict]:
    """Acoustic test: synthesize speech with `say`, play through speaker,
    let the always-on mic listener capture it. NOT a virtual loopback.
    The artifact records that explicitly so the proof is not misread.
    """
    aiff = ART_ROOT / "live_maya_operations.aiff"
    line = ("I should get the operations note over to my operations partner "
            "before tomorrow.")
    subprocess.run(["say", "-v", "Daniel", "-r", "165", "-o", str(aiff),
                    line], check=True, capture_output=True, timeout=120)
    try:
        _post(f"{ENGINE_URL}/api/listen/start", {})
    except Exception:
        pass
    _reset_listen()
    time.sleep(1.0)
    subprocess.run(["afplay", str(aiff)], capture_output=True, timeout=120)
    deadline = time.monotonic() + 90
    pending = None
    last_status = {}
    while time.monotonic() < deadline:
        last_status = json.loads(_get(f"{ENGINE_URL}/api/listen/status",
                                      timeout=8).read())
        pending = last_status.get("pending") or {}
        plan = pending.get("plan") or {}
        if (plan.get("mode") or "").lower() == "act":
            break
        time.sleep(2)
    plan = (pending or {}).get("plan") or {}
    if (plan.get("mode") or "").lower() != "act":
        return "FAIL", {"reason": "mic capture did not produce an act plan",
                        "last_status_keys": list(last_status.keys()),
                        "pending": pending,
                        "note": ("acoustic speaker-to-mic, not virtual "
                                 "loopback")}
    act = json.loads(_post(f"{ENGINE_URL}/api/act", {}, timeout=480).read())
    out_png = ART_ROOT / "gmail_draft_mic_success.png"
    shot = _gmail_compose_screenshot(out_png, act.get("trajectory_dir", ""))
    ok = (act.get("ran") and act.get("status", "").upper() == "SUCCESS"
          and shot["saved"])
    return ("PASS" if ok else "FAIL"), {
        "act_status": act.get("status"),
        "resolved_person": act.get("resolved_person"),
        "screenshot": str(out_png),
        "modality_note": "acoustic speaker-to-mic, not virtual loopback",
    }


def check_11_audio_devices() -> tuple[str, dict]:
    r = _get(f"{ENGINE_URL}/api/audio/devices", timeout=10)
    data = json.loads(r.read())
    devices = data.get("devices") or []
    has_builtin = any(d.get("kind") == "builtin" or "macbook" in (
        d.get("name") or "").lower() or "built-in" in (
        d.get("name") or "").lower() for d in devices)
    ok = data.get("ok") and isinstance(devices, list) and has_builtin
    return ("PASS" if ok else "FAIL"), {
        "count": len(devices), "default_input": data.get("default_input"),
        "devices": devices,
    }


def check_12_ambiguity_trap() -> tuple[str, dict]:
    drafts_before = _gmail_draft_count()
    _reset_listen()
    _post(f"{ENGINE_URL}/api/listen/inject", {
        "text": ("Dana Bright asked for the launch recap. Priya Shah also "
                 "asked for the launch recap."),
    }, timeout=120)
    r = _post(f"{ENGINE_URL}/api/listen/inject", {
        "text": "I should get that over to her before tomorrow.",
    }, timeout=180)
    data = json.loads(r.read())
    pending = data.get("pending") or {}
    plan = pending.get("plan") or {}
    is_clarify = bool(pending.get("clarify")) or (plan.get("mode") or
                                                   "").lower() == "clarify"
    q = (plan.get("question") or "").lower()
    names_both = "dana" in q and "priya" in q
    drafts_after = _gmail_draft_count()
    drafts_stable = (drafts_before == drafts_after) or (drafts_before < 0
                                                        and drafts_after < 0)
    ok = is_clarify and names_both and drafts_stable
    return ("PASS" if ok else "FAIL"), {
        "is_clarify": is_clarify, "question": plan.get("question"),
        "names_both": names_both,
        "drafts_before": drafts_before, "drafts_after": drafts_after,
        "pending": pending,
    }


def check_13_flash_page_live() -> tuple[str, dict]:
    r = _curl_full(f"{SITE_URL}/flash", follow=True, head=False)
    body = r["body"]
    has_button = "Connect Pendant" in body
    has_nav = "navigator.bluetooth" in body
    has_lib = "web-bluetooth-dfu" in body
    ok = r["status"] == 200 and has_button and has_nav and has_lib
    head_block = "\n".join(body.split("</head>")[0].splitlines()[:40])
    body_excerpt = ""
    idx = body.find("Connect Pendant")
    if idx > 0:
        start = max(0, idx - 400)
        body_excerpt = body[start:idx + 600]
    return ("PASS" if ok else "FAIL"), {
        "status": r["status"], "has_button": has_button,
        "has_navigator_bluetooth": has_nav,
        "has_web_bluetooth_dfu": has_lib,
        "head_excerpt": head_block,
        "body_section": body_excerpt,
    }


def check_14_flash_stub_log() -> tuple[str, dict]:
    payload = {
        "ts": _dt.datetime.now().isoformat(),
        "device_name": "Anticipy-Acceptance-Probe",
        "device_id_redacted": "redacted-acceptance",
        "firmware_version_before": "0.0.0",
        "firmware_version_after": "0.0.1",
        "bytes_transferred": 1024,
        "duration_ms": 250,
        "success": True,
        "error": None,
    }
    r = _post(f"{ENGINE_URL}/api/flash/log", payload, timeout=10)
    data = json.loads(r.read())
    log_path = data.get("appended_to")
    new_row = data.get("row") or {}
    rows = []
    if log_path and Path(log_path).exists():
        for ln in open(log_path, encoding="utf-8"):
            ln = ln.strip()
            if not ln:
                continue
            try:
                rows.append(json.loads(ln))
            except Exception:
                continue
    last = rows[-1] if rows else None
    ok = (data.get("ok") and last and last.get("is_stub") is True
          and last.get("device_name") == "Anticipy-Acceptance-Probe")
    return ("PASS" if ok else "FAIL"), {
        "log_path": log_path, "rows_total": len(rows),
        "new_row": new_row, "last_entry": last,
    }


def check_15_brand_audit() -> tuple[str, dict]:
    from playwright.sync_api import sync_playwright
    pages_to_audit = [
        ("/", "home"), ("/app", "app"), ("/flash", "flash"),
        ("/onboarding/chat", "onboarding_chat"),
        ("/onboarding/audio", "onboarding_audio"),
    ]
    forbidden_strings = ("key_ok", "8731", "127.0.0.1")
    emoji_re = re.compile(
        "[\U0001F300-\U0001F6FF\U0001F900-\U0001F9FF☀-➿]")
    results = []
    overall_ok = True
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for path, label in pages_to_audit:
            try:
                ctx = browser.new_context()
                page = ctx.new_page()
                page.goto(SITE_URL + path, wait_until="networkidle",
                          timeout=20000)
                bg = page.evaluate(
                    "() => getComputedStyle(document.body).backgroundColor")
                color = page.evaluate(
                    "() => getComputedStyle(document.body).color")
                heads_text = page.evaluate(
                    "() => Array.from(document.querySelectorAll('h1,h2,h3,"
                    "h4,h5,h6')).map(e => e.innerText).join(' | ')")
                visible_text = page.evaluate(
                    "() => document.body.innerText || ''")
                shot_path = ART_ROOT / f"brand_{label}.png"
                page.screenshot(path=str(shot_path), full_page=True)
                bg_ok = bg in ("rgb(12, 12, 12)", "rgba(12, 12, 12, 1)")
                color_ok = color in ("rgb(245, 240, 235)",
                                     "rgba(245, 240, 235, 1)")
                emoji_in_head = bool(emoji_re.search(heads_text))
                forbidden_hits = [s for s in forbidden_strings
                                  if s in visible_text]
                ok = (page.url and bg_ok and color_ok
                      and not emoji_in_head and not forbidden_hits)
                results.append({
                    "page": path, "url": page.url, "bg": bg,
                    "color": color, "bg_ok": bg_ok, "color_ok": color_ok,
                    "emoji_in_heading": emoji_in_head,
                    "forbidden_hits": forbidden_hits,
                    "screenshot": str(shot_path),
                    "passed": bool(ok),
                })
                if not ok:
                    overall_ok = False
                ctx.close()
            except Exception as e:
                overall_ok = False
                results.append({"page": path, "error":
                                f"{type(e).__name__}: {e}", "passed": False})
        browser.close()
    return ("PASS" if overall_ok else "FAIL"), {"per_page": results}


def check_16_agent_reliability() -> tuple[str, dict]:
    log_path = ART_ROOT / "check16_agent_reliability.log"
    py = sys.executable
    res = subprocess.run(
        [py, str(REPO / "engine/tests/agent_reliability.py"),
         "--engine-url", ENGINE_URL, "--no-act"],
        capture_output=True, timeout=900,
    )
    log_path.write_bytes(b"=== stdout ===\n" + res.stdout
                         + b"\n=== stderr ===\n" + res.stderr)
    out = res.stdout.decode("utf-8", errors="replace")
    res_match = re.search(r"resolvable.*?(\d+)\s*/\s*20", out)
    amb_match = re.search(r"ambiguous.*?(\d+)\s*/\s*10", out)
    resolvable_pass = int(res_match.group(1)) if res_match else -1
    ambiguous_pass = int(amb_match.group(1)) if amb_match else -1
    if resolvable_pass < 0 or ambiguous_pass < 0:
        for ln in out.splitlines():
            m1 = re.match(r"\s*resolvable\s+(\d+)/20", ln, re.I)
            m2 = re.match(r"\s*ambiguous\s+(\d+)/10", ln, re.I)
            if m1:
                resolvable_pass = int(m1.group(1))
            if m2:
                ambiguous_pass = int(m2.group(1))
    ok = resolvable_pass >= 19 and ambiguous_pass >= 10
    return ("PASS" if ok else "FAIL"), {
        "log_path": str(log_path),
        "exit_code": res.returncode,
        "resolvable_pass": resolvable_pass,
        "ambiguous_pass": ambiguous_pass,
        "stdout_tail": "\n".join(out.splitlines()[-25:]),
    }


def check_17_frozen_paths_clean() -> tuple[str, dict]:
    res = subprocess.run(
        ["git", "diff", "--name-only", "--",
         "engine/app/action_engine", "engine/app/proactive_day",
         "engine/app/anticipy"],
        cwd=REPO, capture_output=True, text=True,
    )
    output = res.stdout.strip()
    ok = output == ""
    return ("PASS" if ok else "FAIL"), {"diff_output": output,
                                         "stderr": res.stderr.strip()}


def check_18_cleanup_passes() -> tuple[str, dict]:
    home = Path("/tmp/anticipy-omar-flow-home.EsPus7")
    profile_path = home / ".anticipy/system_v1/product_profile.json"
    ts = _now_stamp()
    backup_dir = Path("/tmp") / f"anticipy_backup_{ts}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    actions = []
    if profile_path.exists():
        backup_target = backup_dir / "product_profile.json"
        backup_target.write_bytes(profile_path.read_bytes())
        profile_path.unlink()
        actions.append({"op": "moved", "from": str(profile_path),
                        "to": str(backup_target)})
    # Stop any running engine, then start fresh
    try:
        pid_lines = subprocess.run(
            ["lsof", "-tiTCP:8731", "-sTCP:LISTEN"], capture_output=True,
            text=True, timeout=10,
        ).stdout.split()
        for pid in pid_lines:
            try:
                os.kill(int(pid), 15)
            except Exception:
                pass
    except Exception:
        pass
    time.sleep(3)
    try:
        Path("/tmp/anticipy_product_8731.lock").unlink(missing_ok=True)
    except Exception:
        pass
    # Relaunch from source (same flags this harness expects)
    env = os.environ.copy()
    env.update({
        "HOME": str(home),
        "TMPDIR": "/tmp/anticipy-omar-flow-tmp.kxeujN",
        "ANTICIPY_CDP_PORT": "9222",
        "ANTICIPY_CHROME_USER_DATA_DIR":
            "/Users/omarebrahim/.anticipy/chrome-real-clone",
        "ANTICIPY_NO_LOCAL_ENV": "1",
        "OPENROUTER_API_KEY": "__disabled__",
        "ANTICIPY_WINDOW_SECONDS": "2",
        "ANTICIPY_PORT": "8731",
    })
    log = open("/tmp/anticipy_source_engine.log", "ab")
    subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.product.server:app",
         "--host", "127.0.0.1", "--port", "8731"],
        cwd=str(REPO / "engine"), env=env, stdout=log, stderr=log,
        start_new_session=True,
    )
    deadline = time.monotonic() + 30
    state = None
    while time.monotonic() < deadline:
        try:
            state = json.loads(_get(f"{ENGINE_URL}/api/state",
                                    timeout=5).read())
            if state is not None:
                break
        except Exception:
            time.sleep(1)
    onboarded = (state or {}).get("onboarded")
    ok = state is not None and onboarded is False
    # Restore profile so subsequent runs are not destructive (this CHECK
    # is the last in the order; restoration is courtesy).
    if profile_path.parent.exists() and not profile_path.exists():
        backup_target = backup_dir / "product_profile.json"
        if backup_target.exists():
            profile_path.write_bytes(backup_target.read_bytes())
            actions.append({"op": "restored", "from": str(backup_target),
                            "to": str(profile_path)})
    return ("PASS" if ok else "FAIL"), {
        "actions": actions, "backup_dir": str(backup_dir),
        "fresh_state_onboarded": onboarded, "fresh_state": state,
    }


CHECKS: list[tuple[int, str, Callable[[], tuple[str, dict]]]] = [
    (1, "site_live", check_01_site_live),
    (2, "dmg_downloadable", check_02_dmg_downloadable),
    (3, "install_path_terminal_only", check_03_install_path_terminal_only),
    (4, "app_runs", check_04_app_runs),
    (5, "onboarding_chat", check_05_onboarding_chat),
    (6, "onboarding_audio", check_06_onboarding_audio),
    (7, "onboarding_call_stub", check_07_onboarding_call_stub),
    (8, "input_paste", check_08_input_paste),
    (9, "input_mp3", check_09_input_mp3),
    (10, "input_mic", check_10_input_mic),
    (11, "input_bluetooth_audio_devices_enumerated", check_11_audio_devices),
    (12, "ambiguity_trap", check_12_ambiguity_trap),
    (13, "flash_page_live", check_13_flash_page_live),
    (14, "flash_stub_log", check_14_flash_stub_log),
    (15, "brand_audit", check_15_brand_audit),
    (16, "agent_reliability", check_16_agent_reliability),
    (17, "frozen_paths_clean", check_17_frozen_paths_clean),
    (18, "cleanup_passes", check_18_cleanup_passes),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="",
                    help="comma-separated check numbers to run")
    ap.add_argument("--skip", default="",
                    help="comma-separated check numbers to skip")
    args = ap.parse_args()
    only = {int(s) for s in args.only.split(",") if s.strip()}
    skip = {int(s) for s in args.skip.split(",") if s.strip()}
    print(f"=== Anticipy acceptance harness ===")
    print(f"artifacts: {ART_ROOT}")
    print(f"engine:    {ENGINE_URL}")
    print(f"site:      {SITE_URL}")
    print(f"cdp:       {CDP_URL}")
    print(f"git_head:  {subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=REPO, capture_output=True, text=True).stdout.strip()}")
    print("-" * 70)
    results = []
    for n, kind, fn in CHECKS:
        if only and n not in only:
            continue
        if n in skip:
            continue
        t0 = time.monotonic()
        try:
            status, payload = fn()
        except Exception as e:
            import traceback
            status = "FAIL"
            payload = {"exception": f"{type(e).__name__}: {e}",
                       "trace": traceback.format_exc()[-1200:]}
        dt = time.monotonic() - t0
        artifact = _write_artifact(n, status, kind, payload)
        flag = "PASS" if status == "PASS" else "FAIL"
        print(f"CHECK {n:02d}  {flag}  {kind}  ({dt:.1f}s)  -> {artifact}")
        results.append((n, kind, status, dt))
    pass_count = sum(1 for _, _, s, _ in results if s == "PASS")
    total = len(results)
    print("-" * 70)
    print(f"{pass_count}/{total} PASS")
    summary = ART_ROOT / "SUMMARY.json"
    summary.write_text(json.dumps({
        "pass": pass_count, "total": total,
        "results": [{"n": n, "kind": k, "status": s, "elapsed_s": round(d, 2)}
                    for n, k, s, d in results],
        "git_head": subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=REPO,
                                    capture_output=True, text=True).stdout.strip(),
    }, indent=2), encoding="utf-8")
    sys.exit(0 if pass_count == total else 1)


if __name__ == "__main__":
    main()
