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
- Current deterministic suite was green after the latest product change: 53 passed, 0 failed.

## What Is Not Done Yet

- The public product has not been proven with a real live Twilio call/SMS round trip in this direct Codex lane. The app can now tell when the system is ready to enable it, but live sending remains explicitly gated.
- The owner app path has not yet proven a real browser hand on a real signed-in Chrome session for a safe cart task with page read-back. The bridge can read pages live, but a cart/store action is still not public-ready proof.
- API hands beyond the mocked owner path still need live public-product proof in the app flow. Calendar had earlier real proof; Gmail draft auth still depends on `gmail.compose`.
- The frontend visual smoke is proven in protected mock mode, but not yet against live connectors, a real browser hand, or live text/call delivery.
- A real multi-day owner trial has not happened. Until Omar can use the app for real days with no false actions, no money execution, and useful closed loops, the product is not finished.

## Why This Attempt Is Working Better

- The target is now product-shaped: messy life input to cards, actions, asks, receipts, and loop closure.
- The system refuses fake finishes: money has no approval path, human-impacting actions wait, and done requires durable proof.
- The tests exercise the public path, not just internals: protected app route, protected engine, memory, uploads, approvals, and card reload.
- The work is one-writer and commit-by-commit. Factory runtime logs are not mixed into product commits.
- Asking is counted as a correct product outcome when asking is the safe behavior. That prevents the old failure where the system treated "did not blindly act" as failure and overfit toward dangerous automation.

## Next Highest-Leverage Steps

1. Prove live text/call loop closure with Omar-confirmed owner phone: app asks, SMS/code round trip resolves, call/text receipt appears, no third-party impact.
2. Prove one real browser action from the owner app path with Chrome helper connected: safe cart or lookup only, no checkout, page read-back receipt.
3. Prove live API connector readiness from the app path: Calendar read/write remains real; Gmail draft path needs `gmail.compose` authorization before it can be counted.
4. Run a real-day trial only after the above are true.
