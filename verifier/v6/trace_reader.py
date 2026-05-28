#!/usr/bin/env python3
"""V6 multi-modal trace reader.

Reads user-visible surfaces only:
- Anticipy Chrome extension/native bridge for the user's real Chrome surface.
- Chrome CDP on port 9222 for legacy tabs, DOM text, and screenshots.
- macOS accessibility through osascript for native app window summaries.
- Terminal text through osascript.
- Engine logs as informational context, never as proof by themselves.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any


DEFAULT_PORT = int(os.environ.get("ANTICIPY_CDP_PORT", "9222"))

SURFACE_ALIASES = {
    "anticipy": "anticipy",
    "anticipy app": "anticipy",
    "app": "anticipy",
    "gmail": "gmail",
    "google mail": "gmail",
    "mail.google.com": "gmail",
    "google_sheets": "google_sheets",
    "google sheets": "google_sheets",
    "sheets": "google_sheets",
    "spreadsheet": "google_sheets",
    "spreadsheets": "google_sheets",
    "docs.google.com/spreadsheets": "google_sheets",
    "google_calendar": "google_calendar",
    "google calendar": "google_calendar",
    "calendar": "google_calendar",
    "calendar.google.com": "google_calendar",
    "slack": "slack",
    "notion": "notion",
    "linear": "linear",
    "hubspot": "crm",
    "app.hubspot.com": "crm",
    "salesforce": "crm",
    "crm": "crm",
    "canva": "canvas_design",
    "figma": "canvas_design",
    "canvas": "canvas_design",
    "design": "canvas_design",
    "amazon": "commerce",
    "opentable": "commerce",
    "resy": "commerce",
    "commerce": "commerce",
    "e-commerce": "commerce",
    "ecommerce": "commerce",
    "browser": "browser",
    "native": "native_ax",
    "native app": "native_ax",
    "native mac app": "native_ax",
    "mac app": "native_ax",
    "macos": "native_ax",
    "accessibility": "native_ax",
    "terminal": "terminal",
    "shell": "terminal",
}

SCRIPT_SURFACE_KEYS = {
    "surface",
    "surfaces",
    "source_surface",
    "source_surfaces",
    "action_surface",
    "action_surfaces",
    "target_surface",
    "target_surfaces",
    "primary_surface",
    "primary_surfaces",
    "user_surface",
    "user_surfaces",
    "visible_surface",
    "visible_surfaces",
    "expected_surface",
    "expected_surfaces",
    "expected_visible_surface",
    "expected_visible_surfaces",
    "proof_surface",
    "proof_surfaces",
    "verification_surface",
    "verification_surfaces",
    "script_surface",
    "script_surfaces",
    "app",
    "apps",
    "application",
    "applications",
    "service",
    "services",
    "target_app",
    "target_apps",
    "target_service",
    "target_services",
    "url",
    "urls",
    "domain",
    "domains",
}

SCRIPT_TEXT_KEYS = {
    "action",
    "actions",
    "ask",
    "command",
    "description",
    "expected",
    "goal",
    "instruction",
    "instructions",
    "intent",
    "input",
    "note",
    "notes",
    "prompt",
    "request",
    "scenario",
    "script",
    "step",
    "steps",
    "task",
    "text",
    "transcript",
    "utterance",
    "voice",
}

SCRIPT_RELEVANT_CONTAINERS = {
    "action",
    "actions",
    "flow",
    "flows",
    "interaction",
    "interactions",
    "moment",
    "moments",
    "scenario",
    "scenarios",
    "script",
    "step",
    "steps",
    "task",
    "tasks",
    "turn",
    "turns",
}

SCRIPT_SCOPE_NOISE_KEYS = {
    "baseline",
    "baselines",
    "browser_context",
    "browser_state",
    "breadth",
    "candidate_tabs",
    "carrier",
    "carriers",
    "category_counts",
    "cdp",
    "chrome",
    "chrome_state",
    "created_at",
    "embedding",
    "embeddings",
    "generated_at",
    "hard_category",
    "hard_categories",
    "history",
    "metadata",
    "meta",
    "observed_tabs",
    "persona",
    "recent_breadth",
    "recent_categories",
    "receipt",
    "receipts",
    "rolling_breadth",
    "rolling_breadth_metadata",
    "scores",
    "similarity",
    "stale_tabs",
    "tab_inventory",
    "tabs",
    "trace",
    "traces",
    "transport",
}

SCRIPT_SCOPE_NOISE_KEY_SUFFIXES = (
    "_metadata",
    "_meta",
    "_history",
    "_tabs",
    "_trace",
    "_traces",
)

GENERIC_CARRIER_SURFACES = {"browser"}


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def http_json(url: str, timeout: float = 5.0) -> Any:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read() or b"null")


class CdpSession:
    def __init__(self, ws_url: str):
        try:
            from websockets.sync.client import connect
        except Exception as exc:
            raise RuntimeError(f"websockets package unavailable: {exc}") from exc
        try:
            self.ws = connect(ws_url, max_size=16 * 1024 * 1024, open_timeout=5)
        except TypeError:
            self.ws = connect(ws_url)
        self.seq = 0

    def call(self, method: str, params: dict | None = None, timeout: float = 8.0) -> dict:
        self.seq += 1
        self.ws.send(json.dumps({"id": self.seq, "method": method, "params": params or {}}))
        deadline = time.time() + timeout
        while time.time() < deadline:
            raw = self.ws.recv(timeout=max(0.1, deadline - time.time()))
            msg = json.loads(raw)
            if msg.get("id") == self.seq:
                if "error" in msg:
                    raise RuntimeError(json.dumps(msg["error"]))
                return msg.get("result") or {}
        raise TimeoutError(method)

    def eval(self, expression: str, timeout: float = 8.0) -> Any:
        result = self.call(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
            timeout=timeout,
        )
        return (result.get("result") or {}).get("value")

    def close(self) -> None:
        try:
            self.ws.close()
        except Exception:
            pass


def chrome_targets(port: int) -> tuple[list[dict], str | None]:
    try:
        version = http_json(f"http://127.0.0.1:{port}/json/version")
        targets = http_json(f"http://127.0.0.1:{port}/json/list")
        return targets if isinstance(targets, list) else [], version.get("Browser")
    except Exception:
        return [], None


def html_to_visible_text(html: str) -> str:
    without_scripts = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    without_tags = re.sub(r"(?s)<[^>]+>", " ", without_scripts)
    return re.sub(r"\s+", " ", without_tags).strip()


def page_from_surface_proof(proof: dict[str, Any]) -> dict[str, Any] | None:
    proofs = proof.get("proofs") if isinstance(proof.get("proofs"), dict) else {}
    url = str(proofs.get("url") or "")
    dom_path_raw = str(proofs.get("dom_path") or "").strip()
    dom_path = Path(dom_path_raw) if dom_path_raw else None
    visible_text_path_raw = str(proofs.get("visible_text_path") or "").strip()
    visible_text_path = Path(visible_text_path_raw) if visible_text_path_raw else None
    screenshot_path = str(proofs.get("screenshot_path") or "")
    dom = (
        dom_path.read_text(encoding="utf-8", errors="ignore")
        if dom_path is not None and dom_path.is_file()
        else ""
    )
    visible_text = (
        visible_text_path.read_text(encoding="utf-8", errors="ignore")
        if visible_text_path is not None and visible_text_path.is_file()
        else ""
    )
    if not url and not dom and not visible_text and not screenshot_path:
        return None
    return {
        "target_id": "chrome-extension-native-messaging",
        "type": "page",
        "url": url,
        "title": "Anticipy real Chrome extension surface",
        "surface": classify_url(url),
        "visible_text": (visible_text or html_to_visible_text(dom))[:20000],
        "focused": True,
        "inputs": [],
        "screenshot_path": screenshot_path,
        "dom_path": str(dom_path) if dom_path is not None and dom_path.is_file() else "",
        "visible_text_path": (
            str(visible_text_path)
            if visible_text_path is not None and visible_text_path.is_file()
            else ""
        ),
        "dom_sha256": (
            proofs.get("dom_sha256")
            or hashlib.sha256(dom.encode("utf-8")).hexdigest()
            if dom
            else ""
        ),
        "dom_bytes": proofs.get("dom_bytes") or len(dom.encode("utf-8")),
        "screenshot_bytes": proofs.get("screenshot_bytes") or 0,
        "acquired_via": proofs.get("acquired_via") or proof.get("surface_path") or "chrome_extension_native_messaging",
    }


def _driver_proof_path_candidates(driver: dict[str, Any]) -> list[Path]:
    raw_paths: list[str] = []

    def add(raw: Any) -> None:
        if isinstance(raw, str) and raw.strip():
            raw_paths.append(raw.strip())

    public_after = driver.get("public_surface_after")
    if isinstance(public_after, dict):
        add(public_after.get("proof_path"))
    service_surface = driver.get("service_surface")
    if isinstance(service_surface, dict):
        add(service_surface.get("proof_path"))
    for raw in driver.get("visible_surface_proof_paths") or []:
        add(raw)
    add(driver.get("visible_surface_proof_path"))

    seen: set[str] = set()
    paths: list[Path] = []
    for raw in raw_paths:
        if raw in seen:
            continue
        seen.add(raw)
        paths.append(Path(raw))
    return paths


def read_driver_surfaces(base: Path) -> tuple[list[dict], list[dict[str, Any]]]:
    driver = load_json(base / "driver_result.json") or {}
    pages: list[dict] = []
    proofs: list[dict[str, Any]] = []
    for proof_path in _driver_proof_path_candidates(driver):
        proof = load_json(proof_path)
        if not isinstance(proof, dict) or proof.get("pass") is not True:
            continue
        proof["proof_json_path"] = str(proof_path)
        page = page_from_surface_proof(proof)
        if page is None:
            continue
        pages.append(page)
        proofs.append(proof)
    return pages, proofs


def read_driver_surface(base: Path) -> tuple[dict | None, dict[str, Any]] | None:
    pages, proofs = read_driver_surfaces(base)
    if not pages or not proofs:
        return None
    return pages[0], proofs[0]


def combined_real_surface_proof(proofs: list[dict[str, Any]]) -> dict[str, Any]:
    if not proofs:
        return {}
    combined = dict(proofs[0])
    proof_items = []
    direct_browser_cdp = False
    uses_chrome_real_clone = False
    visible_surface = False
    screenshot_bytes = 0
    acquired_via = ""
    for proof in proofs:
        proof_items.append(proof)
        direct_browser_cdp = direct_browser_cdp or proof.get("direct_browser_cdp") is True
        uses_chrome_real_clone = uses_chrome_real_clone or proof.get("uses_chrome_real_clone") is True
        proof_data = proof.get("proofs") if isinstance(proof.get("proofs"), dict) else {}
        visible_surface = visible_surface or proof_data.get("visible_surface") is True
        screenshot_bytes += int(proof_data.get("screenshot_bytes") or 0)
        acquired_via = acquired_via or proof_data.get("acquired_via") or proof.get("surface_path") or ""
    combined["pass"] = all(proof.get("pass") is True for proof in proofs)
    combined["direct_browser_cdp"] = direct_browser_cdp
    combined["uses_chrome_real_clone"] = uses_chrome_real_clone
    combined["surface_path"] = acquired_via or "real_chrome_applescript_visible_surface"
    combined["driver_surface_proofs"] = proof_items
    combined["proofs"] = {
        **(combined.get("proofs") if isinstance(combined.get("proofs"), dict) else {}),
        "visible_surface": visible_surface,
        "screenshot_bytes": screenshot_bytes,
        "acquired_via": combined["surface_path"],
    }
    return combined


def read_extension_surface_pages(
    screenshot_dir: Path, base: Path | None = None
) -> tuple[list[dict], dict[str, Any]]:
    if base is not None:
        pages, proofs = read_driver_surfaces(base)
        if pages:
            return pages, combined_real_surface_proof(proofs)

    page, proof = read_extension_surface(screenshot_dir, None)
    return ([page] if page is not None else []), proof


def read_driver_surface_legacy(base: Path) -> tuple[dict | None, dict[str, Any]] | None:
    driver = load_json(base / "driver_result.json") or {}
    proof_path_raw = str(driver.get("visible_surface_proof_path") or "").strip()
    if not proof_path_raw:
        return None
    proof_path = Path(proof_path_raw)
    proof = load_json(proof_path)
    if not isinstance(proof, dict) or proof.get("pass") is not True:
        return None
    proof["proof_json_path"] = str(proof_path)
    page = page_from_surface_proof(proof)
    if page is None:
        return None
    return page, proof


def read_extension_surface(screenshot_dir: Path, base: Path | None = None) -> tuple[dict | None, dict[str, Any]]:
    if base is not None:
        driver_surface = read_driver_surface(base)
        if driver_surface is not None:
            return driver_surface

    repo = Path(__file__).resolve().parents[2]
    proof_path = screenshot_dir / "real_surface_proof.json"
    script = repo / "scripts/v7/probe_real_surface_extension.py"
    if not script.exists():
        return None, {
            "schema": "anticipy.real_surface_proof.v7",
            "pass": False,
            "surface_path": "missing_probe",
            "error": f"{script} not found",
        }

    proof_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            [sys.executable, str(script), "--out", str(proof_path)],
            cwd=str(repo),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
            check=False,
        )
    except Exception as exc:
        return None, {
            "schema": "anticipy.real_surface_proof.v7",
            "pass": False,
            "surface_path": "chrome_extension_native_messaging",
            "error": f"{type(exc).__name__}: {exc}",
        }

    proof = load_json(proof_path) or {
        "schema": "anticipy.real_surface_proof.v7",
        "pass": False,
        "surface_path": "chrome_extension_native_messaging",
        "error": "probe did not write parseable proof",
    }
    proof["probe_stdout"] = (proc.stdout or "")[-4000:]
    proof["probe_stderr"] = (proc.stderr or "")[-4000:]
    proof["probe_exit_code"] = proc.returncode
    proof["proof_json_path"] = str(proof_path)
    if proof.get("pass") is not True:
        return None, proof

    page = page_from_surface_proof(proof)
    if page is None:
        return None, proof
    return page, proof


def load_json(path: str | Path) -> dict | None:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def resolve_script_path(explicit_script: str, stranger_dir: str) -> str:
    if explicit_script:
        return explicit_script

    env_script = os.environ.get("SCRIPT_FILE", "")
    if env_script:
        return env_script

    if stranger_dir:
        for name in ("script.json", "stranger_script.json"):
            candidate = Path(stranger_dir) / name
            if candidate.exists():
                return str(candidate)
    return ""


def resolve_baseline_path(explicit_baseline: str, stranger_dir: str, out_path: str) -> str:
    if explicit_baseline:
        return explicit_baseline

    base = Path(stranger_dir) if stranger_dir else Path(out_path).parent
    candidate = base / "baseline.json"
    if candidate.exists():
        return str(candidate)
    return ""


def is_synthetic_receipt_target(target: dict) -> bool:
    url = str(target.get("url") or "")
    title = str(target.get("title") or "")
    haystack = f"{url}\n{title}".lower()
    parsed = urllib.parse.urlparse(url)
    name = PurePosixPath(urllib.parse.unquote(parsed.path)).name.lower()
    blocked_names = {
        "surface" + ".html",
        "surface" + "_receipt" + ".json",
    }
    if name in blocked_names:
        return True
    return "receipt" in haystack and "anticipy-v6" in haystack


def target_surface(target: dict) -> str:
    return classify_url(str(target.get("url") or ""))


def target_priority(target: dict) -> int:
    surface = target_surface(target)
    priorities = {
        "anticipy": 100,
        "gmail": 95,
        "google_sheets": 93,
        "google_calendar": 92,
        "slack": 90,
        "canvas_design": 88,
        "commerce": 86,
        "notion": 82,
        "linear": 80,
    }
    if surface in priorities:
        return priorities[surface]

    haystack = f"{target.get('url') or ''}\n{target.get('title') or ''}".lower()
    if any(
        term in haystack
        for term in ("gmail", "calendar", "sheets", "spreadsheet", "slack", "amazon", "canva", "figma")
    ):
        return 70
    return 0


def select_page_targets(targets: list[dict], max_pages: int) -> list[dict]:
    limit = max(max_pages, 1)
    candidates = [
        (index, target)
        for index, target in enumerate(targets)
        if target.get("type") == "page" and not is_synthetic_receipt_target(target)
    ]
    ranked = sorted(
        candidates,
        key=lambda row: (
            -target_priority(row[1]),
            row[0],
        ),
    )
    selected: list[tuple[int, dict]] = []
    selected_indexes: set[int] = set()
    selected_surfaces: set[str] = set()
    surface_counts: dict[str, int] = {}

    def add_candidate(index: int, target: dict) -> None:
        selected.append((index, target))
        selected_indexes.add(index)
        surface = target_surface(target)
        selected_surfaces.add(surface)
        surface_counts[surface] = surface_counts.get(surface, 0) + 1

    for index, target in ranked:
        surface = target_surface(target)
        if surface in selected_surfaces:
            continue
        add_candidate(index, target)
        if len(selected) >= limit:
            return [target for _, target in selected]

    per_surface_limit = min(3, limit)
    for index, target in ranked:
        if index in selected_indexes:
            continue
        surface = target_surface(target)
        if surface_counts.get(surface, 0) >= per_surface_limit:
            continue
        add_candidate(index, target)
        if len(selected) >= limit:
            break

    return [target for _, target in selected]


def read_page(target: dict, screenshot_dir: Path) -> dict:
    entry: dict[str, Any] = {
        "target_id": target.get("id"),
        "type": target.get("type"),
        "url": target.get("url"),
        "title": target.get("title"),
        "surface": classify_url(str(target.get("url") or "")),
    }
    ws_url = target.get("webSocketDebuggerUrl")
    if not ws_url or target.get("type") != "page":
        return entry
    try:
        session = CdpSession(ws_url)
        try:
            session.call("Runtime.enable")
            entry["visible_text"] = session.eval(
                """(() => {
                  const text = (document.body && document.body.innerText || "").replace(/\s+/g, " ").trim();
                  return text.slice(0, 20000);
                })()"""
            , timeout=3.0)
            entry["focused"] = session.eval(
                "document.hasFocus && document.hasFocus()"
            , timeout=2.0)
            entry["inputs"] = session.eval(
                """(() => Array.from(document.querySelectorAll('input, textarea, [contenteditable="true"]'))
                  .slice(0, 80).map((el) => ({
                    tag: el.tagName,
                    aria: el.getAttribute('aria-label') || '',
                    role: el.getAttribute('role') || '',
                    text: (el.innerText || el.value || '').slice(0, 1000)
                  })))()"""
            , timeout=3.0)
            screenshot = session.call(
                "Page.captureScreenshot",
                {"format": "png", "captureBeyondViewport": False},
                timeout=5,
            ).get("data")
            if screenshot:
                name = safe_name(entry["surface"] + "-" + str(entry.get("target_id") or "page")) + ".png"
                path = screenshot_dir / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(base64.b64decode(screenshot))
                entry["screenshot_path"] = str(path)
        finally:
            session.close()
    except Exception as exc:
        entry["read_error"] = str(exc)
    return entry


def classify_url(url: str) -> str:
    u = url.lower()
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    try:
        port = parsed.port
    except ValueError:
        port = None
    if host in {"127.0.0.1", "localhost", "::1"} and port == 8731:
        return "anticipy"
    if host == "www.anticipy.ai" and parsed.path.startswith("/app"):
        return "anticipy"
    if "mail.google.com" in u:
        return "gmail"
    if host in {"sheets.google.com"} or (host == "docs.google.com" and parsed.path.startswith("/spreadsheets")):
        return "google_sheets"
    if "calendar.google.com" in u:
        return "google_calendar"
    if "slack.com" in u:
        return "slack"
    if "notion.so" in u:
        return "notion"
    if "linear.app" in u:
        return "linear"
    if "app.hubspot.com" in u or "hubspot.com" in u:
        return "crm"
    if "salesforce.com" in u or "force.com" in u:
        return "crm"
    if "canva.com" in u:
        return "canvas_design"
    if "figma.com" in u:
        return "canvas_design"
    if "amazon." in u or "opentable." in u or "resy." in u:
        return "commerce"
    return "browser"


def surface_from_text(value: str) -> str | None:
    surfaces = surfaces_from_text(value)
    return sorted(surfaces)[0] if surfaces else None


def normalized_script_key(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def is_script_scope_noise_key(key: str) -> bool:
    normalized = normalized_script_key(key)
    if normalized in SCRIPT_SCOPE_NOISE_KEYS:
        return True
    return any(normalized.endswith(suffix) for suffix in SCRIPT_SCOPE_NOISE_KEY_SUFFIXES)


def is_chrome_carrier_text(text: str) -> bool:
    return "chrome" in text and ("9222" in text or "port" in text or "debug" in text)


def surfaces_from_text(
    value: str,
    *,
    fuzzy: bool = True,
    include_generic_carriers: bool = True,
) -> set[str]:
    text = value.strip().lower()
    if not text:
        return set()
    if text in SURFACE_ALIASES:
        surface = SURFACE_ALIASES[text]
        if include_generic_carriers or surface not in GENERIC_CARRIER_SURFACES:
            return {surface}
        return set()
    if text.startswith(("http://", "https://", "file://")):
        surface = classify_url(text)
        if include_generic_carriers or surface not in GENERIC_CARRIER_SURFACES:
            return {surface}
        return set()
    if not fuzzy:
        return set()

    surfaces: set[str] = set()
    for token, surface in SURFACE_ALIASES.items():
        if len(token) < 4 or token not in text:
            continue
        if not include_generic_carriers and surface in GENERIC_CARRIER_SURFACES:
            continue
        surfaces.add(surface)
    if is_chrome_carrier_text(text):
        surfaces.difference_update(GENERIC_CARRIER_SURFACES)
    return surfaces


def script_surface_scope(value: Any) -> set[str]:
    surfaces: set[str] = set()

    def visit(item: Any, key_hint: str = "", relevant: bool = False) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                normalized_key = normalized_script_key(str(key))
                if is_script_scope_noise_key(normalized_key):
                    continue
                visit(
                    child,
                    normalized_key,
                    relevant or normalized_key in SCRIPT_RELEVANT_CONTAINERS,
                )
            return
        if isinstance(item, list):
            for child in item:
                visit(child, key_hint, relevant or key_hint in SCRIPT_RELEVANT_CONTAINERS)
            return
        if not isinstance(item, str):
            return

        if key_hint in SCRIPT_SURFACE_KEYS:
            surfaces.update(surfaces_from_text(item, fuzzy=True))
            return

        if relevant or key_hint in SCRIPT_TEXT_KEYS:
            surfaces.update(surfaces_from_text(item, fuzzy=True, include_generic_carriers=False))
            return

        if not key_hint:
            surfaces.update(surfaces_from_text(item, fuzzy=True, include_generic_carriers=False))

    visit(value)
    return surfaces


def safe_name(text: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in text)[:120]


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def page_key(page: dict) -> str:
    return "\n".join(
        [
            str(page.get("surface") or ""),
            str(page.get("url") or ""),
            str(page.get("title") or ""),
        ]
    )


def page_visible_state(page: dict) -> dict:
    return {
        "surface": page.get("surface"),
        "url": page.get("url"),
        "title": page.get("title"),
        "visible_text": page.get("visible_text") or "",
        "inputs": page.get("inputs") or [],
        "read_error": page.get("read_error") or "",
    }


def page_summary(page: dict) -> dict:
    return {
        "surface": page.get("surface"),
        "url": page.get("url"),
        "title": page.get("title"),
    }


def add_changed_surface(surfaces: set[str], name: str | None) -> None:
    if name:
        surfaces.add(name)


def diff_pages(before: list[dict], after: list[dict]) -> tuple[list[dict], list[dict], list[dict], set[str]]:
    before_by_key = {page_key(page): page for page in before}
    after_by_key = {page_key(page): page for page in after}
    added: list[dict] = []
    removed: list[dict] = []
    changed: list[dict] = []
    changed_surfaces: set[str] = set()

    for key, page in sorted(after_by_key.items()):
        if key not in before_by_key:
            added.append(page_summary(page))
            add_changed_surface(changed_surfaces, page.get("surface"))
            continue
        before_hash = digest(page_visible_state(before_by_key[key]))
        after_hash = digest(page_visible_state(page))
        if before_hash != after_hash:
            changed.append(
                {
                    **page_summary(page),
                    "before_hash": before_hash,
                    "after_hash": after_hash,
                }
            )
            add_changed_surface(changed_surfaces, page.get("surface"))

    for key, page in sorted(before_by_key.items()):
        if key not in after_by_key:
            removed.append(page_summary(page))
            add_changed_surface(changed_surfaces, page.get("surface"))

    return added, removed, changed, changed_surfaces


def surface_receipts_present(trace: dict) -> bool:
    proof = trace.get("real_surface_proof")
    if isinstance(proof, dict):
        proofs = proof.get("proofs") if isinstance(proof.get("proofs"), dict) else {}
        acquired_via = proofs.get("acquired_via") or proof.get("surface_path")
        if (
            proof.get("pass") is True
            and proof.get("direct_browser_cdp") is not True
            and proof.get("uses_chrome_real_clone") is not True
            and proofs.get("visible_surface") is True
            and acquired_via in {
                "chrome_extension_native_messaging",
                "chrome_extension_debugger",
                "real_chrome_applescript_visible_surface",
            }
        ):
            return True
        return False

    pages = trace.get("pages") or []
    if any(page.get("visible_text") or page.get("screenshot_path") or page.get("inputs") for page in pages):
        return True
    native_ax = trace.get("native_ax") or {}
    if native_ax.get("ok") and native_ax.get("summary"):
        return True
    terminal = trace.get("terminal") or {}
    return bool(terminal.get("ok") and terminal.get("text"))


def current_broken_surfaces(current: dict) -> tuple[set[str], set[str]]:
    observed: set[str] = set()
    broken: set[str] = set()
    for page in current.get("pages") or []:
        surface = page.get("surface")
        if not surface:
            continue
        observed.add(surface)
        if page.get("read_error"):
            broken.add(surface)

    native_ax = current.get("native_ax") or {}
    observed.add("native_ax")
    if not native_ax.get("ok"):
        broken.add("native_ax")

    terminal = current.get("terminal") or {}
    observed.add("terminal")
    if not terminal.get("ok"):
        broken.add("terminal")

    return observed, broken


def scope_changed_surfaces(all_changed_surfaces: set[str], current: dict, script: dict | None) -> dict:
    scope = script_surface_scope(script) if script else set()
    scoped = bool(scope)
    if scoped:
        changed_surfaces = all_changed_surfaces & scope
        unrelated = all_changed_surfaces - scope
    else:
        changed_surfaces = set(all_changed_surfaces)
        unrelated = set()

    observed, broken = current_broken_surfaces(current)
    broken_script_surfaces = broken & scope if scoped else set()
    missing_script_surfaces = scope - observed if scoped else set()

    return {
        "changed_surfaces": sorted(changed_surfaces),
        "all_changed_surfaces": sorted(all_changed_surfaces),
        "unrelated_changed_surfaces": sorted(unrelated),
        "script_surface_scope": sorted(scope),
        "scoped_to_script": scoped,
        "broken_script_surfaces": sorted(broken_script_surfaces),
        "missing_script_surfaces": sorted(missing_script_surfaces),
    }


def trace_diff(baseline: dict | None, current: dict, script: dict | None = None) -> dict:
    if not baseline:
        scoped = scope_changed_surfaces(set(), current, script)
        return {
            **scoped,
            "added_pages": [],
            "removed_pages": [],
            "changed_pages": [],
            "native_ax_changed": False,
            "terminal_changed": False,
        }

    added, removed, changed, changed_surfaces = diff_pages(
        baseline.get("pages") or [],
        current.get("pages") or [],
    )
    native_ax_changed = digest(baseline.get("native_ax") or {}) != digest(current.get("native_ax") or {})
    terminal_changed = digest(baseline.get("terminal") or {}) != digest(current.get("terminal") or {})
    if native_ax_changed:
        changed_surfaces.add("native_ax")
    if terminal_changed:
        changed_surfaces.add("terminal")

    return {
        **scope_changed_surfaces(changed_surfaces, current, script),
        "added_pages": added,
        "removed_pages": removed,
        "changed_pages": changed,
        "native_ax_changed": native_ax_changed,
        "terminal_changed": terminal_changed,
    }


def run_osascript(script: str, timeout: int = 10) -> tuple[int, str]:
    try:
        p = subprocess.run(
            ["osascript", "-e", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
        )
        return p.returncode, p.stdout
    except Exception as exc:
        return 1, str(exc)


def read_ax_summary() -> dict:
    script = r'''
tell application "System Events"
  set axSummary to ""
  repeat with p in (processes whose background only is false)
    try
      set appName to name of p
      set winCount to count of windows of p
      set windowNames to ""
      repeat with w in windows of p
        try
          set winName to name of w as text
          if winName is not "" then set windowNames to windowNames & " title=" & winName
        end try
      end repeat
      set axSummary to axSummary & appName & " windows=" & (winCount as text) & windowNames & linefeed
    end try
  end repeat
  return axSummary
end tell
'''
    code, out = run_osascript(script)
    return {"ok": code == 0, "summary": out.strip()}


def read_terminal_text() -> dict:
    script = r'''
tell application "System Events"
  if exists process "Terminal" then
    tell process "Terminal"
      try
        return value of text area 1 of window 1
      on error errMsg
        return errMsg
      end try
    end tell
  end if
  return ""
end tell
'''
    code, out = run_osascript(script)
    return {"ok": code == 0, "text": out[-20000:]}


def read_engine_logs(home: Path) -> dict:
    root = home / ".anticipy"
    paths = [
        root / "actions.log",
        root / "declined_actions" / "latest.jsonl",
        root / "engine.log",
    ]
    logs: dict[str, str] = {}
    for path in paths:
        if path.exists() and path.is_file():
            logs[str(path)] = path.read_text(errors="ignore")[-20000:]
    return logs


def read_jsonl_matches(path_raw: str, ingest_id: str, limit: int = 5) -> list[dict]:
    if not path_raw or not ingest_id:
        return []
    path = Path(path_raw)
    if not path.exists() or not path.is_file():
        return []
    matches: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                row = json.loads(line)
            except Exception:
                continue
            if isinstance(row, dict) and row.get("ingest_id") == ingest_id:
                matches.append(row)
    except Exception:
        return []
    return matches[-limit:]


def read_v7_artifacts_from_driver(driver: dict | None) -> dict:
    driver = driver if isinstance(driver, dict) else {}
    recent = (
        driver.get("status_after_sanitized", {}).get("matching_recent")
        if isinstance(driver.get("status_after_sanitized"), dict)
        else {}
    )
    recent = recent if isinstance(recent, dict) else {}
    ingest_id = str(recent.get("ingest_id") or driver.get("upload", {}).get("response", {}).get("ingest_id") or "")
    paths = recent.get("v7_artifacts") if isinstance(recent.get("v7_artifacts"), dict) else {}
    upload_response = driver.get("upload", {}).get("response") if isinstance(driver.get("upload"), dict) else {}
    if not paths and isinstance(upload_response, dict):
        paths = upload_response.get("v7_artifacts") if isinstance(upload_response.get("v7_artifacts"), dict) else {}
    records = {
        name: read_jsonl_matches(str(path), ingest_id)
        for name, path in (paths or {}).items()
    }
    return {
        "ingest_id": ingest_id,
        "paths": paths or {},
        "records": records,
        "present": bool(paths) and any(records.values()),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--stranger-dir", default="")
    ap.add_argument("--baseline", default="")
    ap.add_argument("--script", default="")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--max-pages", type=int, default=8)
    args = ap.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    base = Path(args.stranger_dir) if args.stranger_dir else out.parent
    screenshot_dir = base / "screenshots" / safe_name(out.stem or "trace")
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    extension_pages, real_surface_proof = read_extension_surface_pages(screenshot_dir, base)
    if extension_pages:
        targets = []
        browser = "chrome_extension_native_messaging"
        pages = extension_pages
    else:
        targets, browser = chrome_targets(args.port)
        page_targets = select_page_targets(targets, args.max_pages)
        pages = [read_page(t, screenshot_dir) for t in page_targets]

    driver_result = load_json(base / "driver_result.json")
    trace = {
        "schema": "anticipy.v6.trace",
        "created_at": now(),
        "cdp_port": args.port,
        "browser": browser,
        "chrome_surface_path": (
            real_surface_proof.get("surface_path", "chrome_extension_native_messaging")
            if extension_pages
            else "cdp"
        ),
        "extension_surface_proof": real_surface_proof,
        "real_surface_proof": real_surface_proof,
        "tabs": [
            {
                "id": t.get("id"),
                "type": t.get("type"),
                "url": t.get("url"),
                "title": t.get("title"),
            }
            for t in targets
        ],
        "pages": pages,
        "native_ax": read_ax_summary(),
        "terminal": read_terminal_text(),
        "engine_logs": read_engine_logs(Path.home()),
        "driver_result": driver_result,
        "v7_artifacts": read_v7_artifacts_from_driver(driver_result),
        "transcript_quality": load_json(base / "transcript_quality.json"),
        "cost_breakdown": load_json(base / "cost_breakdown.json"),
    }
    baseline_path = resolve_baseline_path(args.baseline, args.stranger_dir, args.out)
    baseline = load_json(baseline_path) if baseline_path else None
    script_path = resolve_script_path(args.script, args.stranger_dir)
    script = load_json(script_path) if script_path else None
    trace["script"] = {
        "path": script_path,
        "loaded": script is not None,
        "surface_scope": sorted(script_surface_scope(script) if script else set()),
    }
    trace["surface_receipts_present"] = surface_receipts_present(trace)
    trace["baseline"] = {
        "path": baseline_path,
        "loaded": baseline is not None,
        "created_at": (baseline or {}).get("created_at"),
    }
    trace["diff"] = trace_diff(baseline, trace, script)
    out.write_text(json.dumps(trace, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "out": str(out),
                "pages": len(pages),
                "surface_receipts_present": trace["surface_receipts_present"],
                "changed_surfaces": trace["diff"]["changed_surfaces"],
                "all_changed_surfaces": trace["diff"]["all_changed_surfaces"],
            }
        )
    )
    return 0 if trace["surface_receipts_present"] else 1


if __name__ == "__main__":
    sys.exit(main())
