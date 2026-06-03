"""Validate the adoption stack: browser-use (0.12) + OpenRouter Gemini + vision,
driving a Chrome over CDP. Run with the .venv-bu (3.11) python.
Usage: _bu_probe.py [cdp_url]
"""
import asyncio
import os
import sys
from pathlib import Path


def load_env():
    p = Path(__file__).resolve().parents[2] / ".env.local"
    for line in p.read_text().splitlines():
        if line.startswith("OPENROUTER_API_KEY="):
            os.environ["OPENROUTER_API_KEY"] = line.split("=", 1)[1].strip()


load_env()
from browser_use import Agent, BrowserSession, ChatOpenAI


async def main():
    cdp = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:9223"
    llm = ChatOpenAI(model="google/gemini-3-flash-preview", base_url="https://openrouter.ai/api/v1",
                     api_key=os.environ["OPENROUTER_API_KEY"], temperature=0.1)
    session = BrowserSession(cdp_url=cdp)
    agent = Agent(
        task="Go to https://example.com and report the exact main heading (H1) text on the page.",
        llm=llm, browser_session=session, use_vision=True)
    hist = await agent.run(max_steps=6)
    try:
        print("FINAL:", hist.final_result())
    except Exception as e:
        print("history type:", type(hist).__name__, "| err:", e)
        print("repr:", repr(hist)[:300])


if __name__ == "__main__":
    asyncio.run(main())
