# 01 PRODUCT — what you are building, full size

## What it is
A device the user wears that hears their day and quietly clears the petty work of running their life, across the specific apps their life actually runs on, so the always-on weight in their head is gone.

## What it solves
The mental load: anticipating what is needed, finding options, deciding, and tracking that it got done. It is the work that sits in the back of the head all day and could never be handed off before, because a human assistant needs the task spelled out. We remove it by overhearing the user's life and knowing what they meant, and what they did not even say.

## The real product is inference
People barely say their tasks out loud. They mumble them, vent around them, half-decide, or never say them. So Anticipy does not wait for commands. It infers the real need from weak signals: what was said, where the user is, what they are doing, who they were just with, what is in their inboxes, and their patterns over time. The product is not "do what I told it." It is "know what I needed before I would have asked." That inference, from unspoken signals, is the hard core and the whole moat.

## Who it is for, and the per-person mesh
Anyone: student, parent, lawyer, doctor, founder. It works for all of them because it ships with no fixed app list. At onboarding it builds a mesh of connections shaped to one person only, the set of services that person's life runs on. Same brain, a different mesh wired per person. That is why it is not locked to one kind of person.

## The shape, end to end
- Ears: the worn device (mic plus a gate that decides if anyone is talking), the phone mic, or for testing a recording or a typed transcript of a real day. Streams audio only when speech is likely.
- Phone: turns speech to text on the device, throws the raw audio away. Only short text leaves.
- Brain (cloud): inference and decision. Reads memory, weighs signals, works out the real need, decides act / ask / stay quiet.
- Hands: does the task through each app's own back door (a real API or connector) when one exists; drives the user's own signed-in browser when there is no back door.
- Voice line: its own phone number. It can call, text, and be called back.
- Memory: who the user is, their people, their patterns, every loose end still open.
All of it runs together at all times.

## The six hard pieces (the ones that must not be faked)
1. Onboarding, on the user's real machine: reads inboxes, watches what they use, calls them with custom questions, and builds the per-person mesh. For each service: API or connector if one exists; else take over the signed-in browser to get in or grab a token; else reset and store a password. The only thing it will not do without the human is spend money.
2. Memory: four stores, profile (who and their people), open loops (the exact ledger of what is promised, never lost), history (timestamped log), derived (patterns with confidence). Local-first store plus an on-device embedder, hybrid retrieval. Never lets a stale fact act as current. When unsure, it asks rather than guesses.
3. Proactive engine (the decider): triage drops the roughly 99 percent that is noise, infer the real need, decide act / ask / ignore, hand a goal to the hands, watch it finish. Also fires on time and on open loops, so it can act later when something comes due. The cardinal mistake is acting on something the user only vented about.
4. Browser agent (the hands' fallback): runs in the user's real signed-in browser, sees the page (structure plus a screenshot with numbered boxes), clicks and types with real trusted input, verifies the page changed, remembers what it tried, hands off at a wall. This is the piece with the most endless cases and the least clean checkmark, so it is the easiest to fake. Judge it only by whether the real result appeared.
5. The studs (the glue): one frozen contract every piece speaks, a worker takes a job and returns a result with proof, a bus carries jobs, the brain plans then dispatches then verifies proof then retries then resumes. Proof is required at every seam. Nothing is "done" on a worker's word.
6. The whole system as one: a brick is never done in isolation. The unit of truth is a whole real day run end to end that comes out better, proven by what actually happened in the real apps.

## The one rule on action
Spending money is the only hard stop; ask first for that. Everything else, act. Real safety rules beyond money are added at the very end by the human. Do not invent extra safety gates.

## The build method
Two real things get built: (1) a Mac app anyone can download at the project's link and use; (2) the full body later, the iPhone app, the Mac app, the pendant firmware, and a one-click way to flash the pendant and pair it. The ordered plan is in `07_MILESTONES.md`.

## The three test inputs (in the Mac app)
- MP3: a recording of a whole day, for the human to test on real life.
- Transcript: pasted text, for you to test fast, since the voice step is simple.
- Listen: live, through whatever Bluetooth device is connected, the real thing.
