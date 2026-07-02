# DONE — the only definition (Omar's guiding star, 2026-06-19)

> This is THE definition of done. Every other "what done means" in this repo defers to this.
> Set the loop up so it does not stop until ALL of this is true and provable.

## Base codebase — DECIDED 2026-06-19 (one repo, never fork the engine again)
Build on **`~/Anticipy`**. It is the only version whose inference brain (memory + proactive
act/ask/silent + browser action + local-Whisper listen) actually works and is proven (suite green,
safety floor 0, freshest, least rot). The other versions were scored on reality and rejected as
bases: `Anticipy-DEV-FINAL` (good website/extension/ASR but a graveyard of 6 action / 5 proactive
engines, broken memory-scrape, dead code + live landmines), `Anticipy-V7` (most product-shaped but
older, build broken, public path never worked, never run on a real machine), `Anticipy Core` (a minor
bridge artifact). Root cause of the months-long yo-yo: we kept REBUILDING the working brain from
scratch in DEV-FINAL/V7 (re-climbing the hard 60%) while the website lived in yet another repo — so
the brain and the front door were never in one place. Fix: one repo (`~/Anticipy`); borrow only the
website/onboarding VISUAL DESIGN from the others as reference, never their engine code.

## Architecture (non-negotiable, Omar's call 2026-06-19)
- **BROWSER-ONLY for every action.** Email is sent from the browser (Gmail in the user's own
  Chrome). Scraping is done from the browser. Web tasks are done from the browser. Anything the
  product DOES for the user happens through the user's real Chrome. **Drop the Arcade API.**
- **Twilio is the ONE exception: it uses its API key** (TWILIO_* in .env.local). Never log in to
  Twilio. SMS + voice go out via the Twilio REST API. It is infrastructure, not a user action.
- No money ever (the one hard stop, by design). Never act on a vent (the cardinal sin). These two
  floors stay hard-coded; NOTHING else about the product's decisions is hard-coded — decisions are
  the brain's inference, not keyword rules.

## Done = ALL of these are true and provable LIVE (no mock, receipt you can click)
1. Listens — mic + transcript + MP3 — and infers the messy day → act / ask / silent, by judgment.
2. Figures out who the user is by reading their world through the browser (real onboarding scrape).
3. Acts for real, all via the browser: sends an email, does a web task, etc. — proven end to end.
4. Reaches out on its own: a time-due reminder really lands on the phone (Twilio API), and an
   inbound reply is answered by the brain (round-trip).
5. Runs as something anybody can set up and use (their Chrome, their number) — not just this Mac.
6. I can vouch for it with certainty: every capability has a live, independently-read-back proof.

## The bar, in Omar's words (2026-06-19)
"I want it all built for anybody and everybody to use — not 'the brain works' or 'the hands work.'
Everything works. Browser-only; Twilio uses its API key. I don't care about goals or loops — I care
that it's fully done and you can vouch with certainty that it's ready for anybody. If I test it, I
won't bite your head off. Once that's true, you're done. Set yourself up so you don't stop until then."

## Only-Omar items (cannot be faked or done without him; everything else is mine to finish)
- Apple Developer ID — only needed for a one-click SIGNED download; without it the app opens via
  right-click and everything else still works.
- Living with it for real (the final validation only he can do).
