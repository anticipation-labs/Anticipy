import asyncio
from io import BytesIO
from typing import Any

from app.product.surface_runtime import SurfaceRuntime


class FakeSurfaceRuntime(SurfaceRuntime):
    def __init__(
        self,
        *,
        proof_urls: list[str] | None = None,
        command_data: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(host="127.0.0.1", port=7777, secret="test-secret")
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []
        self.proof_urls = proof_urls or ["https://example.com/"]
        self.command_data = command_data or {}

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> tuple[int, dict[str, Any], str]:
        self.calls.append((method, path, payload))
        if method == "GET" and path == "/status":
            return 200, {
                "ok": True,
                "current_task_running": False,
                "bridge_closed": False,
                "pid": 123,
                "platform": "test",
            }, ""
        if method == "POST" and path == "/surface-command":
            assert payload is not None
            command = str(payload.get("command") or "")
            data = self.command_data.get(command, {"selector": payload.get("selector")})
            return 200, {
                "ok": True,
                "command": command,
                "data": data,
                "acquired_via": "fake_bridge",
            }, ""
        if method == "POST" and path == "/surface-proof":
            url = self.proof_urls.pop(0) if self.proof_urls else "https://example.com/"
            return 200, {
                "ok": True,
                "url": url,
                "dom": "<html><body>visible proof</body></html>",
                "screenshot_data_url": "data:image/jpeg;base64,abc",
                "acquired_via": "fake_bridge",
                "pid": 123,
            }, ""
        raise AssertionError(f"unexpected request {method} {path}")


def _payloads(runtime: FakeSurfaceRuntime, path: str) -> list[dict[str, Any]]:
    return [
        payload or {}
        for _, called_path, payload in runtime.calls
        if called_path == path
    ]


def test_existing_open_browser_task_still_navigates_and_reads_visible_proof():
    runtime = FakeSurfaceRuntime(proof_urls=["https://example.com/"])

    receipt = runtime.run_browser_task(
        verb="open_browser_tab",
        target="example.com",
        task="open example",
    )

    assert receipt["ok"] is True
    assert receipt["proof"]["url_match"] is True
    command_payload = _payloads(runtime, "/surface-command")[0]
    assert command_payload["command"] == "navigate"
    assert command_payload["url"] == "https://example.com"


def test_click_type_read_and_enter_key_return_surface_receipts():
    runtime = FakeSurfaceRuntime(
        command_data={
            "click": {"clicked": "#go", "selector": "#go"},
            "type": {
                "typed": 5,
                "selector": "#q",
                "submitted": False,
                "preservedValue": False,
            },
            "read": {"text": "visible page text", "selector": "body"},
            "key": {"key": "Enter", "selector": "#q", "activeTag": "INPUT"},
        }
    )

    click = runtime.run_click(selector="#go")
    typed = runtime.run_type(selector="#q", text="hello")
    read = runtime.read_surface(selector="body")
    enter = runtime.run_key(selector="#q", key="Enter")

    assert click["ok"] is True
    assert click["proof"]["clicked"] == "#go"
    assert typed["ok"] is True
    assert typed["proof"]["typed"] == 5
    assert read["ok"] is True
    assert read["proof"]["text"] == "visible page text"
    assert enter["ok"] is True
    assert enter["proof"]["key"] == "Enter"

    command_payloads = _payloads(runtime, "/surface-command")
    assert [p["command"] for p in command_payloads] == [
        "click",
        "type",
        "read",
        "key",
    ]
    assert command_payloads[-1]["key"] == "Enter"


def test_wait_for_url_polls_until_visible_url_matches():
    runtime = FakeSurfaceRuntime(
        proof_urls=[
            "https://example.com/loading",
            "https://example.com/done",
        ]
    )

    receipt = runtime.wait_for_url(
        expected_url="https://example.com/done",
        timeout=1.0,
        interval=0.05,
    )

    assert receipt["ok"] is True
    assert receipt["proof"]["url"] == "https://example.com/done"
    assert receipt["proof"]["attempts"] == 2


def test_non_enter_key_uses_real_key_primitive():
    runtime = FakeSurfaceRuntime(
        command_data={"key": {"key": "Escape", "selector": "#q"}}
    )

    receipt = runtime.run_key(selector="#q", key="Escape")

    assert receipt["ok"] is True
    assert receipt["proof"]["key"] == "Escape"


def test_list_and_close_tabs_return_bridge_receipts():
    runtime = FakeSurfaceRuntime(
        command_data={
            "list_tabs": {
                "tabs": [{"url": "https://example.com", "title": "Example"}],
                "count": 1,
            },
            "close_tabs_matching": {
                "matched": [{"url": "https://youtube.com/watch?v=1"}],
                "closed": [{"url": "https://youtube.com/watch?v=1"}],
                "matchedCount": 1,
                "closedCount": 1,
            },
        }
    )

    listed = runtime.list_tabs()
    closed = runtime.close_tabs_matching(url_includes="youtube", max_close=3)

    assert listed["ok"] is True
    assert listed["proof"]["tabs"][0]["url"] == "https://example.com"
    assert closed["ok"] is True
    assert closed["proof"]["closedCount"] == 1
    close_payload = _payloads(runtime, "/surface-command")[-1]
    assert close_payload["command"] == "close_tabs_matching"
    assert close_payload["url_includes"] == "youtube"


def test_native_bridge_emits_key_and_close_tab_primitives():
    from native_host.native_bridge import NativeBridge

    class FakeNativeBridge(NativeBridge):
        def __init__(self) -> None:
            super().__init__(
                stdin=BytesIO(),
                stdout=BytesIO(),
                loop=asyncio.get_running_loop(),
            )
            self.payloads: list[dict[str, Any]] = []

        async def _send_and_await(
            self,
            payload: dict[str, Any],
            timeout: float | None = None,
        ) -> dict[str, Any]:
            self.payloads.append(payload)
            if payload["type"] == "list_tabs":
                return {"data": {"tabs": [{"url": "https://example.com"}]}}
            if payload["type"] == "close_tabs_matching":
                return {"data": {"closed": [{"url": "https://example.com"}]}}
            return {"data": {"key": payload.get("key")}}

    async def run() -> FakeNativeBridge:
        bridge = FakeNativeBridge()
        assert await bridge.key("Enter", selector="#q") == {"key": "Enter"}
        assert await bridge.list_tabs() == [{"url": "https://example.com"}]
        assert await bridge.close_tabs_matching(url_includes="example") == {
            "closed": [{"url": "https://example.com"}],
        }
        return bridge

    bridge = asyncio.run(run())
    assert [payload["type"] for payload in bridge.payloads] == [
        "key",
        "list_tabs",
        "close_tabs_matching",
    ]
    assert bridge.payloads[-1]["urlIncludes"] == "example"
