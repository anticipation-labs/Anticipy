# final/ — THE product. This is where we build.

If you ever wonder **"where is the real system,"** it is HERE. One home per system. Nothing else
in the repo is "the system" — everything else is support (engine server, app screens, extension
hands) or archive.

```
final/
  proactive/   ← the ONE final proactive  (catch real tasks, stay silent on vents, decide act/ask/confirm)   [nearly done]
  browser/     ← the ONE final browser    (screenshot-first + small-model voting → 60%)                       [NOT done]
  context/     ← the ONE final context    (memory that learns you + retrieves the right facts)                [partial]
  run.py       ← the ONE line that wires them:  hear → proactive → context → browser → warm check-in → learn
  tests/       ← each system proven on MANY cases (varied fake users), NOT one
```

## The rule that ends the pain
A system is **"done" only when it passes its MANY-case test in `final/tests/`.**
"Works on my one example" is NOT done — that's the disease (and how hardcoding hides). The
many-case test is the cure: varied people, varied phrasings, so it can't fake it.

## How the rest of the codebase works (so you're never lost)
- `engine/` = the brain (a Python server that thinks).
- `app/` = the screens (what you see).
- `extension/` = the hands (acts in your real Chrome).
- `final/` = the clean home where the brain's three core systems are assembled and proven.
