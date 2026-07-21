"""Real-world scenario demos: spoken line -> live LLM triage -> action.

Run with OPENROUTER_API_KEY set. Browser windows are launched visibly
(headless=False) so the run can be screen-recorded.
"""
import asyncio
import json
import os
import sys

import httpx

sys.path.insert(0, "/home/ubuntu/anticipy_app")
from brain.orchestrator import Brain  # noqa: E402

PB = "http://127.0.0.1:8090"


async def run_browser_goal(task: str) -> str:
    from browser_use import Agent, BrowserSession
    from browser_use.llm import ChatOpenAI

    llm = ChatOpenAI(
        model=os.environ.get("ANTICIPY_MODEL", "deepseek/deepseek-v3.2"),
        api_key=os.environ["OPENROUTER_API_KEY"],
        base_url="https://openrouter.ai/api/v1",
    )
    session = BrowserSession(headless=False)
    agent = Agent(task=task, llm=llm, browser_session=session)
    history = await agent.run(max_steps=18)
    return history.final_result() or "(no result)"


async def main():
    brain = Brain()
    assert brain.llm.live

    scenarios = [
        ("small talk", "Haha no way, that ending was ridiculous, I can't believe he did that."),
        ("dinner", "We should grab Italian food somewhere nice downtown this weekend."),
        ("price check", "Hold on, let me check what mystery novels are going for these days."),
        ("pitch deck", "I'll send you the pitch deck right after this call, I promise."),
    ]

    for name, line in scenarios:
        print(f"\n=== SCENARIO: {name} ===")
        print(f'heard: "{line}"')
        d = brain.triage(line)
        print(f"brain: {d.decision} | goal={d.goal!r} | {d.reason}")

        if d.decision == "ignore":
            print("-> stayed silent (correct).")
            continue
        if d.decision == "ask":
            print("-> would text you a short clarifying question (correct for ambiguity).")

        if name == "dinner":
            result = await run_browser_goal(
                "Search duckduckgo.com for 'best italian restaurants downtown Vancouver'. "
                "Open one promising results page and report the names of 3 restaurants you find."
            )
            print(f"-> agent research result:\n{result}")
            print("-> would text: 'Found 3 spots. Want me to check availability and book?'")
        elif name == "price check":
            result = await run_browser_goal(
                "Go to https://books.toscrape.com/catalogue/category/books/mystery_3/index.html "
                "and report the price range of the first 5 mystery books."
            )
            print(f"-> agent research result:\n{result}")
        elif name == "pitch deck":
            async with httpx.AsyncClient() as c:
                r = await c.post(f"{PB}/api/collections/jobs/records", json={
                    "goal": "draft_and_send_document", "status": "awaiting_confirm",
                    "params": json.dumps({"to": "investor@example.com",
                                          "subject": "Anticipy — pitch deck",
                                          "body": "Great speaking today — deck attached."}),
                    "device_id": "scenario-demo",
                })
                job = r.json()
            print(f"-> draft prepared, job {job['id']} status: {job['status']}")
            print("-> IRREVERSIBLE: stops here. Texts you: 'Draft ready for the investor — send it?'")
            print("   (an SMS reply of YES flips this job to queued and the extension sends it)")

    print("\nSCENARIO DEMOS COMPLETE")


if __name__ == "__main__":
    asyncio.run(main())
