"""
Deterministic test of the extension's content.js actions on real public sites.

No LLM. No Realtime. No service worker. Just: load extension into headed
Chromium → navigate to a real URL → send DOM_ACTION messages to content.js
exactly as the BrowserAgent would → verify outcome on the real page.

Each scenario has an expected post-condition that we check directly (URL
contains X, an element appears, a specific value lands in an input, etc.).

This is the ground-truth reliability test for the extension's action set.
The LLM-driven loop is only as good as these primitives.

Run:
    cd engine && DISPLAY=:99 python test_extension_actions.py

Pass criterion: 100% on every test, 3 consecutive runs.
"""

import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
EXT_DIR = ROOT / "extension"


# ---------------------------------------------------------------------------
# Helpers — drive content.js via tabs.sendMessage from a chrome-extension page
# ---------------------------------------------------------------------------


async def wait_for_extension(ctx, retries: int = 30) -> str | None:
    """Get the loaded extension's id."""
    for _ in range(retries):
        for sw in ctx.service_workers:
            if sw.url.startswith("chrome-extension://"):
                return sw.url.split("/")[2]
        await asyncio.sleep(0.5)
    return None


async def open_extension_runner(ctx, ext_id: str):
    """Open the extension's popup page and use it as a privileged context that
    can call chrome.tabs.sendMessage. Returns the page handle.

    We use popup.html because it's part of the extension and has chrome.* APIs."""
    p = await ctx.new_page()
    await p.goto(f"chrome-extension://{ext_id}/popup.html", timeout=15_000)
    return p


async def call_content_action(runner, tab_id: int, action: dict, timeout_ms: int = 15_000) -> dict:
    """From the extension runner page, send a DOM_ACTION to a target tab's
    content script. Auto-injects content.js if needed (mirrors what
    BrowserAgent._sendToContent does)."""
    return await runner.evaluate(
        """async ({tabId, action, timeoutMs}) => {
            return await new Promise((resolve) => {
                const send = (attempt) => {
                    chrome.tabs.sendMessage(tabId, { type: "DOM_ACTION", action }, (resp) => {
                        if (chrome.runtime.lastError) {
                            if (attempt === 0) {
                                chrome.scripting.executeScript({ target: { tabId }, files: ["content.js"] }, () => {
                                    if (chrome.runtime.lastError) {
                                        resolve({ success: false, error: chrome.runtime.lastError.message });
                                        return;
                                    }
                                    setTimeout(() => send(1), 500);
                                });
                            } else {
                                resolve({ success: false, error: chrome.runtime.lastError.message });
                            }
                        } else {
                            resolve(resp || { success: false, error: "Empty response" });
                        }
                    });
                };
                send(0);
                setTimeout(() => resolve({ success: false, error: "timeout" }), timeoutMs);
            });
        }""",
        {"tabId": tab_id, "action": action, "timeoutMs": timeout_ms},
    )


async def get_page_state(runner, tab_id: int) -> dict:
    res = await call_content_action(runner, tab_id, {"type": "getPageState"})
    return res.get("data") or {}


async def open_tab_at(ctx, url: str):
    """Open a new tab at url and wait for it to settle. Returns Playwright Page
    + chrome tabId via the extension's tabs.query."""
    page = await ctx.new_page()
    await page.goto(url, timeout=30_000, wait_until="domcontentloaded")
    # Give SPA scripts a moment
    try:
        await page.wait_for_load_state("networkidle", timeout=5_000)
    except Exception:
        pass
    await asyncio.sleep(1.0)
    return page


async def get_tab_id(runner, url_like: str) -> int | None:
    return await runner.evaluate(
        """(needle) => new Promise((res) => {
            chrome.tabs.query({}, (tabs) => {
                const hit = tabs.find(t => (t.url || "").includes(needle));
                res(hit ? hit.id : null);
            });
        })""",
        url_like,
    )


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


async def scenario_wikipedia_search(ctx, runner) -> dict:
    """Type 'cats' into Wikipedia's search and submit. Verify URL changed."""
    page = await open_tab_at(ctx, "https://en.wikipedia.org/wiki/Main_Page")
    tab_id = await get_tab_id(runner, "wikipedia.org/wiki")
    if tab_id is None:
        await page.close()
        return {"name": "wikipedia_search", "passed": False, "reason": "tab not found"}
    start_url = page.url
    r = await call_content_action(runner, tab_id, {
        "type": "type",
        "selector": "input[name='search']",
        "value": "cats",
        "submit": True,
    })
    if not r.get("success"):
        await page.close()
        return {"name": "wikipedia_search", "passed": False, "reason": f"type+submit failed: {r}"}
    # Wait for ANY navigation away from Main_Page
    try:
        await page.wait_for_function(
            "(start) => location.href !== start",
            arg=start_url,
            timeout=10_000,
        )
    except Exception:
        await asyncio.sleep(2)
    final = page.url
    await page.close()
    ok = (final != start_url) and (
        "/wiki/Cat" in final or "search=cats" in final.lower() or "fulltext=" in final
    )
    return {"name": "wikipedia_search", "passed": ok, "reason": f"final url: {final}"}


async def scenario_duckduckgo_search(ctx, runner) -> dict:
    page = await open_tab_at(ctx, "https://duckduckgo.com/")
    tab_id = await get_tab_id(runner, "duckduckgo.com")
    if tab_id is None:
        await page.close()
        return {"name": "duckduckgo_search", "passed": False, "reason": "tab not found"}
    r = await call_content_action(runner, tab_id, {
        "type": "type",
        "selector": "input[name='q']",
        "value": "anticipy",
        "submit": True,
    })
    if not r.get("success"):
        await page.close()
        return {"name": "duckduckgo_search", "passed": False, "reason": f"type+submit failed: {r}"}
    try:
        await page.wait_for_url("**?q=anticipy*", timeout=10_000)
    except Exception:
        await asyncio.sleep(2)
    final = page.url
    await page.close()
    ok = "q=anticipy" in final
    return {"name": "duckduckgo_search", "passed": ok, "reason": f"final url: {final}"}


async def scenario_shadow_dom_pierce(ctx, runner) -> dict:
    """Definitive shadow-DOM capability test: build a custom element with a
    CLOSED shadow root containing an input, then verify type+submit reaches
    it. world_patch.js coerces the closed root open at construction time;
    pierceQueryAll then walks it and finds the input."""
    page = await open_tab_at(ctx, "https://example.com/")
    tab_id = await get_tab_id(runner, "example.com")
    if tab_id is None:
        await page.close()
        return {"name": "shadow_dom_pierce", "passed": False, "reason": "tab not found"}
    # The custom element's constructor uses { mode: 'closed' } — without
    # world_patch, this would be invisible to all JS. With world_patch, it
    # gets coerced to open and pierceQuery can walk it.
    mode_used = await page.evaluate("""
      () => {
        class XBox extends HTMLElement {
          constructor() {
            super();
            const r = this.attachShadow({ mode: 'closed' });
            r.innerHTML = '<form id="xf"><input id="xi" name="needle" placeholder="hidden" /></form>';
            this.__detected_mode = !!this.shadowRoot ? 'open' : 'closed';
          }
        }
        if (!customElements.get('x-box')) customElements.define('x-box', XBox);
        const el = document.createElement('x-box');
        document.body.appendChild(el);
        return el.__detected_mode;
      }
    """)
    # Try to type into the hidden input via pierceQuery + the type action
    r = await call_content_action(runner, tab_id, {
        "type": "type",
        "selector": "input#xi",
        "value": "needle-found",
    })
    landed = await page.evaluate("""
      () => {
        const xb = document.querySelector('x-box');
        const root = xb && xb.shadowRoot;
        const inp = root && root.querySelector('input#xi');
        return inp ? inp.value : '';
      }
    """)
    await page.close()
    ok = bool(r.get("success")) and landed == "needle-found"
    return {
        "name": "shadow_dom_pierce",
        "passed": ok,
        "reason": f"shadow_mode_after_patch={mode_used} type_ok={r.get('success')} value_landed={landed!r}",
    }


async def scenario_pierce_query_youtube(ctx, runner) -> dict:
    """Verify pierce_query finds an element inside YouTube's shadow tree.
    Use a label that's reliably present on the homepage masthead: "Home"."""
    page = await open_tab_at(ctx, "https://www.youtube.com/")
    tab_id = await get_tab_id(runner, "youtube.com")
    if tab_id is None:
        await page.close()
        return {"name": "pierce_query_youtube", "passed": False, "reason": "tab not found"}
    await asyncio.sleep(3.0)
    # Try several labels in order — Home is on the side rail, Subscriptions
    # is a guide entry, and the YT logo has aria-label "YouTube Home"
    for label in ("Home", "YouTube Home", "Subscriptions", "Search"):
        r = await call_content_action(runner, tab_id, {
            "type": "pierce_query",
            "text": label,
        })
        if r.get("success") and isinstance(r.get("x"), int):
            await page.close()
            return {"name": "pierce_query_youtube", "passed": True, "reason": f"found '{label}' at ({r['x']},{r['y']})"}
    await page.close()
    return {"name": "pierce_query_youtube", "passed": False, "reason": "none of Home/YouTube Home/Subscriptions/Search found"}


async def scenario_contenteditable_canvas_type(ctx, runner) -> dict:
    """canvas_type's fallback path is "active contenteditable" — the generic
    case for any rich editor with no <input>. Inject a contenteditable onto a
    real http page (example.com) and verify canvas_type writes into it."""
    page = await open_tab_at(ctx, "https://example.com/")
    tab_id = await get_tab_id(runner, "example.com")
    if tab_id is None:
        await page.close()
        return {"name": "contenteditable_canvas_type", "passed": False, "reason": "tab not found"}
    # Inject the contenteditable + give it focus
    await page.evaluate("""
      () => {
        const ed = document.createElement('div');
        ed.id = '__ed';
        ed.contentEditable = 'true';
        ed.style.cssText = 'border:1px solid;min-height:60px;padding:8px;outline:none';
        ed.tabIndex = 0;
        document.body.prepend(ed);
        ed.focus();
      }
    """)
    marker = f"AnticipyTest{uuid.uuid4().hex[:6]}"
    r = await call_content_action(runner, tab_id, {"type": "canvas_type", "text": marker})
    await asyncio.sleep(0.5)
    landed = await page.evaluate("(m) => (document.getElementById('__ed').innerText || '').includes(m)", marker)
    await page.close()
    ok = bool(r.get("success")) and landed
    return {"name": "contenteditable_canvas_type", "passed": ok, "reason": f"action_ok={r.get('success')} landed={landed} marker={marker}"}


async def scenario_form_completeness(ctx, runner) -> dict:
    """Multi-field form: each field must end up with a value. Inject a clean
    form onto a stable http page so the verifier and the action target the
    same input (no iframe ambiguity)."""
    page = await open_tab_at(ctx, "https://example.com/")
    tab_id = await get_tab_id(runner, "example.com")
    if tab_id is None:
        await page.close()
        return {"name": "form_completeness", "passed": False, "reason": "tab not found"}
    await page.evaluate("""
      () => {
        document.body.insertAdjacentHTML('afterbegin',
          '<form id="__f">' +
          '<input id="__fn" name="fname" placeholder="First">' +
          '<input id="__ln" name="lname" placeholder="Last">' +
          '<input id="__em" name="email" type="email" placeholder="Email">' +
          '</form>');
      }
    """)
    fields = [("fname", "Omar"), ("lname", "Ebrahim"), ("email", "omar@anticipy.ai")]
    for name, val in fields:
        await call_content_action(runner, tab_id, {
            "type": "type", "selector": f"input[name='{name}']", "value": val,
        })
    out = await page.evaluate("""
      () => ({
        fname: document.querySelector('input[name="fname"]').value,
        lname: document.querySelector('input[name="lname"]').value,
        email: document.querySelector('input[name="email"]').value,
      })
    """)
    await page.close()
    ok = out == {"fname": "Omar", "lname": "Ebrahim", "email": "omar@anticipy.ai"}
    return {"name": "form_completeness", "passed": ok, "reason": str(out)}


async def scenario_force_type_react(ctx, runner) -> dict:
    """A React-controlled input. Use force_type to ensure the value sticks.
    React playground's TodoMVC at todomvc.com/examples/react/ uses controlled inputs."""
    page = await open_tab_at(ctx, "https://todomvc.com/examples/react/dist/")
    tab_id = await get_tab_id(runner, "todomvc.com/examples/react")
    if tab_id is None:
        await page.close()
        return {"name": "force_type_react", "passed": False, "reason": "tab not found"}
    await asyncio.sleep(2)
    marker = f"buy milk {uuid.uuid4().hex[:4]}"
    r = await call_content_action(runner, tab_id, {
        "type": "force_type",
        "selector": "input.new-todo, input[placeholder*='What needs to be done']",
        "value": marker,
    })
    val = await page.evaluate(
        "document.querySelector('input.new-todo, input[placeholder*=\"What needs to be done\"]')?.value"
    )
    await page.close()
    ok = bool(r.get("success")) and val == marker
    return {"name": "force_type_react", "passed": ok, "reason": f"value={val!r} marker={marker!r}"}


async def scenario_canvas_pointer_dispatch(ctx, runner) -> dict:
    """Verify canvas_pointer dispatches a click an http page actually sees.
    Inject a click-counting canvas into a real http page and exercise it."""
    page = await open_tab_at(ctx, "https://example.com/")
    tab_id = await get_tab_id(runner, "example.com")
    if tab_id is None:
        await page.close()
        return {"name": "canvas_pointer_dispatch", "passed": False, "reason": "tab not found"}
    # Inject a fixed-position canvas at top-left so the test coords are stable
    await page.evaluate("""
      () => {
        const c = document.createElement('canvas');
        c.id = '__c';
        c.width = 400; c.height = 200;
        c.style.cssText = 'position:fixed;top:0;left:0;border:1px solid;background:#eee;z-index:9999';
        document.body.appendChild(c);
        window.__clicks = 0;
        const bump = () => { window.__clicks++; };
        c.addEventListener('mousedown', bump);
        c.addEventListener('pointerdown', bump);
      }
    """)
    r = await call_content_action(runner, tab_id, {
        "type": "canvas_pointer",
        "x": 100, "y": 50,
    })
    await asyncio.sleep(0.4)
    val = await page.evaluate("window.__clicks")
    await page.close()
    ok = bool(r.get("success")) and isinstance(val, int) and val >= 1
    return {"name": "canvas_pointer_dispatch", "passed": ok, "reason": f"clicks={val} ok={r.get('success')}"}


SCENARIOS = [
    scenario_wikipedia_search,
    scenario_duckduckgo_search,
    scenario_shadow_dom_pierce,
    scenario_pierce_query_youtube,
    scenario_contenteditable_canvas_type,
    scenario_form_completeness,
    scenario_force_type_react,
    scenario_canvas_pointer_dispatch,
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> int:
    profile_dir = f"/tmp/ext_actions_profile_{uuid.uuid4().hex[:8]}"
    os.makedirs(profile_dir, exist_ok=True)
    args = [
        f"--disable-extensions-except={EXT_DIR}",
        f"--load-extension={EXT_DIR}",
        "--no-sandbox",
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
        "--no-first-run",
        "--no-default-browser-check",
    ]

    results = []
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=False,
            args=args,
            viewport={"width": 1280, "height": 800},
        )
        try:
            ext_id = await wait_for_extension(ctx)
            if not ext_id:
                print("FAIL: extension not loaded", flush=True)
                return 1
            print(f"Extension id: {ext_id}", flush=True)
            # Give the SW time to register the MAIN-world shadow-open patch
            # before any tab navigates — registerContentScripts only applies
            # to FUTURE navigations.
            await asyncio.sleep(3)
            runner = await open_extension_runner(ctx, ext_id)

            for sc in SCENARIOS:
                name = sc.__name__.replace("scenario_", "")
                print(f"\n=== {name} ===", flush=True)
                t0 = time.time()
                try:
                    res = await asyncio.wait_for(sc(ctx, runner), timeout=90)
                except asyncio.TimeoutError:
                    res = {"name": name, "passed": False, "reason": "scenario timeout"}
                except Exception as e:
                    res = {"name": name, "passed": False, "reason": f"exception: {type(e).__name__}: {e}"}
                res["elapsed"] = round(time.time() - t0, 1)
                results.append(res)
                tag = "✓ PASS" if res["passed"] else "✗ FAIL"
                print(f"  {tag} ({res['elapsed']}s) {res['reason']}", flush=True)
        finally:
            try:
                await ctx.close()
            except Exception:
                pass

    import shutil
    shutil.rmtree(profile_dir, ignore_errors=True)

    print("\n" + "=" * 70)
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    pct = 100.0 * passed / total if total else 0
    print(f"RESULT: {passed}/{total} ({pct:.0f}%)")
    print("=" * 70)
    for r in results:
        tag = "✓" if r["passed"] else "✗"
        print(f"  {tag} {r['name']:<30} {r['reason']}")

    out = Path("/tmp/ext_actions_detail.json")
    out.write_text(json.dumps(results, indent=2))
    print(f"\nDetail: {out}")

    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
