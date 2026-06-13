# Anticipy Product Status

Updated: 2026-06-13

This is the human product target. It intentionally avoids factory phase names.

## What Omar Wants Built

A user opens Anticipy, presses Go, or uploads/types/listens to a messy transcript of real life. The proactive engine understands the input, uses saved memory for context, creates clear task cards, executes safe actions with durable receipts, asks before actions that affect another human, never spends money, and closes loops through the app, memory, browser/API hands, and text/call replies.

Done means this works together as one product, not as isolated demos.

## What Is Proven Now

- Protected owner app access exists: the Next app has an owner unlock session and the engine has an owner API token gate.
- Press Go through the app route reaches the protected engine and creates durable owner cards.
- Text upload through the app route reaches the same engine path and cleans upload staging afterward.
- Messy transcripts produce the expected mix of outcomes: safe reminders/actions done, human-impacting sends waiting for approval, vague browser tasks asking when context is missing, money blocked with no approval path.
- Saved setup memory feeds later actions: onboarding memory can resolve a later vague cart request and produce a memory-resolution receipt.
- Owner approval works through the app route: approving and declining waiting cards update durable records and survive reload.
- Text/call readiness is visible without leaking secrets: outbound channel readiness and inbound YES/NO reply readiness are both surfaced.
- Inbound SMS reply mechanics are backend-proven with fake transport: exact YES/NO codes resolve owner cards, ambiguity is refused, restart recovery works, and money still fails closed.
- Browser visual smoke has passed for the owner UI in protected mock mode: locked owner gate, unlock, transcript input, Go, task cards, approval, decline, blocked money, done receipts, and no browser console errors.
- The live browser hand can reach Chrome through the native bridge and return read-only page proof: a live `read_page` job opened `https://example.com/` and returned URL, title, and screenshot proof.
- The live browser hand can now execute a safe cart-only browser action when memory/context supplies the product page: on Demo Web Shop it opened the known product page, clicked only `Add to cart`, navigated to the cart, and verified `Computing and Internet` was present with screenshot proof. It did not checkout, pay, log in, or place an order.
- The owner engine path can now carry that live browser proof back onto a task card: a messy transcript line supplied the product memory, a later "cart that thing" line executed through the browser hand, and the card showed a `browser_receipt` with cart URL, answer, and screenshot flag.
- The protected Next owner ingest route has now been run with live browser mode enabled: the same HTTP route behind Press Go accepted a messy transcript, resolved "that Fiction book thing" from same-transcript memory, executed the cart-only browser hand, and returned a done card with `memory_resolution` plus `browser_receipt` proof for the cart URL and screenshot.
- The actual browser-rendered UI has now been clicked through in live browser mode: owner unlock, transcript entry, Go, live cart-only browser execution, and the visible done card showed `used memory`, `browser receipt`, and `Verified cart contains Fiction` with no console errors or framework overlay.
- Live outbound owner SMS is now proven in the direct Codex lane: with Twilio live mode enabled, the same channel worker used by approval asks sent a harmless owner text and returned `status=success`, `delivered=live`, `channel=text`, `mock=False`.
- Live inbound Twilio polling is reachable and fails closed: a fresh cold-start poll fetched an existing message, skipped it as stale, and resolved/ingested nothing.
- Focused verification is green after the latest product change: Python compile, orchestrator regression, messy proactive handoff regression, browser-hand unit test, JS syntax check, owner app product-path smoke, live owner-engine browser receipt proof, and live UI receipt smoke.

## What Is Not Done Yet

- The public product has not been proven with a full live Twilio YES/NO round trip in this direct Codex lane. Outbound live SMS and inbound polling are proven, but an owner reply to a real approval code still needs to resolve a waiting card.
- Real signed-in retailer/browser actions remain unproven. The safe boundary is clear: cart-only or lookup only, no checkout, no payment, no order.
- API hands beyond the mocked owner path still need live public-product proof in the app flow. Calendar had earlier real proof; Gmail draft auth still depends on `gmail.compose`.
- The frontend visual smoke is now proven against a real browser hand, but not yet against live text/call delivery or live API connectors beyond the already-proven calendar path.
- A real multi-day owner trial has not happened. Until Omar can use the app for real days with no false actions, no money execution, and useful closed loops, the product is not finished.

## Why This Attempt Is Working Better

- The target is now product-shaped: messy life input to cards, actions, asks, receipts, and loop closure.
- The system refuses fake finishes: money has no approval path, human-impacting actions wait, and done requires durable proof.
- The tests exercise the public path, not just internals: protected app route, protected engine, memory, uploads, approvals, and card reload.
- The work is one-writer and commit-by-commit. Factory runtime logs are not mixed into product commits.
- Asking is counted as a correct product outcome when asking is the safe behavior. That prevents the old failure where the system treated "did not blindly act" as failure and overfit toward dangerous automation.

## Next Highest-Leverage Steps

1. Prove live text loop closure with Omar-confirmed owner phone: create one harmless approval ask, have Omar reply with the exact YES/NO code, show the waiting card resolves, and record the receipt. Then prove the live call path.
2. Prove a real signed-in browser action on Omar's actual Chrome profile with the same no-checkout/no-payment boundary.
3. Prove live API connector readiness from the app path: Calendar read/write remains real; Gmail draft path needs `gmail.compose` authorization before it can be counted.
4. Run a real-day trial only after the above are true.
