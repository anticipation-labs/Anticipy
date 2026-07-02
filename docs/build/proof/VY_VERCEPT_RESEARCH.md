# Vy by Vercept — Research & How We Beat It

_Researched live from vercept.com and its Wayback Machine history, 2026-06-28._

## The headline you need to know first

**Vercept (the company behind Vy) is being acqui-hired by Anthropic.**
- Announcement on vercept.com, dated **February 25th, 2026**: "Vercept is joining Anthropic."
- **Vy shuts down 30 days later — March 25th, 2026.** (Direct quote from the site FAQ: "Vy will shut down in 30 days, on March 25th, 2026.")
- Paid subscriptions are being wound down; users pointed to support@vercept.com.

So "beating Vy" as a shipping product is partly moot — **the product is dead in <30 days.** What you are actually now up against is **Anthropic's computer-use line (Claude in Chrome / Computer Use), reinforced by the Vercept team and their tech.** That reframes the fight: the competitor isn't a scrappy startup app anymore, it's a frontier lab that just bought world-class talent in exactly this domain.

## Who Vercept is (why this matters)

The three founders are not lightweight:
- **Ross Girshick** — one of the most-cited computer-vision researchers alive: R-CNN / Fast R-CNN / Faster R-CNN, Mask R-CNN, RetinaNet/Focal Loss, Detectron. Ex-FAIR/Microsoft Research.
- **Kiana Ehsani** and **Luca Weihs** — embodied-AI researchers from the Allen Institute for AI (AI2-THOR, ProcTHOR, robotic manipulation).

Backed by Fifty Years, Point Nine, AI2 Incubator, Madrona. This is a vision-research-heavy team — which is exactly why Vy was **screenshot/vision-first**, and exactly why Anthropic wanted them for Computer Use.

## What Vy actually was (from the live 2025 product page)

- A **native macOS desktop app** (required macOS 14.0+), downloaded as a binary — not a browser extension and not cloud.
- A **whole-computer agent**, not browser-only: "Vy works across different software on your computer… Seamlessly integrates with any application."
- **Vision-first / screen-understanding**: it looked at your actual screen and acted on it ("AI that could see what you see and act on your behalf").
- Feature set (verbatim task demos from the site):
  - "Find a GitHub issue to work on and try to fix it"
  - "Find me pet-friendly 1-bedroom apartment listings in Seattle"
  - "Merge these two shapes in Figma" (native desktop app control)
  - "Upload all the receipts in my Downloads folder to my banking app" (filesystem + web)
  - "Fill out a website form using details Vy knows about me" (memory + form-fill)
  - Type **"@" to reference browser tabs, PDFs, etc.**
  - **Scheduled / autonomous workflows**: "Create, edit, and run custom workflows on a schedule… automate repetitive tasks when you're not using your computer."
  - **Per-user memory**: "Vy remembers information about you… only when you ask it to."

## Honest head-to-head: Vy vs. Anticipy

| Dimension | Vy (Vercept) | Anticipy (us) |
|---|---|---|
| Scope | **Whole OS** — any native app (Figma, banking app), filesystem, browser | **Browser only** (today) |
| Perception | **Vision-first** (screenshots of the live screen) | **DOM/accessibility-first**, screenshot only as fallback |
| Where it runs | Native macOS app, drives the visible desktop | **User's own authenticated Chrome, background tab, via CDP trusted input** |
| Cost model | Vision-every-step → frontier-priced tokens on every step | Cheap-model routine + frontier-on-hard routing + **recipe replay ≈ $0 on repeats** |
| Autonomy | **Scheduled workflows** when you're away | On-demand (no scheduler yet) |
| Memory | Per-user memory, form-fill | Per-user memory + self-healing recipe library |
| Verification | (not published) | **Read-back judge, "never fake done"** |
| Status | **Shutting down 2026-03-25; absorbed into Anthropic** | Alive, in active development |

### Where Vy genuinely beat us
1. **Whole-computer scope.** It could drive Figma, the Finder/Downloads folder, and native apps — we're browser-only. This is the biggest capability gap.
2. **Vision grounding for arbitrary GUIs.** A Girshick-led team's pixel grounding is going to be excellent on apps that have no DOM (canvas tools, native UIs). DOM-first can't see those at all.
3. **Scheduled autonomous workflows.** "Run while you're not at the computer" is a product feature we don't have.
4. **Research + compute firepower** — and now Anthropic's models behind it.

### Where we beat them (and beat Anthropic's version too)
1. **Cost.** Vision-on-every-step at frontier prices is the single most expensive way to run an agent. Our DOM-first + routing + recipe-replay is structurally cheaper — and the gap *grows* on repeat tasks (their cost stays flat at frontier vision pricing; ours bends toward $0).
2. **Real authenticated browser depth.** We drive the user's *own logged-in Chrome*. A fresh remote/visioned desktop still has to log in; on the web specifically, DOM-first is faster and more reliable than reading pixels.
3. **Never-fake-done verification.** We grade by reading the resulting page back, not by trusting a screenshot the model might misread.
4. **It's being shut down.** There is a **30-day window** and an **orphaned user base + Discord community** of people who specifically wanted a local, cross-app, scheduled agent. That is a concrete go-to-market opening.

## The strategic read

"We must beat them" now means two different things:
1. **Beat the dead product (easy / time-boxed):** match the Vy capabilities its users will lose on March 25 — cross-app reach, scheduled workflows, vision grounding for non-DOM apps — and court the orphaned community. This is a real, dated opportunity.
2. **Beat what they became (the hard, real fight):** Anthropic's computer-use, now with the Vercept vision team. You don't beat a frontier lab on raw model quality. You beat them on the layer they don't optimize for: **$/task economics, the user's authenticated real environment, compounding per-user data + recipe replay, and honest verification.** Same conclusion as the broader research — the model is a commodity; the moat is the system around it.

## Concrete next moves to actually beat them

1. **Close the scope gap toward whole-computer.** Vy's killer differentiator was "any app, not just browser." Add an OS/vision actor (the SOTA approach for non-DOM apps) that *complements* our DOM-first browser path — DOM-first where a DOM exists (cheap, reliable), vision grounding only for canvas/native UIs. Keeps our cost edge while erasing their scope edge.
2. **Ship scheduled/autonomous workflows.** Record a verified recipe once, then run it on a schedule at ≈$0 (we already have recipe-replay — the scheduler is the missing piece). This directly matches Vy's "automate when you're away" and our replay makes it far cheaper than they could.
3. **Win on a public number with cost attached.** Run WebArena + Online-Mind2Web, publish success% *and* $/task together. Anthropic publishes accuracy; nobody publishes "success-per-dollar." Define and own that metric.
4. **Court the orphaned Vy users now.** 30-day shutdown window + an existing Discord community that wanted exactly this. A migration path ("keep your local cross-app agent, cheaper, in your real Chrome") is a concrete wedge.
