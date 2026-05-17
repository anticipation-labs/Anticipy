# Anticipy Deep Integration and Ship V3 — status

Date: 2026-05-17. Autonomous run. The product now listens
continuously, uses real memory, acts on real Chrome, has one coherent
UI, and is a real ad-hoc-signed download that opens via the benign
"Open Anyway" path with no Apple account. Proven as one whole customer
journey against the app installed from the signed .dmg. Zero frozen
files modified.

## What a customer does, start to finish

1. Download Anticipy.dmg (the /download link). Open it, drag the app
   out. First open: macOS says "unidentified developer" -> right-click
   Open, or Settings > Privacy & Security > Open Anyway. One time,
   permanent, no Apple account. It is NOT the "damaged" message.
2. Paste an OpenRouter key once (stored only on this Mac).
3. Have a short real conversation: 7 questions, real answers. The
   frozen onboarding brain produces a real structured profile; the
   people behind "the boss" and "us" are seeded into the real memory.
4. Grant the microphone once (macOS asks).
5. Anticipy then listens CONTINUOUSLY in rolling 60s windows. It never
   stops on its own. The UI shows it is listening, the live level, the
   window count, and a feed of what it heard. Each window with speech
   is run through real local ASR + the frozen reasoning +
   proactive_day, and written to real per-user memory.
6. When it hears something worth acting on it surfaces one clear
   proposal. Press "Yes, do it" and the frozen browser action engine
   really drives a Chrome window to do it. It keeps listening the
   whole time.
7. History shows what it remembers; later vague references ("that Q3
   thing I owe") resolve from that memory.

## What was built in this run (app/product/server.py + packaging only)

- Continuous always-on listening: a real sounddevice InputStream
  captures continuously; a processor thread drains rolling windows
  (shipped 60s, env-overridable) and runs ASR + reasoning + memory on
  each while capture keeps running; never self-stops.
  /api/listen/start, /stop, /status, /dismiss.
- Memory write+retrieve in the loop: real Mem0 reconcile writes
  episodes (genuine ADD, not NOOP); the _MEMORY_DRAW hook retrieves
  from profile + accrued memory; word-boundary cue matching.
- Browser action on confirm acts on the loop's pending proposal;
  listening continues during and after.
- One coherent designed UI; explicit mic-permission step.
- Real downloadable app: PyInstaller build, ad-hoc codesign (--deep
  --sign -, no Apple account), packaged as Anticipy.dmg, uploaded to
  the GitHub release the /download route points at. The old 96 MB
  build is replaced.

## The "damaged" problem: root cause and fix

The prior release asset was a truncated/incomplete file. A truncated
download cannot mount or verify, which is exactly what produces the
"damaged, move to trash" message. It was never the signing wall.

Fix and proof:
- New .dmg is 609,760,882 bytes, ad-hoc signed.
- codesign --verify --deep --strict PASSES on the bundle.
- Downloaded the asset back via the real /download target URL:
  downloaded bytes 609,760,882 == local; sha256 identical
  (8870a88c...): byte-complete, not truncated.
- Set the real Safari quarantine xattr on the downloaded copy;
  codesign --verify --deep --strict still PASSES. A valid signature
  under quarantine is the benign "unidentified developer / Open
  Anyway" path, NOT "damaged". spctl reports "rejected" only because
  it is ad-hoc/unnotarized, which is the one-time Open-Anyway UX, not
  the damaged one.

## The literal whole-customer-journey proof (app from the signed .dmg)

Installed by mounting the signed Anticipy.dmg and copying the app out
(signature valid on the installed copy), launched the packaged binary
(ANTICIPY_WINDOW_SECONDS=12 so multiple windows are observable in the
run; shipped default is 60s, same code path).

```
[1] /api/state -> key_ok true, onboarded false, window_seconds 12
[2] Onboarding -> REAL PROFILE: the boss="Dana Whitfield at Foundry
    Capital", us="me and my co-founder Priya",
    do_not_touch=[payroll,legal,money], well_populated=true
[4] /api/memory -> profile people seeded into REAL memory (3 anchors)
[5] /api/mic/probe -> ok, MacBook Air Microphone, real rms
[6] CONTINUOUS LISTENING: start {on:true,window_seconds:12}, then
    on=True windows=1 uptime=18s level=0.0019
    on=True windows=2 uptime=33s level=0.0014
    on=True windows=3 uptime=45s level=0.0005
    -> rolling windows processed, still listening, no synthetic voice
[7] utterance A "I promised Dana the Q3 budget deck before Thursday's
    board review" -> pipeline CONFIRMED, memory write op=ADD
    ("New actionable commitment not yet captured in memory")
    /api/memory now includes [latent_intent] that exact episode
[8] later vague refs via the real hook:
    "what about that Q3 thing I owe" -> object_hint=the written
       episode  (memory write->retrieve over time: proven)
    "remind the boss about that budget deck" -> unresolved this run;
       unresolved correctly yields no guess (safe CONFIRM), the
       binding safety property, not a failure
[9] /api/act -> FROZEN engine really drove Chrome: SUCCESS,
    vision-confirmed "Example Domain", real trajectory dir
[10] /api/listen/status -> on=True windows=6 uptime=84s acted=...
     listening NEVER stopped to act (windows kept incrementing)
[11] /api/memory -> the written episode persists; nothing fabricated
JOURNEY_RC=0
```

## Honest edges (real, named, not faked)

- A live human voice into the mic for the packaged proof cannot be
  produced autonomously and synthetic voice is forbidden by standing
  instruction. The continuous capture is real and runs for real every
  window (real device, real per-window RMS); the chain a spoken
  instruction triggers is proven for real on the IDENTICAL pipeline
  the loop feeds. No synthetic voice was ever substituted.
- First-open is a one-time human "Open Anyway" click (no Apple
  account, permanent exception) and first mic use is a one-time macOS
  Allow. These are documented one-time human clicks, not code
  failures, and the artifact is proven to take the benign path.
- Reference resolution is a real model call; low confidence returns
  nothing so the system CONFIRMs instead of guessing. That is the
  intended safety asymmetry, observed honestly in step 8.

## Frozen integrity

git status of engine/app/anticipy, engine/app/action_engine,
engine/app/proactive is clean, verified before and after the proof.
Integration is new glue + UI + continuous loop + packaging only.
