# final/browser — the ONE final browser  [STATUS: NOT DONE]

This is the honest one. The browser is where we keep band-aiding and stalling at ~26–56%. No more
band-aids — here is the actual plan (not "make the browser agent 100%"):

## The plan (screenshot-first + small-model voting)
1. **Look at the page like a person** — a screenshot with numbered boxes on clickable things
   (set-of-marks), not DOM parsing. Act by number ("click 5"), never raw pixels.
2. **Vote on each action** — 2–3 cheap vision models each propose the next click; they agree → do it;
   they split → a 4th breaks the tie; still split → **stop and ask Omar** ("okay to go ahead?").
3. **Check after every action** — a screenshot confirms it actually worked; if not, try the next-best
   guess instead of blindly re-clicking.
4. **Built on browser-use** (already installed in engine/.bu-venv) as the hands; we add the control layer.

## Done when
`final/tests/browser_eval.py` (the many-case proof, to be written) holds **60%** across repeated
runs on the standard task set — not one lucky demo. The same "uncertain → ask you" signal is both
the reliability mechanism AND the ask-first UX.

## Where the real code will assemble
`ensemble.py` (the voting decide) + `validator.py` (per-action check) on top of the existing
`engine/anticipy_engine/agent/webvoyager.py`. Needs Omar to load the extension for real-account runs.
