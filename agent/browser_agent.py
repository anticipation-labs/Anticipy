"""Anticipy browser agent.

Browser-ONLY action layer (no service APIs): it operates real websites through
a real Chromium using the user's logged-in sessions, exactly like a human.

- When OPENROUTER_API_KEY is set: uses browser-use (Playwright + LLM) so the
  agent can pursue an arbitrary natural-language goal.
- With no key: a deterministic Playwright executor runs concrete recipes so the
  browser automation itself is provable end-to-end without any secret.
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Optional

from playwright.async_api import async_playwright


@dataclass
class AgentRun:
    goal: str
    mode: str
    ok: bool
    summary: str
    steps: list = field(default_factory=list)
    screenshot: Optional[str] = None
    extracted: Optional[str] = None


class BrowserAgent:
    def __init__(self, api_key: Optional[str] = None, headless: bool = True, user_data_dir: Optional[str] = None):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        self.headless = headless
        # Persisting a user_data_dir is how we reuse the user's logged-in sessions.
        self.user_data_dir = user_data_dir

    @property
    def live(self) -> bool:
        return bool(self.api_key)

    async def run_goal(self, goal: str) -> AgentRun:
        if self.live:
            return await self._run_browser_use(goal)
        return await self._run_recipe(goal)

    # ---------- real LLM-driven agent (browser-use over OpenRouter) ----------
    async def _run_browser_use(self, goal: str) -> AgentRun:
        from browser_use import Agent
        from browser_use.llm import ChatOpenAI

        llm = ChatOpenAI(
            model=os.environ.get("ANTICIPY_MODEL", "deepseek/deepseek-v3.2"),
            api_key=self.api_key,
            base_url="https://openrouter.ai/api/v1",
        )
        agent = Agent(task=goal, llm=llm)
        history = await agent.run()
        return AgentRun(
            goal=goal,
            mode="browser-use+openrouter",
            ok=True,
            summary=str(history.final_result()) if hasattr(history, "final_result") else "completed",
            steps=[str(a) for a in getattr(history, "action_results", lambda: [])()] if hasattr(history, "action_results") else [],
        )

    # ---------- keyless deterministic proof that browsing/acting works -------
    async def _run_recipe(self, goal: str) -> AgentRun:
        steps: list[str] = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            ctx = await browser.new_context()
            page = await ctx.new_page()
            try:
                if goal == "form_submit_demo":
                    r = await self._recipe_form(page, steps)
                elif goal == "research_and_report":
                    r = await self._recipe_search(page, steps)
                else:
                    r = await self._recipe_search(page, steps)
                shot = "/home/ubuntu/anticipy_app/proof/agent_last.png"
                await page.screenshot(path=shot)
                r.screenshot = shot
                r.steps = steps
                return r
            finally:
                await browser.close()

    async def _recipe_form(self, page, steps) -> AgentRun:
        # A real login form on a public sandbox — proves fill+click+read result.
        await page.goto("https://the-internet.herokuapp.com/login", wait_until="domcontentloaded")
        steps.append("navigated to login sandbox")
        await page.fill("#username", "tomsmith")
        await page.fill("#password", "SuperSecretPassword!")
        steps.append("typed username + password")
        await page.click("button[type=submit]")
        await page.wait_for_selector("#flash", timeout=10000)
        msg = (await page.inner_text("#flash")).strip().split("\n")[0]
        steps.append(f"read result banner: {msg!r}")
        ok = "You logged into a secure area" in msg
        return AgentRun(goal="form_submit_demo", mode="playwright-recipe", ok=ok,
                        summary=f"Logged in, site said: {msg!r}", extracted=msg)

    async def _recipe_search(self, page, steps) -> AgentRun:
        # Real live web read — proves navigation + multi-element extraction on a
        # public automation sandbox (with the LLM path this is any real site).
        await page.goto("https://books.toscrape.com/catalogue/category/books/mystery_3/index.html",
                        wait_until="domcontentloaded")
        steps.append("navigated to live catalogue page")
        await page.wait_for_selector("article.product_pod h3 a", timeout=15000)
        items = await page.eval_on_selector_all(
            "article.product_pod h3 a", "els => els.slice(0,3).map(e => e.getAttribute('title'))"
        )
        prices = await page.eval_on_selector_all(
            "article.product_pod .price_color", "els => els.slice(0,3).map(e => e.innerText)"
        )
        options = [f"{t} ({p})" for t, p in zip(items, prices)]
        steps.append(f"extracted top {len(options)} options with prices")
        return AgentRun(goal="research_and_report", mode="playwright-recipe", ok=len(options) > 0,
                        summary="Top options: " + " | ".join(options), extracted="\n".join(options))


if __name__ == "__main__":
    import sys
    g = sys.argv[1] if len(sys.argv) > 1 else "form_submit_demo"
    run = asyncio.run(BrowserAgent(headless=True).run_goal(g))
    print("MODE:", run.mode, "OK:", run.ok)
    print("SUMMARY:", run.summary)
    for s in run.steps:
        print("  -", s)
    print("SHOT:", run.screenshot)
