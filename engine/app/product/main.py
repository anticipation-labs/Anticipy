"""Anticipy desktop entry. Starts the local product backend
in-process (no external server) and opens it in a real native
window. Big models via OpenRouter cloud exactly as the engine
does; small audio models local. No hardcoded /Users/ paths.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import threading
import time
import urllib.request


def _preflight_mic_permission(timeout_s: float = 20.0) -> None:
    """Ask macOS for microphone permission from the app's main process.

    PortAudio can wedge if the first permission request happens inside the
    background HTTP worker thread. This preflight is best-effort: denial or
    timeout is reported later by the product UI.
    """
    try:
        import Foundation
        from AVFoundation import AVCaptureDevice, AVMediaTypeAudio
    except Exception:
        return
    try:
        status = int(AVCaptureDevice.authorizationStatusForMediaType_(
            AVMediaTypeAudio))
    except Exception:
        return
    if status != 0:
        return

    done = threading.Event()

    def cb(_granted: bool) -> None:
        done.set()

    try:
        AVCaptureDevice.requestAccessForMediaType_completionHandler_(
            AVMediaTypeAudio, cb)
    except Exception:
        return

    deadline = time.time() + timeout_s
    while not done.is_set() and time.time() < deadline:
        Foundation.NSRunLoop.currentRunLoop().runMode_beforeDate_(
            Foundation.NSDefaultRunLoopMode,
            Foundation.NSDate.dateWithTimeIntervalSinceNow_(0.1))


def _serve(port: int) -> None:
    import uvicorn

    from app.product.server import app

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def _fixed_or_free_port(headless: bool) -> int:
    raw = os.environ.get("ANTICIPY_PORT")
    if raw:
        return int(raw)
    return 8731


def _engine_healthy(port: int) -> bool:
    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/health", timeout=1.0) as res:
            data = json.loads(res.read().decode("utf-8"))
        return (
            data.get("ok") is True
            and data.get("service") == "anticipy-local-engine"
        )
    except Exception:
        return False


def _wait_until_healthy(port: int, seconds: float = 30.0) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if _engine_healthy(port):
            return True
        time.sleep(0.5)
    return False


def _startup_error_html(port: int, errors: list[str]) -> str:
    log_path = os.path.join(os.path.expanduser("~"), ".anticipy",
                            "product-engine.log")
    detail = "\n".join(errors) or "The local engine did not become healthy."
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <style>
    body {{
      margin: 0;
      min-height: 100vh;
      background: #080806;
      color: #f4eee4;
      font: 15px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      display: grid;
      place-items: center;
    }}
    main {{ max-width: 560px; padding: 32px; }}
    h1 {{ margin: 0 0 12px; font-size: 28px; }}
    p {{ color: rgba(244, 238, 228, .78); line-height: 1.55; }}
    code {{
      display: block;
      margin-top: 14px;
      padding: 14px;
      border: 1px solid rgba(244, 238, 228, .16);
      border-radius: 8px;
      background: rgba(255,255,255,.05);
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }}
  </style>
</head>
<body>
  <main>
    <h1>Anticipy could not start.</h1>
    <p>The local engine on 127.0.0.1:{port} did not become healthy, so the app
    is showing this diagnostic screen instead of a blank window.</p>
    <code>{html.escape(detail)}</code>
    <p>Log: {html.escape(log_path)}</p>
  </main>
</body>
</html>"""


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Anticipy local engine")
    parser.add_argument("--server", action="store_true",
                        help="run only the localhost engine, no native UI")
    parser.add_argument("--port", type=int, default=None,
                        help="localhost port for --server")
    args = parser.parse_args(argv)

    headless = args.server or os.environ.get("ANTICIPY_HEADLESS") == "1"
    port = args.port or _fixed_or_free_port(headless)
    os.environ["ANTICIPY_PORT"] = str(port)

    if headless:
        _serve(port)
        return

    url = f"http://127.0.0.1:{port}/"
    server_errors: list[str] = []
    if not _engine_healthy(port):
        def start_server() -> None:
            try:
                _serve(port)
            except BaseException as exc:
                server_errors.append(f"{type(exc).__name__}: {exc}")

        threading.Thread(target=start_server, daemon=True).start()
        _preflight_mic_permission()

    import webview

    if _wait_until_healthy(port):
        webview.create_window("Anticipy", url, width=820, height=720,
                              min_size=(560, 560))
    else:
        webview.create_window("Anticipy",
                              html=_startup_error_html(port, server_errors),
                              width=820,
                              height=720,
                              min_size=(560, 560))
    webview.start()


if __name__ == "__main__":
    main()
