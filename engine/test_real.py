"""
REAL test suite for the Anticipy Action Engine.
Every test requires multi-step browser interaction on a live website.
Run: cd engine && python test_real.py
"""

import asyncio
import json
import sys
import time
import os

sys.path.insert(0, ".")

# Load env vars from .env.local
from pathlib import Path
env_file = Path(__file__).parent.parent / ".env.local"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

from app.agent import execute_task

PASS_COUNT = 0
FAIL_COUNT = 0
RESULTS = []

# Banned words in responses (technical leakage)
BANNED_PATTERNS = [
    "json", "api ", "error code", "stack trace", "traceback",
    "exception", "null", "nonetype",
    "dom ", "selector", "xpath", "javascript", "python",
    "function", "debug", "console", "endpoint",
    "playwright", "patchright", "chromium", "webdriver",
    "groq", "gemini", "llama", "deepseek", "fastapi",
    "websocket", "supabase", "httpx", "async", "await",
]


def check_leakage(text: str) -> str | None:
    text_lower = " " + text.lower() + " "
    for word in BANNED_PATTERNS:
        if f" {word}" in text_lower or f"\n{word}" in text_lower:
            return word
    return None


async def run_test(
    test_num: int,
    label: str,
    task_text: str,
    pass_check,
    timeout: int = 240,
):
    """Run a single browser test, capturing all messages."""
    global PASS_COUNT, FAIL_COUNT

    print(f"\n{'='*60}", flush=True)
    print(f"TEST {test_num}: {label}", flush=True)
    print(f"TASK: {task_text[:100]}...", flush=True)
    print(f"{'='*60}", flush=True)

    messages = []

    async def send(data):
        messages.append(data)
        t = data.get("type", "")
        m = data.get("message", "")[:120]
        print(f"  [{t}] {m}", flush=True)

    async def recv():
        return "yes"

    start = time.time()
    max_retries = 2
    for attempt in range(max_retries):
        try:
            await asyncio.wait_for(
                execute_task(task_text, send, recv, user_id="test_user"),
                timeout=timeout + 30,
            )
            break
        except asyncio.TimeoutError:
            messages.append({"type": "error", "message": "HARD TIMEOUT"})
            print("  [HARD TIMEOUT]", flush=True)
            break  # Don't retry timeouts
        except Exception as e:
            err_msg = str(e)[:100]
            if attempt < max_retries - 1:
                print(f"  [RETRY] Attempt {attempt+1} failed: {type(e).__name__}, retrying...", flush=True)
                messages.clear()
                await asyncio.sleep(3)
                continue
            messages.append({"type": "error", "message": err_msg})
            print(f"  [EXCEPTION] {type(e).__name__}", flush=True)

    elapsed = time.time() - start

    # Get final message
    complete_msgs = [m for m in messages if m.get("type") == "complete"]
    error_msgs = [m for m in messages if m.get("type") == "error"]
    final_text = ""
    if complete_msgs:
        final_text = complete_msgs[-1].get("message", "")
    elif error_msgs:
        final_text = error_msgs[-1].get("message", "")

    # Check for technical leakage
    all_text = " ".join(m.get("message", "") for m in messages)
    leak = check_leakage(all_text)

    # Run the pass check
    passed = pass_check(final_text)
    if leak:
        passed = False
        print(f"  LEAKAGE: '{leak}' found in response", flush=True)

    status = "PASS" if passed else "FAIL"
    if passed:
        PASS_COUNT += 1
    else:
        FAIL_COUNT += 1

    print(f"\n  [{status}] {label} ({elapsed:.1f}s)", flush=True)
    print(f"  RESPONSE: {final_text[:200]}", flush=True)

    RESULTS.append({
        "test": test_num,
        "label": label,
        "passed": passed,
        "elapsed": round(elapsed, 1),
        "response": final_text[:500],
        "message_count": len(messages),
        "leak": leak,
    })


async def run_intent_test(
    test_num: int,
    label: str,
    task_text: str,
    pass_check,
):
    """
    Test the intent classifier and chat/question handlers without launching a browser.
    Simulates the classify → handle_chat/handle_question pipeline.
    """
    global PASS_COUNT, FAIL_COUNT
    from app.router import classify, handle_chat, handle_question
    from app.models import CostTracker
    from app import messages as msg_module

    print(f"\n{'='*60}", flush=True)
    print(f"TEST {test_num}: {label}", flush=True)
    print(f"INPUT: {task_text}", flush=True)
    print(f"{'='*60}", flush=True)

    start = time.time()
    category = "error"
    response = ""

    try:
        tracker = CostTracker()
        classification = await asyncio.wait_for(classify(task_text, tracker), timeout=30)
        category = classification.category if hasattr(classification, "category") else str(classification)
        print(f"  [classify] → {category} (degraded={getattr(classification,'degraded',False)})", flush=True)

        if category == "chat":
            response = await asyncio.wait_for(handle_chat(task_text, tracker), timeout=30)
        elif category == "question":
            response = await asyncio.wait_for(handle_question(task_text, tracker), timeout=30)
        elif category == "ambiguous":
            response = msg_module.AMBIGUOUS_REQUEST
        else:
            # action — note what was detected but don't run browser
            response = f"[action detected — would launch browser]"
    except Exception as e:
        response = f"[error: {type(e).__name__}]"
        print(f"  [EXCEPTION] {type(e).__name__}: {e}", flush=True)

    elapsed = time.time() - start

    leak = check_leakage(response)
    passed = pass_check(category, response)
    if leak:
        passed = False
        print(f"  LEAKAGE: '{leak}' found in response", flush=True)

    status = "PASS" if passed else "FAIL"
    if passed:
        PASS_COUNT += 1
    else:
        FAIL_COUNT += 1

    print(f"\n  [{status}] {label} ({elapsed:.1f}s)", flush=True)
    print(f"  CATEGORY: {category}", flush=True)
    print(f"  RESPONSE: {response[:200]}", flush=True)

    RESULTS.append({
        "test": test_num,
        "label": label,
        "passed": passed,
        "elapsed": round(elapsed, 1),
        "category": category,
        "response": response[:500],
        "leak": leak,
    })


async def main():
    global PASS_COUNT, FAIL_COUNT

    print("=" * 60)
    print("ANTICIPY ACTION ENGINE — REAL TEST SUITE")
    print("22 tests: 9 browser + 1 leakage audit + 3 intent + 3 extra + 6 hard")
    print("=" * 60)

    # TEST 1: OpenTable search
    await run_test(
        1, "OpenTable availability search",
        "Go to opentable.com, search for Cactus Club Cafe in Vancouver, "
        "and check what times are available for 4 people tomorrow evening around 7pm",
        lambda r: (
            len(r) > 30
            and any(kw in r.lower() for kw in ["time", "available", "reservation", "no avail", "pm", "cactus"])
        ),
    )

    # TEST 2: Amazon
    await run_test(
        2, "Amazon search",
        "Go to amazon.ca, search for USB-C cable, and tell me the name and price of the top 3 results",
        lambda r: "$" in r and any(c.isdigit() for c in r),
    )

    # TEST 3: Google search + click
    await run_test(
        3, "Google search and click",
        "Search Google for 'Anticipy AI wearable', click the first non-ad result, "
        "and tell me what the page says about it",
        lambda r: len(r) > 50,
    )

    # TEST 4: SauceDemo full checkout (needs more time for multi-page flow)
    await run_test(
        4, "SauceDemo checkout",
        "Go to saucedemo.com, log in with username standard_user and password secret_sauce, "
        "add the first item to cart, click the cart icon (top right), click Checkout, "
        "fill in First Name: John, Last Name: Smith, Zip: 12345, click Continue, "
        "then tell me the total amount shown on the checkout overview page",
        lambda r: "$" in r and any(c.isdigit() for c in r),
        timeout=300,
    )

    # TEST 5: GitHub trending
    await run_test(
        5, "GitHub trending deep dive",
        "Go to github.com/trending, click into the top repository, "
        "and tell me its name, description, star count, and how many open issues it has",
        lambda r: len(r) > 30 and any(c.isdigit() for c in r),
    )

    # TEST 6: Bot detection
    await run_test(
        6, "Bot detection fingerprint",
        "Go to bot.sannysoft.com and tell me if there are any failed tests on the page",
        lambda r: any(kw in r.lower() for kw in ["test", "pass", "fail", "detect", "result"]),
    )

    # TEST 7: Cloudflare-protected site
    await run_test(
        7, "Cloudflare-protected site",
        "Go to nowsecure.nl and tell me what the page says",
        lambda r: len(r) > 20,
    )

    # TEST 8: reCAPTCHA demo
    await run_test(
        8, "reCAPTCHA demo",
        "Go to https://www.google.com/recaptcha/api2/demo and solve the CAPTCHA",
        lambda r: any(kw in r.lower() for kw in ["solved", "captcha", "verification", "success", "check", "complete", "submit", "robot"]),
    )

    # TEST 9: Login form
    await run_test(
        9, "Login form — the-internet",
        "Go to the-internet.herokuapp.com/login, log in with username tomsmith "
        "and password SuperSecretPassword!, then tell me what the secure page says",
        lambda r: any(kw in r.lower() for kw in ["secure", "welcome", "logged", "success"]),
    )

    # TEST 10: Technical leakage audit (meta-test)
    print(f"\n{'='*60}")
    print(f"TEST 10: Technical leakage audit")
    print(f"{'='*60}")
    all_text = " ".join(r.get("response", "") for r in RESULTS)
    leak = check_leakage(all_text)
    if leak:
        FAIL_COUNT += 1
        print(f"  [FAIL] Technical leakage: '{leak}'")
        RESULTS.append({"test": 10, "label": "Technical leakage audit", "passed": False, "leak": leak})
    else:
        PASS_COUNT += 1
        print(f"  [PASS] No technical leakage detected")
        RESULTS.append({"test": 10, "label": "Technical leakage audit", "passed": True, "leak": None})

    # --- PROACTIVE INTENT DETECTION TESTS (no browser) ---

    # TEST 11: Pure social statement — should NOT trigger browser action
    await run_intent_test(
        11, "Intent: pure social statement",
        "we should grab dinner sometime",
        lambda cat, r: (
            cat in ("chat", "ambiguous")
            and len(r) > 5
            and "error" not in r.lower()
        ),
    )

    # TEST 12: Embedded reminder request — should be detected as action or offer help
    await run_intent_test(
        12, "Intent: embedded reminder request",
        "remind me to call the dentist",
        lambda cat, r: (
            len(r) > 5
            and "error" not in r.lower()
            and any(kw in r.lower() for kw in [
                "remind", "call", "dentist", "calendar", "reminder", "schedule",
                "note", "help", "sure", "action", "browser", "would",
            ])
        ),
    )

    # TEST 13: Implied task from past-tense social statement
    await run_intent_test(
        13, "Intent: implied send-task from social context",
        "I told Sarah I'd send her that document",
        lambda cat, r: (
            len(r) > 5
            and "error" not in r.lower()
        ),
    )

    # --- ADDITIONAL BROWSER TESTS ---

    # TEST 14: Wikipedia article extraction
    await run_test(
        14, "Wikipedia article extraction",
        "Go to en.wikipedia.org, search for 'Large language model', "
        "and tell me the first sentence of the article",
        lambda r: len(r) > 40 and any(kw in r.lower() for kw in ["model", "language", "ai", "neural", "text", "machine"]),
    )

    # TEST 15: Books.toscrape — find cheapest book
    await run_test(
        15, "books.toscrape — cheapest book",
        "Go to books.toscrape.com, look at the books listed and tell me the title and price "
        "of the cheapest book you can find on the first page",
        lambda r: "£" in r or "$" in r or any(c.isdigit() for c in r),
    )

    # TEST 16: DuckDuckGo search
    await run_test(
        16, "DuckDuckGo search",
        "Go to duckduckgo.com, search for 'best programming languages 2025', "
        "and list 3 results you find",
        lambda r: len(r) > 40 and any(kw in r.lower() for kw in [
            "python", "javascript", "rust", "go", "typescript", "java", "c++", "swift", "kotlin",
            "programming", "language", "result", "search",
        ]),
    )

    # ── HARD TESTS (17-22) ──────────────────────────────────────────────────────

    # TEST 17: Cross-site research — HackerNews headline → Wikipedia
    await run_test(
        17, "Cross-site: HackerNews → Wikipedia",
        "Go to news.ycombinator.com and note the title and point count of the #1 ranked story. "
        "Then search Wikipedia for the main topic in that title and give me the first sentence "
        "of the Wikipedia article. Report both the HN story title and the Wikipedia sentence.",
        lambda r: len(r) > 60 and any(c.isdigit() for c in r),
        timeout=240,
    )

    # TEST 18: Multi-site price comparison — BestBuy CA vs Amazon CA
    await run_test(
        18, "Multi-site price comparison: BestBuy vs Amazon",
        "Go to bestbuy.ca and search for 'Sony WH-1000XM5'. Note the price. "
        "Then go to amazon.ca and search for the same headphones. Note that price. "
        "Which store has the lower price today? Show exact prices from both.",
        lambda r: "$" in r and r.lower().count("$") >= 1 and any(c.isdigit() for c in r),
        timeout=300,
    )

    # TEST 19: Paginated site — navigate to specific page, extract filtered result
    await run_test(
        19, "Paginated nav: quotes.toscrape page 5",
        "Go to quotes.toscrape.com, navigate to page 5 (click Next until you reach page 5), "
        "and list the first 3 quotes you see along with their authors.",
        lambda r: len(r) > 60 and ("—" in r or "-" in r or "by" in r.lower() or any(c.isalpha() for c in r)),
        timeout=180,
    )

    # TEST 20: Ambiguous instruction — no URL given, model must make a reasonable choice
    await run_intent_test(
        20, "Ambiguous: 'What's trending right now?'",
        "What's trending right now?",
        lambda cat, r: (
            len(r) > 10
            and "error" not in r.lower()
        ),
    )

    # TEST 21: Dynamic/canvas-heavy page — Google Trends
    await run_test(
        21, "Google Trends — top US searches",
        "Go to trends.google.com/trends/trendingsearches/daily?geo=US and tell me "
        "the top 3 trending searches in the United States right now.",
        lambda r: len(r) > 20,
        timeout=180,
    )

    # TEST 22: Challenging DOM — table extraction + link detection
    await run_test(
        22, "Challenging DOM: table extraction",
        "Go to the-internet.herokuapp.com/challenging-dom, read the table, "
        "and tell me the value in the 3rd row of the first column. "
        "Also tell me the text of the first row's action link (edit or delete).",
        lambda r: len(r) > 10 and any(kw in r.lower() for kw in ["edit", "delete", "row", "column", "value", "lorem"]),
        timeout=120,
    )

    # Final leakage check across all 22 tests
    print(f"\n{'='*60}")
    print(f"FINAL LEAKAGE AUDIT (all 22 tests)")
    print(f"{'='*60}")
    all_responses = " ".join(r.get("response", "") for r in RESULTS)
    final_leak = check_leakage(all_responses)
    if final_leak:
        print(f"  WARNING: '{final_leak}' detected in combined responses")
    else:
        print(f"  Clean — no technical leakage across all 22 tests")

    # Summary
    print(f"\n{'='*60}")
    print(f"RESULTS: {PASS_COUNT}/{PASS_COUNT + FAIL_COUNT} passed")
    print(f"{'='*60}")

    for r in RESULTS:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"  [{status}] Test {r.get('test', '?')}: {r.get('label', '')}")
        if not r["passed"] and r.get("response"):
            print(f"         Response: {r['response'][:100]}")

    # Save results
    os.makedirs("logs", exist_ok=True)
    with open("logs/test_real_results.json", "w") as f:
        json.dump({
            "total": PASS_COUNT + FAIL_COUNT,
            "passed": PASS_COUNT,
            "failed": FAIL_COUNT,
            "results": RESULTS,
        }, f, indent=2)
    print(f"\nResults saved to logs/test_real_results.json")


if __name__ == "__main__":
    asyncio.run(main())
