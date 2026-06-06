# 08 HUMAN GATES — the only times you stop for the human

You are in full send. You do the work. The human is pulled in only for things that are genuinely impossible for you to do yourself. Everything else, you handle.

## The only gates
1. A sign-in or OAuth you cannot complete even with computer use (for example a two-factor code that goes to the human's phone, or a login whose password you do not have and cannot reset).
2. Spending real money or entering payment details. This is the one hard stop in the whole product.
3. A missing, unfunded, or failing API key that you cannot provision yourself (OpenRouter funding, Arcade, Twilio).
4. Flashing the physical pendant, or anything that needs the human's hands on hardware.
5. A hard external block you cannot pass (for example a captcha that requires a human).

That is the whole list. If a task is not one of these, it is not a gate. Do it yourself.

## How to handle a gate without stalling the whole run
1. Append a specific, actionable item to `PENDING_FOR_OMAR.md`: exactly what you need, the exact URL or step, and why it is blocked. Be concrete enough that the human can clear it in one action.
2. Keep working on everything that is not blocked by it. A single blocked connector does not stop progress on the front door, the input box, the browser hands, logging, or any other milestone.
3. Only if every remaining path is blocked: send the human a short text on the Twilio line summarizing what is waiting, then pause the loop and wait. Do not sit idle while unblocked work exists.

## What is NOT a gate (do these yourself, never ask the human)
- Running terminal commands, builds, tests, or scripts.
- Editing config (after researching the official syntax).
- Installing dependencies.
- Loading or reloading the Chrome extension (including the desktop-copy rsync and reload).
- Navigating, clicking, typing, or filling forms on the web via computer use.
- Reading the repo, the brief, the logs, or the real days.
Routing any of these to the human is a Law 8 violation. The human's time is for decisions and the five gates only.

## When the milestones are done
When all milestones in `07_MILESTONES.md` are met and the judge has confirmed them on fresh days, write a clear summary to `PENDING_FOR_OMAR.md` and `logs/journal.md` (what is built, the latest scorecard, what you verified with your own eyes), send the human a text, and stop. That is the only "pull me back when everything is done."
