"""Anticipy desktop entry. Starts the local product backend
in-process (no external server) and opens it in a real native
window. Big models via OpenRouter cloud exactly as the engine
does; small audio models local. No hardcoded /Users/ paths.
"""

from __future__ import annotations

import socket
import threading
import time


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


def main() -> None:
    port = _free_port()
    threading.Thread(target=_serve, args=(port,), daemon=True).start()

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
