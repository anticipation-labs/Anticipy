> ⚠️ **SUPERSEDED — 2026-07-02.** Historical document. The living truth is **`CANON/00_START_HERE.md`**
> (+ `MISSION_LOCK.md` for live mission status). Do not follow this file's read-order, done-definition,
> or status claims. Indexed with context in `CANON/99_SUPERSEDED_INDEX.md`.

# 00 AMENDMENT: NEVER STALL, NEVER FAKE, ALWAYS MOVE THE REAL TASK FORWARD

Read this first, before AGENTS.md and before anything in autopilot/. This file supersedes any rule in the other control-plane files that conflicts with it. If you ever think "I am blocked, I will stop," you are wrong unless the blocker is one of the five named human gates in section 6. Re-read this file at the start of every lap.

This exists because of one structural flaw that kept stalling the loop: the only thing that counted as progress (a judge-confirmed real action) needed paid credits, so when credits ran low the loop had nothing it was allowed to do and it either parked ("honestly blocked") or drifted to easy fake work (status displays, toggles, example.com, search-bar tricks). Both are failures. This file removes that flaw by giving you a permanent ladder of real, hard work that does NOT need the judge and does NOT need heavy paid model calls. You climb that ladder continuously. You never sit idle, and you never fake.

## 1. The One Disease, Named

Every past failure was the same move wearing different clothes: when the real goal got hard to measure, you swapped it for something easy to measure and optimized the easy thing. Fake green tests. Calling a demo the goal. A single hardcoded task. example.com. Typing the whole task into a search bar. Polishing buttons and status lights. These are all the same disease: proxy substitution.

The real goal does not bend to this. The real goal is: hear a messy, vague, real day, infer the unspoken need, and actually do the petty life-admin task on the real site or app, correctly, and prove it really happened. The inference from weak signal is the actual product. The doing is the easy half. The buttons around it are not the product at all.

If you catch yourself reaching for work that is easy to mark green, stop. That itch is the disease. The cure is in section 3: there is always real, hard, judge-free work available, so you never need the easy fake.

## 2. What M3 Actually Is

M3 is not "the browser opened a page." It is the whole chain, from vague speech to a real change on a real site, proven by a separate judge. The full shape:

1. The task is given in vague, natural language that does NOT name the site or the exact item. Example: "grab that thing I was looking at earlier for the kitchen." Not "add the stainless water bottle on target.com to my cart." If the instruction names the site and the item, it is a wiring test, not the product.
2. The system uses MEMORY to resolve what "that thing" and "earlier" mean, to pick the right real site, and to find the right real item.
3. The browser hand completes it on that real site. The item is really in the real cart. The form is really submitted. Something real changed.
4. It is proven ONLY when the separate judge opens the real site or account and sees the real change. No mocks. No self-grading. No screenshots of example.com.

Hard bans, written into 02_LAWS.md and 07_MILESTONES.md the first lap you read this:

- example.com, localhost, and any contrived no-stakes page are BANNED as task targets. They prove the system is on. They are not tasks. Using them as M3 evidence is a violation.
- The browser hand is NEVER driven by typing the instruction into a search bar or address bar. If a task collapses into "type the whole task into search," that is a FAIL, not a result.
- A mocked browser check NEVER counts as M3 progress. Mocks prove wiring only. M3 advances only when the separate judge sees a real artifact in the real world.
- "12 of the same action shape with different words" is one capability proven across phrasing. It is not "12/13 of the way done." Breadth of phrasing is not breadth of product.

## 3. The Ladder

Being blocked on PROOF does not block BUILDING. Being low on paid model credit does not block BUILDING. The judge confirms M3; it is not needed to build M3. Heavy live planning is one way to drive the browser; it is not the only way. So when proof or credit is unavailable, you do NOT stop and you do NOT drift to buttons. You climb this ladder. Every rung is real work on the real task, and none of it needs the judge or heavy spend. Label every output on this ladder UNPROVEN-PENDING-JUDGE.

Rung A. Memory-to-intent resolution, the actual brain and the hardest and most valuable rung.
Build the piece that turns vague speech into a concrete item and a concrete real site, using memory. "That thing I looked at earlier for the kitchen" becomes a specific product and a specific store. Test it on real recorded or vague inputs you already have. This is pure logic and retrieval. It needs no judge, no live browser, almost no spend. This is the part nobody has cracked, so this is where most of your time should go, not the perimeter.

Rung B. Real-site DOM action recipes, captured against the real page.
For a real store, build and harden the concrete steps: find the item, open the product page, add to cart. Run it against the real site's actual DOM. Capture the real page state after each step, the real HTML/structure and what actually changed, as evidence, even though it cannot be judge-certified yet. This is real action work on a real site. It does not need the judge to be built and captured.

Rung C. Make the live browser planner cheap enough to run on low credit.
Cache page observations so you do not re-pay to re-read the same page. Cut redundant model calls. Use the smallest model that can still choose the next correct click. The goal is that a real cart attempt can run end to end without heavy spend. This is engineering that directly unblocks the expensive part, and it needs no judge.

Rung D. When one real site fights you, do not stop.
Move sideways to another real site, or build the offline pieces, intent resolution, item matching, DOM recipes, that move the real task forward on any site. A hard site is a reason to switch rungs, never a reason to park.

Rung E. Harden failure modes you already found, on the real chain.
Make the chain fail honestly and fast instead of looping or pretending. Real robustness work on the real path. No judge needed.

Rule: while the judge is unavailable or credit is low, you must be on rung A, B, C, D, or E every single lap. You may not be on buttons, status displays, observability polish, onboarding cosmetics, or contrived pages. If you genuinely cannot make progress on building the real chain, not proving it, building it, then and only then write the specific blocker in PENDING_FOR_OMAR.md, and the blocker must name exactly what is stopping the BUILD, not the proof.

## 4. Anti-Stall Rule

"Honestly blocked" is NOT an acceptable resting state. Delete any BLOCKS_ALL marker from PENDING_FOR_OMAR.md unless the blocker is one of the five human gates in section 6.

- Blocked on the JUDGE quota: keep building the real chain on the ladder. Mark it UNPROVEN-PENDING-JUDGE. Do not stop.
- Low on MODEL CREDIT: go to rung C and make planning cheap, then keep building on the rest of the ladder. Low credit is a thing to engineer around, not a wall.
- A hard SITE: switch rungs. Do not stop.

You stop the loop and wait for the human only when every remaining rung is blocked by a real human gate at the same time. That is extremely rare. Until then, never park, never fake, always be moving the real task forward.

## 5. Judge Honesty

Section 3 lets you build without the judge. It does NOT let you claim M3 is done without the judge. Keep all of this:

- The builder and the judge are SEPARATE sessions. The builder never grades its own work.
- The judge proves itself every lap with a planted fake before you trust any verdict. If the judge misses the planted fake, halt and log it; do not trust a judge that cannot catch a known fake.
- The judge's verdict is cross-checked by a different model family, not the same model that built the work, on the calls that matter. A model agreeing with itself is not proof.
- The judge for ACTIONS opens the real app and looks. The judge for JUDGMENT/taste is graded against the human's own marks on real days, never against an answer key the builder wrote. If the only "human" in the answer key is an AI, the number is provisional and you say so.
- Abstaining is not progress. "I declined to act" is never logged as a win toward a milestone.

When credit returns, the first thing you do is take everything you built UNPROVEN-PENDING-JUDGE up the ladder and run it through the real judge. That is how the ladder converts into real M3 progress.

## 6. The Only Five Human Gates

You are in full send. You do the work yourself. You pull the human in only for these:

1. A sign-in or OAuth you cannot complete even with computer use, such as a 2FA code to the human's phone, or a login whose password you do not have and cannot reset.
2. Spending real money or entering payment details. This is the one hard product stop.
3. A missing, unfunded, or failing API key you cannot provision yourself, including OpenRouter funding, Arcade, or Twilio.
4. Flashing the physical pendant, or anything needing the human's hands on hardware.
5. A hard external block you cannot pass, such as a captcha that needs a human.

Low model credit is NOT a gate; reduce planning cost and keep building. A blocked judge is NOT a gate; keep building the chain. A hard site is NOT a gate; switch rungs. For a real gate: write a specific, one-action item in PENDING_FOR_OMAR.md, exactly what you need, the exact URL or step, why it is blocked, keep working everything not blocked by it, and only pause if everything is gated at once.

## 7. Every Lap, In Order

1. Re-read this file and the on-disk state. Do not trust memory across laps; state lives in files and git.
2. If the judge and credit are available: work the real M3 chain and prove the next piece with the separate judge. Convert any UNPROVEN-PENDING-JUDGE work first.
3. If the judge or credit is unavailable: climb the ladder, section 3, rung A first. Build the real chain. Capture real evidence. Label it UNPROVEN-PENDING-JUDGE. Never park, never fake, never touch buttons.
4. Log the lap honestly: what you built, what is proven vs unproven, what real evidence you captured, drift numbers. No silent work.
5. If and only if every rung is blocked by a real human gate: write the exact blocker in PENDING_FOR_OMAR.md and pause. Otherwise, next lap.

The finish line is the real one: vague speech, resolved by memory, done on a real site, confirmed by a separate judge, holding up across many different real days. Not a button. Not a green test. Not a demo. Keep climbing the ladder toward that, every lap, forever, until the milestones in 07_MILESTONES.md are met and judge-confirmed on fresh days, or a real human gate stops you.
