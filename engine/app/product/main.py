"""Anticipy desktop entry. Starts the local product backend
in-process (no external server) and opens it in a real native
window. Big models via OpenRouter cloud exactly as the engine
does; small audio models local. No hardcoded /Users/ paths.
"""

from __future__ import annotations

import argparse
import os
import socket
import threading
import time


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


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _serve(port: int) -> None:
    import uvicorn

    from app.product.server import app

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def _fixed_or_free_port(headless: bool) -> int:
    raw = os.environ.get("ANTICIPY_PORT")
    if raw:
        return int(raw)
    return 8731 if headless else _free_port()


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

    threading.Thread(target=_serve, args=(port,), daemon=True).start()
    _preflight_mic_permission()

    url = f"http://127.0.0.1:{port}/"
    import urllib.request

    for _ in range(60):
        try:
            urllib.request.urlopen(url, timeout=1).read()
            break
        except Exception:
            time.sleep(0.5)

    import webview

    webview.create_window("Anticipy", url, width=820, height=720,
                          min_size=(560, 560))
    webview.start()


if __name__ == "__main__":
    main()
