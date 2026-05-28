"""
Patchright browser management with anti-detection, humanization,
persistent profiles, iframe traversal, multi-tab, Cloudflare handling,
and encrypted cookie storage.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import time
from typing import Any
from urllib.parse import urlparse

from cryptography.fernet import Fernet
from patchright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright

from app import supabase_client
from app.config import (
    PROFILE_ENCRYPTION_KEY,
    BROWSER_PROFILE_BASE,
    BROWSER_ACTION_TIMEOUT,
    BROWSER_NAV_TIMEOUT,
    MAX_BROWSER_TASKS,
)


# --- Encryption helpers ---

_fernet = Fernet(PROFILE_ENCRYPTION_KEY.encode() if isinstance(PROFILE_ENCRYPTION_KEY, str) else PROFILE_ENCRYPTION_KEY)


def _encrypt(data: str) -> str:
    """Encrypt a string with Fernet, return base64 token."""
    return _fernet.encrypt(data.encode("utf-8")).decode("utf-8")


def _decrypt(token: str) -> str:
    """Decrypt a Fernet token back to string."""
    return _fernet.decrypt(token.encode("utf-8")).decode("utf-8")


# --- Humanization ---

async def humanize(page: Page, action_type: str = "click") -> None:
    """Add human-like delays and occasional mouse jitter before actions."""
    await asyncio.sleep(random.uniform(0.15, 0.6))
    if random.random() < 0.15:
        x = random.randint(100, 800)
        y = random.randint(100, 500)
        await page.mouse.move(x, y, steps=random.randint(3, 8))
        await asyncio.sleep(random.uniform(0.05, 0.15))


async def human_type(page: Page, locator, text: str) -> None:
    """Type text with realistic but efficient input."""
    await locator.click(timeout=BROWSER_ACTION_TIMEOUT)
    await asyncio.sleep(random.uniform(0.1, 0.2))
    # Use fill for speed and reliability, with a slight pause
    await locator.fill(str(text), timeout=BROWSER_ACTION_TIMEOUT)
    await asyncio.sleep(random.uniform(0.1, 0.3))


async def human_scroll(page: Page, direction: str = "down") -> None:
    """Scroll with randomized distance and speed."""
    distance = random.randint(300, 700)
    if direction == "up":
        distance = -distance
    steps = random.randint(3, 8)
    step_size = distance // steps
    for _ in range(steps):
        await page.mouse.wheel(0, step_size)
        await asyncio.sleep(random.uniform(0.05, 0.15))
    await asyncio.sleep(random.uniform(0.2, 0.5))


# --- Cloudflare / redirect helpers ---

async def wait_for_cloudflare(page: Page, timeout: int = 15000) -> None:
    """Wait for Cloudflare challenge to resolve if present."""
    try:
        cf = page.locator(
            "#challenge-running, #cf-challenge-running, .cf-browser-verification"
        )
        if await cf.count() > 0:
            await cf.first.wait_for(state="hidden", timeout=timeout)
    except Exception:
        pass
    try:
        await page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        pass


async def wait_for_url_stable(page: Page, checks: int = 5, interval: float = 1.0) -> str:
    """Wait for URL to stabilize after redirects."""
    last_url = page.url
    for _ in range(checks):
        await asyncio.sleep(interval)
        current = page.url
        if current == last_url:
            return current
        last_url = current
    return page.url


async def detect_spa_navigation(page: Page, old_content_hash: str) -> bool:
    """Detect SPA navigation by checking if page content changed."""
    try:
        new_text = await page.inner_text("body", timeout=3000)
        new_hash = str(hash(new_text[:500]))
        return new_hash != old_content_hash
    except Exception:
        return False


# --- Popup dismissal ---

POPUP_SELECTORS = [
    '[class*="overlay"] button[class*="close"]',
    '[class*="modal"] button[class*="close"]',
    '[class*="popup"] button[class*="close"]',
    '[aria-label="Close"]',
    '[aria-label="Dismiss"]',
    'button[class*="dismiss"]',
    '[class*="cookie"] button',
    '[id*="cookie"] button',
    '[class*="consent"] button',
    '[class*="banner"] button[class*="close"]',
    '.intercom-close-button',
    '[class*="notification"] button[class*="close"]',
]


async def dismiss_popups(page: Page) -> None:
    """Try to dismiss common overlays and popups."""
    for selector in POPUP_SELECTORS:
        try:
            loc = page.locator(selector).first
            if await loc.is_visible(timeout=500):
                await loc.click(timeout=2000)
                await asyncio.sleep(0.3)
                return
        except Exception:
            continue


class BrowserManager:
    """Manages a persistent Chromium context with anti-detection and humanization."""

    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._pages: list[Page] = []
        self._task_count: int = 0
        self._user_id: str | None = None

    async def launch(self, user_id: str | None = None) -> None:
        """Launch Chromium with persistent profile using patchright."""
        self._user_id = user_id
        self._playwright = await async_playwright().start()

        profile_dir = os.path.join(BROWSER_PROFILE_BASE, user_id or "_anonymous")
        os.makedirs(profile_dir, exist_ok=True)

        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-infobars",
            "--disable-gpu",
            "--window-size=1920,1080",
        ]

        try:
            self._context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                channel="chrome",
                headless=False,
                no_viewport=True,
                args=launch_args,
                locale="en-US",
                java_script_enabled=True,
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
        except Exception:
            # Fallback: launch without channel specification
            self._context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                headless=False,
                no_viewport=True,
                args=launch_args,
                locale="en-US",
                java_script_enabled=True,
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )

        # Stealth: override navigator.webdriver
        await self._context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        # Listen for new pages (tabs)
        self._context.on("page", self._handle_new_page)

        # Use existing page or create new one
        if self._context.pages:
            self._page = self._context.pages[0]
        else:
            self._page = await self._context.new_page()
        self._pages = list(self._context.pages)

    def _handle_new_page(self, page: Page) -> None:
        """Track new tabs opened by the page."""
        self._pages.append(page)
        self._page = page  # Switch focus to newest tab

    async def new_context(self, user_id: str | None = None) -> Page:
        """Create context (for compatibility). Returns active page."""
        if not self._context:
            await self.launch(user_id)
        return self._page

    @property
    def page(self) -> Page | None:
        return self._page

    async def switch_to_latest_tab(self) -> Page | None:
        """Switch focus to the most recently opened tab."""
        if self._context and self._context.pages:
            self._pages = list(self._context.pages)
            self._page = self._pages[-1]
            return self._page
        return None

    async def navigate(self, url: str) -> None:
        """Navigate to URL with Cloudflare handling and URL stabilization."""
        if not self._page:
            return
        try:
            await self._page.goto(url, wait_until="networkidle", timeout=BROWSER_NAV_TIMEOUT)
        except Exception:
            try:
                await self._page.goto(url, wait_until="load", timeout=BROWSER_NAV_TIMEOUT)
            except Exception:
                pass

        await wait_for_cloudflare(self._page)
        await self.wait_for_interactive_content(min_elements=2, max_wait=3.0)

    async def get_accessibility_tree(self) -> dict | None:
        """Get merged accessibility tree from all frames."""
        if not self._page:
            return None

        merged_children: list[dict] = []

        for frame in self._page.frames:
            try:
                frame_tree = await frame.accessibility.snapshot()
                if frame_tree:
                    if frame == self._page.main_frame:
                        # Main frame is the root
                        merged_children = frame_tree.get("children", [])
                        root_tree = frame_tree
                    else:
                        # Iframe elements get appended
                        children = frame_tree.get("children", [])
                        if children:
                            merged_children.extend(children)
            except Exception:
                continue

        if not merged_children:
            # Fallback: try main frame only
            try:
                tree = await self._page.accessibility.snapshot()
                return tree
            except Exception:
                return None

        try:
            root_tree["children"] = merged_children
            return root_tree
        except Exception:
            return {"role": "WebArea", "name": "", "children": merged_children}

    async def get_url(self) -> str:
        """Return current page URL."""
        if not self._page:
            return ""
        return self._page.url

    async def get_title(self) -> str:
        """Return current page title."""
        if not self._page:
            return ""
        try:
            return await self._page.title()
        except Exception:
            return ""

    async def execute_action(self, action: dict, elements: list[dict]) -> bool:
        """
        Execute a parsed action dict against the page.
        Calls humanize() before every action, dismiss_popups() before interaction.
        Returns True on success, False on failure.
        """
        if not self._page:
            return False

        act = action.get("action", "")
        target_label = action.get("target")
        value = action.get("value")

        try:
            # Dismiss popups before interaction actions
            if act in ("click", "type", "select"):
                await dismiss_popups(self._page)

            if act == "click" and target_label:
                await humanize(self._page, "click")
                node = self._find_element(target_label, elements)
                if node:
                    name = node.get("name", "")
                    role = node.get("role", "")
                    locator = self._build_locator(name, role)
                    if locator:
                        await locator.click(timeout=BROWSER_ACTION_TIMEOUT)
                        await self._wait_stable()
                        return True
                return False

            elif act == "type" and target_label and value is not None:
                await humanize(self._page, "type")
                node = self._find_element(target_label, elements)
                if node:
                    name = node.get("name", "")
                    role = node.get("role", "")
                    locator = self._build_locator(name, role)
                    if locator:
                        await human_type(self._page, locator, str(value))
                        await self._wait_stable()
                        return True
                return False

            elif act == "select" and target_label and value is not None:
                await humanize(self._page, "select")
                node = self._find_element(target_label, elements)
                if node:
                    name = node.get("name", "")
                    role = node.get("role", "")
                    locator = self._build_locator(name, role)
                    if locator:
                        await locator.select_option(label=str(value), timeout=BROWSER_ACTION_TIMEOUT)
                        await self._wait_stable()
                        return True
                return False

            elif act == "scroll":
                await humanize(self._page, "scroll")
                direction = str(value or "down").lower()
                await human_scroll(self._page, direction)
                await self._wait_stable()
                return True

            elif act == "navigate" and value:
                await humanize(self._page, "navigate")
                url = str(value)
                if not url.startswith("http"):
                    url = "https://" + url
                await self.navigate(url)
                return True

            elif act == "go_back":
                await humanize(self._page, "navigate")
                await self._page.go_back(wait_until="networkidle", timeout=BROWSER_ACTION_TIMEOUT)
                await self._wait_stable()
                return True

            elif act in ("done", "stuck", "need_info"):
                return True

        except Exception:
            return False

        return False

    def _find_element(self, label: str, elements: list[dict]) -> dict | None:
        """Find the element dict by its label letter."""
        for elem in elements:
            if elem.get("label") == label:
                return elem
        return None

    def _build_locator(self, name: str, role: str):
        """Build a Playwright locator from element name and role."""
        if not self._page or not name:
            return None

        role_map = {
            "button": "button",
            "link": "link",
            "textbox": "textbox",
            "searchbox": "searchbox",
            "combobox": "combobox",
            "checkbox": "checkbox",
            "radio": "radio",
            "switch": "switch",
            "tab": "tab",
            "menuitem": "menuitem",
            "option": "option",
            "slider": "slider",
            "spinbutton": "spinbutton",
        }

        aria_role = role_map.get(role)
        if aria_role:
            return self._page.get_by_role(aria_role, name=name, exact=False)

        # Fallback: use text-based locator
        return self._page.get_by_text(name, exact=False)

    async def _wait_stable(self) -> None:
        """Wait for page to settle after an action."""
        try:
            await self._page.wait_for_load_state("domcontentloaded", timeout=3000)
        except Exception:
            pass
        # Brief extra wait for JS-rendered content
        await asyncio.sleep(0.5)

    async def wait_for_interactive_content(self, min_elements: int = 3, max_wait: float = 5.0) -> None:
        """Wait until the page has enough interactive elements loaded."""
        if not self._page:
            return
        start = time.time()
        while time.time() - start < max_wait:
            try:
                tree = await self._page.accessibility.snapshot()
                if tree:
                    from app.harness import extract_interactive_elements
                    elements = extract_interactive_elements(tree)
                    if len(elements) >= min_elements:
                        return
            except Exception:
                pass
            await asyncio.sleep(0.5)

    async def take_screenshot(self) -> bytes | None:
        """Take a screenshot of the current page. Returns PNG bytes."""
        if not self._page:
            return None
        try:
            return await self._page.screenshot(type="png", timeout=BROWSER_ACTION_TIMEOUT)
        except Exception:
            return None

    async def get_page_text(self) -> str:
        """Get visible text content of the page (limited)."""
        if not self._page:
            return ""
        try:
            text = await self._page.inner_text("body", timeout=3000)
            return text[:4000]
        except Exception:
            return ""

    async def detect_canvas_heavy(self) -> bool:
        """Detect if the page is canvas-heavy (e.g., Google Maps, games)."""
        if not self._page:
            return False
        try:
            canvas_count = await self._page.evaluate(
                "() => document.querySelectorAll('canvas').length"
            )
            return canvas_count >= 2
        except Exception:
            return False

    async def save_cookies(self, user_id: str, domain: str) -> None:
        """Save context cookies encrypted to Supabase browser_profiles table."""
        if not self._context:
            return
        try:
            cookies = await self._context.cookies()
            cookies_json = json.dumps(cookies)
            encrypted = _encrypt(cookies_json)
            await supabase_client.upsert_row(
                "browser_profiles",
                {
                    "user_id": user_id,
                    "site_domain": domain,
                    "cookies_json": encrypted,
                    "updated_at": "now()",
                },
            )
        except Exception:
            pass

    async def load_cookies(self, user_id: str, domain: str) -> None:
        """Load saved cookies from Supabase, decrypt, and add to context."""
        if not self._context:
            return
        try:
            rows = await supabase_client.select_rows(
                "browser_profiles",
                filters={"user_id": user_id, "site_domain": domain},
                limit=1,
            )
            if rows:
                encrypted = rows[0].get("cookies_json", "")
                if not encrypted:
                    return
                try:
                    cookies_json = _decrypt(encrypted)
                except Exception:
                    # Fallback: try reading as plaintext (legacy data)
                    cookies_json = encrypted
                cookies = json.loads(cookies_json)
                if cookies:
                    await self._context.add_cookies(cookies)
        except Exception:
            pass

    def should_restart(self) -> bool:
        """Check if browser should be restarted due to task count."""
        self._task_count += 1
        return self._task_count >= MAX_BROWSER_TASKS

    async def close(self) -> None:
        """Close browser and all contexts."""
        try:
            if self._context:
                await self._context.close()
        except Exception:
            pass
        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass
        self._page = None
        self._pages = []
        self._context = None
        self._playwright = None
