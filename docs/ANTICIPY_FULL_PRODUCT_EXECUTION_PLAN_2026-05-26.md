# Anticipy Full Product Execution Plan - 2026-05-26

This document is the working plan for turning the current Anticipy pieces into the public product Omar actually wants.

It is not a completion claim. It is the plan a junior engineer, senior engineer, or agent swarm can execute without relying on memory from a chat.

## 0. Omar's Goal, Restated

Omar does not want a Gmail bot, a proof harness, a demo, or a local-only Mac toy.

Omar wants:

1. A public user goes to `https://www.anticipy.ai/app`.
2. The user signs in and downloads Anticipy.
3. Anticipy installs a user-device engine on that user's Mac.
4. The user can feed Anticipy context through MP3 upload, transcript paste/upload, computer microphone, external microphone, and later pendant audio.
5. Anticipy listens to natural context, understands what a competent person would do, and either acts, asks, declines, or stays silent.
6. It uses the user's real surfaces: Chrome, web apps, native Mac apps, files, screen, audio devices, and signed-in accounts.
7. It remembers the user's people, rules, preferences, tools, repeated patterns, do-not-touch list, prior corrections, and learned surface recipes.
8. It becomes a second version of the user, not a menu of five hard-coded skills.

Short version:

```text
Public app -> downloaded Mac engine -> real input -> memory + intent -> proactive decision -> action engine -> real browser/native surface -> visible receipt.
```

## 1. Like You Are Five

Anticipy is a car.

The **car body** is the public website and Mac app shell.

The **engine** is the user-device engine running on each user's Mac.

The **eyes** are the browser extension, screen reads, DOM reads, native accessibility reads, and audio transcripts.

The **brain** is memory plus intent detection plus proactive reasoning.

The **hands** are the action engine and browser/native surface runtime.

The current problem is not that no parts exist. The problem is that there are multiple half-connected engines, multiple steering wheels, multiple memory boxes, and multiple browser paths. Some pieces work in isolation, but they are not one dependable car.

The fix is to choose one product spine and move every important part onto it.

## 2. Non-Negotiable Product Spine

Every real feature must run through this path:

```text
https://www.anticipy.ai/app
  -> public account/session
  -> public downloadable app/DMG
  -> installed user-device engine on 127.0.0.1:8731
  -> normalized input boundary
  -> memory/profile/context load
  -> intent/want decision
  -> proactive policy
  -> action dispatcher
  -> surface runtime
  -> real Chrome extension/native bridge or native-app adapter
  -> visible receipt
```

Anything outside that spine is either:

- legacy,
- test-only,
- verifier-only,
- or a temporary adapter that must be clearly labelled.

## 3. Current State In Plain English

### What Exists

The public app exists.

The public downloadable engine exists.

The installed engine can run on `127.0.0.1:8731`.

The app can talk to the installed engine.

There is code for:

- MP3/audio upload,
- transcript paste/upload,
- computer microphone,
- local ASR,
- onboarding/profile extraction,
- local memory,
- hosted Supabase memory,
- proactive reasoning,
- intent extraction,
- browser action execution,
- Chrome extension/native messaging,
- surface receipts,
- generated-stranger evaluation.

### What Is Not Done

The pieces are not unified.

Current blockers:

1. Public DMG hash currently does not match the manifest.
2. Chrome extension path is ambiguous: there is a current native bridge extension and older legacy extensions.
3. The public installer installs the native host/app but does not fully guarantee Chrome extension installation/connection.
4. Memory is split between local JSONL, local profile JSON, hosted memory tables, hosted preferences, hosted episode recall, and hosted dossiers.
5. Local memory is not properly account/device scoped yet.
6. Proactive, intent, and action execution have multiple competing loops.
7. Browser action can be marked successful before a real visible receipt.
8. Action coverage is too narrow and not yet a general browser/native surface agent.
9. External microphone is not proven.
10. Clean-room installs are Omar-owned and off the engineering critical path for now.
11. Only 3 successful generated stranger interactions are counted.
12. Memory system was under-mentioned before. That was wrong. It is central.

## 4. Chrome Extension Decision

The Chrome extension stays.

Reason: if Anticipy is going to act inside the user's real Chrome without cloning profiles or forcing hidden CDP browsers, it needs an authorized user-visible browser bridge. The cleanest current path is:

```text
local engine -> SurfaceRuntime -> native host -> extension_v4 -> real Chrome tab
```

Canonical extension:

```text
extension_v4/
```

Packaged public zips:

```text
public/anticipy-extension.zip
public/anticipy-extension-v6.zip
```

Legacy extension paths:

```text
extension/
extension_v2/
extension_v3/
```

Decision:

- `extension_v4` is the public Chrome bridge.
- `extension/`, `extension_v2/`, and `extension_v3/` are legacy until proven otherwise.
- Legacy build scripts must not overwrite `public/anticipy-extension.zip`.

Research fact:

- Chrome native messaging requires a Chrome extension with `nativeMessaging` permission and a native host manifest registered on the user's machine. Official docs: [Chrome native messaging](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging).
- Public Chrome extension distribution should go through the Chrome Web Store or a clear enterprise/dev install path. Official docs: [Publish in the Chrome Web Store](https://developer.chrome.com/docs/webstore/publish/).
- Chrome inline installation is discontinued; websites can redirect users to the Web Store listing instead of silently installing extensions. Official docs: [Inline installation FAQ](https://developer.chrome.com/docs/extensions/mv2/inline-faq).

Practical implication:

The Mac app can install the native host. Chrome still needs the extension installed and authorized by the user or via an accepted distribution path. The product UI must detect and explain that clearly.

## 5. Browser Agent Strategy

Do not build a giant skills library.

The browser agent should be a universal surface runtime:

1. Read the page/surface.
2. Decide the next primitive.
3. Execute one primitive.
4. Verify visible result.
5. Learn a tiny user-local recipe only after success.

Primitive actions:

- open
- read
- click
- type
- keyboard shortcut
- wait
- verify
- ask
- decline
- notify

This is how Anticipy handles unknown apps. It does not need a prebuilt skill for every CRM on earth. It needs a strong read-act-verify loop.

Skill/recipe rule:

- No giant global skill library.
- Use general primitives by default.
- Save small user-local recipes only after a successful visible receipt.
- Retrieve only a few relevant recipes for the current user/surface/task.

## 6. Memory System Strategy

Memory is not optional. It is the product's identity layer.

Anticipy must remember:

- who the user is,
- important people,
- pronouns and aliases,
- do-not-touch rules,
- preferred tools,
- repeated workflows,
- prior accepted actions,
- prior rejected actions,
- local surface recipes,
- user-specific facts,
- recent context,
- long-term patterns.

### Current Memory Places

Local user-device memory:

```text
engine/app/product/server.py
engine/app/anticipy/memory.py
product_profile.json
memory.jsonl
```

Hosted memory:

```text
public.anticipy_memory
public.anticipy_preferences
public.anticipy_user_profile
public.anticipy_intents.embedding
public.dossiers
```

Current issue:

There are too many memory boxes. They are not clearly one account/device-scoped source of truth.

### Required Memory Architecture

Use two layers:

1. Local operational memory on the user's device.
   - Fast.
   - Private.
   - Used by inference and action execution.
   - Scoped by account ID and device ID.

2. Cloud sync memory.
   - Account portability.
   - Backup.
   - Cross-device continuity.
   - Not the only source for live action.

Required rule:

```text
Every memory item has account_id, device_id, source, timestamp, confidence, kind, active flag, and provenance.
```

Never again use a static local ID like:

```text
USER_ID = "anticipy-user"
```

for real product state.

### Memory Fix Tasks

1. Replace static local user ID with provisioned account/device identity.
2. Scope `product_profile.json` and `memory.jsonl` by account/device.
3. Make onboarding dossier active in runtime inference, not just written to cloud.
4. Sync local memory writes to hosted memory with source labels.
5. Sync hosted dossier/profile into local memory on provision.
6. Add pronoun aliases into memory and action planning context.
7. Move fire-and-forget hosted memory writes to awaited writes or durable outbox.
8. Make Twilio/SMS/voice confirmation paths feed the same preference and episode learning loop when keys are later configured.
9. Add tests for account switch isolation and profile-to-intent visibility.

## 7. Intent Detection Strategy

Intent detection is the bridge between input and action.

It answers:

```text
Is there something here a competent assistant should do?
If yes, what?
For whom?
On what surface?
With what risk?
Should Anticipy act, ask, decline, or stay silent?
```

Current issue:

There are multiple intent systems:

- local proactive engine,
- hosted `/api/engine/analyze`,
- middle-layer v2 contracts,
- older streaming proactive route,
- generated eval paths.

This causes split behavior.

Required strategy:

One normalized input boundary feeds one canonical inference result.

Every input mode must produce:

```json
{
  "schema": "anticipy.normalized_input.v7",
  "source_mode": "audio_upload | transcript_upload | computer_microphone | external_microphone",
  "transcript_text": "...",
  "surface_context_refs": [],
  "account_id": "...",
  "device_id": "...",
  "public_build": {}
}
```

Then the inference layer outputs:

```json
{
  "actionable_probability": 0.0,
  "want": {},
  "interpretation": {},
  "action_binding": {},
  "risk": {},
  "decision": {
    "mode": "silent_execute | execute_notify | ask_first | decline"
  }
}
```

Rules can exist for safety and validation. Rules cannot be the final brain.

## 8. Proactive Engine Strategy

The proactive engine is not just "respond to a prompt."

It must notice:

- a user says they should do something,
- a user is clearly stuck,
- a calendar conflict appears,
- an unanswered message needs a draft,
- a task was mentioned earlier and becomes relevant later,
- the user is on a surface where a competent assistant would help.

Current issue:

There are multiple proactive engines/pipelines:

```text
engine/app/proactive/engine.py
engine/app/anticipy/proactive_engine.py
engine/app/proactive/pipeline.py
engine/app/proactive_day/pipeline.py
```

Some are older, some are simulation/eval, some are product-adjacent. They are not one clean product spine.

Required strategy:

1. Choose one canonical proactive runtime for product.
2. Use the other proactive modules only as adapters, legacy references, or offline evaluators.
3. Feed proactive runtime from the same normalized input boundary.
4. Feed it current memory and current surface context.
5. Require it to output one decision: act, ask, decline, or silent.
6. Send act decisions to the same action dispatcher as explicit commands.
7. Store silent and declined decisions too, so the product can learn without interrupting.

Proactive test method:

- Use MP3 and transcript windows.
- Include clear wants, ambiguous wants, jokes, hypotheticals, third-party wants, and real ambient opportunities.
- Verify not just whether it acted, but whether a competent person would have acted.

## 9. Action Engine Strategy

The action engine is the hands.

It must not be "works on five websites." It must be a general surface agent:

```text
read -> plan -> primitive action -> verify -> continue or ask/decline
```

Current issue:

There are multiple execution paths:

- old Supabase Realtime extension path,
- `/ws/agent`,
- native host,
- DSv4/CDP action engine,
- `SurfaceRuntime`,
- hosted `executeAction()`,
- product server direct paths.

This is why it keeps feeling like it "works" and then only opens a blank tab or fails in the real app.

Required strategy:

Build one shared `ActionDispatcher`.

Every action request goes through:

```text
ActionDispatcher
  -> choose surface adapter
  -> execute one bounded primitive sequence
  -> require visible receipt
  -> return queued/running/succeeded/asked/declined/failed
```

Never mark browser action `succeeded` just because it was dispatched. Only mark succeeded after receipt.

Valid receipts:

- Chrome extension/native bridge surface proof,
- DOM read,
- screenshot,
- AX tree,
- file hash,
- visible state diff.

Invalid receipts:

- "SUCCESS" log line,
- queued event,
- old screenshot,
- hidden Chrome,
- cloned Chrome,
- backend-only API result for a visual task.

## 10. Aevoy, Twilio, Calls, Texts, Email

These should be adapters, not the core product.

The core product should expose:

```text
NotificationAdapter
MessageAdapter
EmailAdapter
VoiceAdapter
```

When credentials are missing:

- adapter reports `configured: false`,
- product can queue/stub/decline visibly,
- nothing pretends a real text/call/email was sent.

When Twilio is added:

- SMS/call confirmations go through the same decision and memory learning loop.

When Aevoy/Cloudflare email is added:

- email notifications/drafts/sends go through the same adapter contract.

The rule:

```text
Communication channels are hands, not the brain.
```

They must not create separate memory, intent, or action systems.

## 11. Why Testing Felt Like It Was Blocking Work

The issue is not "testing is bad."

The issue was testing the wrong thing too early or accepting proof that did not prove the product.

Correct test philosophy:

1. Pick the smallest product spine failure.
2. Fix that failure.
3. Run the smallest proof that proves that exact failure is gone.
4. Ship if bundled code changed.
5. Move to the next spine failure.

Wrong test philosophy:

- build huge harnesses before the product path exists,
- count fixture-only passes,
- accept log-only success,
- test stale source servers,
- chase 100 strangers before the public DMG/extension/memory spine is clean.

## 12. Execution Loop

Use this loop every cycle:

```text
1. Read current V7 status.
2. Pick the earliest red product-spine blocker.
3. Assign parallel agents only to independent scopes.
4. Locally fix the blocking scope.
5. Run the smallest real proof.
6. If product code changed, ship.
7. Update status and handoff.
8. Repeat.
```

### New-Issue Protocol

When a new issue appears:

1. Capture exact failure.
2. Classify it:
   - artifact parity,
   - install,
   - extension/browser,
   - input/ASR,
   - memory/profile,
   - intent/proactive,
   - action/surface,
   - receipt/proof,
   - external dependency,
   - Omar-only decision.
3. Isolate the smallest repro.
4. Research current docs/issues if not obvious.
5. Patch one layer.
6. Prove the patch on the product spine.
7. Ship if bundled.
8. Record the result.

Do not jump to breadth while an earlier spine blocker is red.

## 13. Parallel Agent System

Run agents in parallel only when scopes do not overlap.

### Lead Agent

Owns:

- product spine,
- task order,
- integration,
- final commit decisions,
- shipping.

### Browser Agent Worker

Owns:

```text
extension_v4/
native_host/
engine/app/product/surface_runtime.py
scripts/v7/probe_real_surface_extension.py
public/install.sh extension checks
```

Does not touch memory or proactive code.

### Memory Worker

Owns:

```text
engine/app/anticipy/memory.py
engine/app/product/server.py memory/profile endpoints only
src/lib/memory-*.ts
src/lib/meta-monitor.ts
supabase/migrations/
```

Does not touch browser extension or action execution.

### Intent/Proactive Worker

Owns:

```text
contracts/INFERENCE.md
engine/app/anticipy/proactive_engine.py
engine/app/proactive_day/
engine/app/proactive/
src/lib/intent-*.ts
src/app/api/engine/analyze/
```

Does not touch extension/native host.

### Action Dispatcher Worker

Owns:

```text
engine/app/product/action_dispatcher.py or equivalent new module
engine/app/product/server.py action endpoints only
src/lib/execute-action.ts
src/app/api/engine/confirm/
```

Does not touch memory schema except to read it.

### Packaging Worker

Owns:

```text
scripts/ship.sh
scripts/build_dmg.sh
state/builds/manifest.json
public/install.sh
desktop/src-tauri/
```

Does not touch product logic.

## 14. Detailed Phase Plan

### Phase 0 - Stabilize The Ground

Goal:

The repo, live app, public DMG, and installed app agree about what version exists.

Tasks:

1. Run:
   ```bash
   bash scripts/v7/check_done.sh
   ```
2. Inspect:
   ```bash
   jq '.diagnostics.dmg, .diagnostics.commits' state/check_done_v7.json
   ```
3. Fix public DMG parity:
   - if public DMG is wrong, rerun `scripts/ship.sh`;
   - if manifest is wrong, update manifest only after verifying the public artifact is the intended build;
   - never paper over mismatch.
4. Confirm:
   ```bash
   curl -fsS "https://www.anticipy.ai/api/app/state?x=$(date +%s)" | jq .
   curl -fsSL --max-time 300 https://www.anticipy.ai/dl/Anticipy_1.0.0_aarch64.dmg | shasum -a 256
   cat state/builds/manifest.json | jq .
   ```

Done when:

- live commit is current,
- public DMG SHA equals manifest SHA,
- installed app is the public app,
- no source server is being mistaken for product.

### Phase 1 - Canonical Browser Bridge

Goal:

One Chrome path:

```text
local engine -> SurfaceRuntime -> native host -> extension_v4 -> real Chrome
```

Tasks:

1. Rename or fence legacy extension build scripts so they cannot overwrite `public/anticipy-extension.zip`.
2. Make `scripts/v7/package_extension_v6.sh` the only public extension packager.
3. Add or verify `/api/surface/status` on the installed engine.
4. `/api/surface/status` must report:
   - native host installed,
   - extension connected,
   - bridge source,
   - extension version,
   - active Chrome profile path,
   - no clone.
5. Replace `local-dev` default secret with install-generated random secret shared by engine and native host.
6. Make `/app` show a clear "Chrome extension not connected" state when missing.
7. Add one product proof:
   - submit "open example.com",
   - bridge opens/reads real Chrome tab,
   - receipt source is native extension bridge,
   - proof includes URL/title/DOM/screenshot summary.

Done when:

- extension path is not ambiguous,
- installed product can prove browser control without fallback/manual Computer Use,
- no old extension path can overwrite the public extension zip.

### Phase 2 - Memory Spine

Goal:

One account/device memory system.

Tasks:

1. Replace static local `USER_ID` with provisioned account/device ID.
2. Store local profile and `memory.jsonl` under account/device path.
3. Make `/api/provision` persist:
   - account ID,
   - device ID,
   - build ID,
   - memory namespace.
4. On profile save, write:
   - local profile,
   - local memory anchors,
   - cloud dossier/memory sync.
5. On provision, pull hosted dossier/profile into local memory if newer.
6. Seed people, emails, aliases, pronouns, do-not-touch list, critical tools, and recurring topics into local memory.
7. Make hosted `/api/engine/analyze` read active dossier/profile context, not only learned accept/reject profile.
8. Add test:
   - user A profile cannot appear in user B memory,
   - onboarding profile influences intent resolution,
   - pronoun/alias resolves correctly,
   - do-not-touch blocks action.

Done when:

- onboarding memory actually affects inference and action,
- no static user ID is used for product state,
- local and hosted memory have clear source/provenance.

### Phase 3 - Unified Input Boundary

Goal:

MP3, transcript, computer mic, external mic all create the same normalized input record.

Tasks:

1. Make each input mode write `anticipy.normalized_input.v7`.
2. Verify MP3 upload writes audio hash, transcript, ASR metadata.
3. Verify transcript paste writes text hash and `source_mode=transcript_upload`.
4. Verify computer mic writes selected device and `mic-asr` receipt.
5. Verify external mic writes selected external device and `mic-asr` receipt.
6. Add device selection UI/state for external mic.
7. Do not count BlackHole or built-in mic as external mic.

Done when:

- all four modes enter the same downstream inference path,
- downstream code does not care which mode produced the transcript except metadata.

### Phase 4 - Canonical Intent/Proactive Runtime

Goal:

One product inference brain.

Tasks:

1. Choose canonical runtime for product decisions.
2. Mark older proactive/analyze paths as adapters or legacy.
3. Convert every input event to:
   - memory context,
   - recent surface context,
   - candidate wants,
   - risk,
   - decision.
4. Implement hard negative handling:
   - jokes,
   - quotes,
   - hypotheticals,
   - third-party wants,
   - already-satisfied wants,
   - ambiguous unsafe asks.
5. Store silent and decline decisions.
6. Add transcript/MP3 proactive eval:
   - clear actionable,
   - ambiguous ask,
   - competent decline,
   - silent no-op.

Done when:

- proactive is not a side simulation,
- it is the live decision engine for ambient input.

### Phase 5 - Action Dispatcher

Goal:

One action execution path.

Tasks:

1. Add shared `ActionDispatcher`.
2. Route hosted confirm, local proactive ACT, `/api/act`, and auto-proceed through it.
3. Define statuses:
   - queued,
   - running,
   - succeeded,
   - asked,
   - declined,
   - failed.
4. Do not return `succeeded` until visible receipt exists.
5. If surface missing or blocked, return ask/decline with proof.
6. Keep DSv4/CDP as an adapter only if it can produce visible receipts through real Chrome.
7. Add proof:
   - browser navigation,
   - search/read,
   - form fill ask/decline,
   - native-app ask/decline.

Done when:

- action success means the user's visible surface changed or a correct ask/decline was shown.

### Phase 6 - General Browser Agent

Goal:

Move beyond five websites.

Tasks:

1. Implement read-act-verify loop using surface primitives.
2. Prefer keyboard shortcuts and DOM reads when reliable.
3. Fall back to screenshot/vision for canvas.
4. Learn user-local recipes only after successful receipts.
5. Add hostile-surface behavior:
   - ask or decline on CAPTCHA,
   - do not evade bot protection,
   - do not leave half-filled forms.
6. Prove across:
   - Gmail,
   - Calendar,
   - generic website,
   - CRM-like DOM,
   - canvas/design,
   - e-commerce decline/cart prep,
   - native Mac app.

Done when:

- unknown web apps can be read, acted on in bounded steps, and verified,
- failure is a competent ask/decline, not a broken tab.

### Phase 7 - Proactive Product Behavior

Goal:

Anticipy acts ambiently, not only on explicit prompts.

Tasks:

1. Feed live mic/transcript windows into proactive runtime.
2. Add surface observation events:
   - visible tab context,
   - active app,
   - recent user action,
   - calendar/message/page state.
3. Make proactive decisions:
   - act for low-risk obvious tasks,
   - ask for ambiguous/high-risk,
   - decline when unverifiable,
   - stay silent for non-actionable context.
4. Test with Omar's MP3 and generated transcripts.
5. Include memory-sensitive cases:
   - "send it to her",
   - "that thing from Friday",
   - "the one we discussed",
   - "do not touch payroll/legal".

Done when:

- proactive behavior uses memory and surface context,
- not just explicit command transcripts.

### Phase 8 - Breadth And Scale

Goal:

Scale from 3 counted interactions to 100.

Tasks:

1. Generate stranger interactions only after earlier spine gates are clean.
2. Count only public-installed-engine runs with real surface receipts.
3. Cover at least 20 categories.
4. Cover hard categories:
   - canvas,
   - CRM,
   - e-commerce,
   - native,
   - ambient.
5. Stop counting anything with stale proof or fake receipts.

Done when:

- 100 successful interactions,
- 20 categories,
- 5 hard categories,
- last 20 pass.

### Phase 9 - Omar-Owned Clean Room

Omar will handle clean-room installs.

Engineering still must provide:

1. Clear clean-room checklist.
2. Public download URL.
3. Expected hashes.
4. Commands to collect installed engine health.
5. A file format for Omar to paste proof into:
   ```text
   state/v7/clean_room_public_install.json
   ```

This is off the engineering critical path until Omar supplies the runs.

## 15. Immediate Next 12 Tasks

Do these in order unless a command proves the order is wrong.

### Task 1 - Fix Public DMG Parity

Owner: packaging worker.

Files:

```text
scripts/ship.sh
scripts/build_dmg.sh
state/builds/manifest.json
public/install.sh
```

Success:

```bash
bash scripts/v7/check_done.sh
jq '.gates["V7.5_public_dmg_sha_green"]' state/check_done_v7.json
```

Must be `true`.

### Task 2 - Freeze Legacy Extension Artifacts

Owner: browser worker.

Files:

```text
extension/build.sh
scripts/v7/package_extension_v6.sh
public/anticipy-extension.zip
public/anticipy-extension-v6.zip
```

Success:

- only `extension_v4` builds public extension zip,
- legacy `extension/build.sh` cannot overwrite public zip without an explicit failure.

### Task 3 - Add Surface Status Endpoint

Owner: browser worker.

Files:

```text
engine/app/product/server.py
engine/app/product/surface_runtime.py
native_host/anticipy_agent.py
extension_v4/background.js
```

Success:

```bash
curl -fsS http://127.0.0.1:8731/api/surface/status | jq .
```

It must show extension/native bridge connected or a precise missing-step state.

### Task 4 - Install-Generated Bridge Secret

Owner: browser/packaging worker.

Files:

```text
public/install.sh
native_host/anticipy_agent.py
engine/app/product/surface_runtime.py
```

Success:

- no `local-dev` default in product proof,
- engine and native host share install-generated secret.

### Task 5 - Account/Device Scoped Memory

Owner: memory worker.

Files:

```text
engine/app/product/server.py
engine/app/anticipy/memory.py
engine/app/anticipy/platform_adapter.py
```

Success:

- no product profile/memory writes under static `anticipy-user`,
- account switch cannot read previous account profile.

### Task 6 - Make Dossier Active

Owner: memory worker.

Files:

```text
src/app/api/engine/analyze/route.ts
src/lib/intent-prompt.ts
engine/app/product/server.py
```

Success:

- onboarding people/do-not-touch/tools appear in inference prompt/context,
- transcript "send it to her" resolves from profile when unambiguous,
- ambiguity asks instead of guessing.

### Task 7 - Shared Action Dispatcher

Owner: action dispatcher worker.

Files:

```text
engine/app/product/action_dispatcher.py
engine/app/product/server.py
src/lib/execute-action.ts
src/app/api/engine/confirm/route.ts
```

Success:

- no browser action is marked succeeded without visible receipt,
- hosted confirm and local proactive both use same dispatcher.

### Task 8 - Canonical Proactive Runtime

Owner: proactive worker.

Files:

```text
engine/app/anticipy/proactive_engine.py
engine/app/proactive_day/
engine/app/proactive/
engine/app/product/server.py
```

Success:

- one product proactive path documented and used,
- other paths marked adapter/legacy,
- transcript window can produce act/ask/decline/silent decision.

### Task 9 - External Mic Proof

Owner: input worker.

Files:

```text
engine/app/product/server.py
src/app/app/page.tsx
contracts/INPUT_MODES.md
state/v7/input_modes.json
```

Success:

- a real external mic is selected,
- engine records selected device,
- fresh `mic-asr` transcript enters same boundary.

### Task 10 - Deterministic Transcript Driver

Owner: harness worker.

Files:

```text
scripts/v7/drive_transcript_paste_ui.py
scripts/v7/probe_real_surface_extension.py
```

Success:

- transcript driver works without manual Computer Use when extension bridge is connected,
- if bridge missing, failure is precise and actionable.

### Task 11 - Native + Ambient Stranger Passes

Owner: lead or evaluator worker.

Files:

```text
state/strangers/
scripts/v6/breadth_audit.py
verifier/v6/trace_reader.py
```

Success:

- native hard category counted,
- ambient hard category counted,
- no fake receipt.

### Task 12 - Scale Breadth

Owner: orchestrator plus parallel workers.

Success:

- 100 successful interactions,
- 20 categories,
- 5 hard categories,
- last 20 pass.

## 16. Definition Of "Actually Done"

For engineering, excluding Omar-owned clean-room installs for now:

```text
DONE-ENGINEERING =
  public app live
  public DMG parity green
  installed engine current
  Chrome extension/native bridge canonical and connected
  all four input modes enter one boundary
  memory is account/device scoped and active
  intent/proactive uses memory and surface context
  action dispatcher requires visible receipts
  proactive ambient behavior proven
  browser/native/canvas/e-commerce/CRM categories proven
  no fake receipts
  no cloned Chrome proof
```

For full V7 product:

```text
DONE-FULL =
  DONE-ENGINEERING
  plus Omar's 3 clean-room public installs
  plus 100 stranger successes
  plus 20 categories
  plus 5 hard categories
  plus last 20 interactions pass
  plus state/COMPLETE.md written by mechanical checker
```

## 17. What To Say To Omar During The Work

Use this status format:

```text
Current blocker:
What I changed:
What proof passed:
What proof failed:
What is next:
Ship required: yes/no
```

Do not say:

```text
done
mostly done
works locally
probably
should
```

unless the mechanical proof says so.

## 18. First Command For The Next Work Session

```bash
cd /private/tmp/anticipy-ship-8c4935a
git fetch origin main
git status --short
bash scripts/v7/check_done.sh
jq '{red_gates: (.gates | with_entries(select(.value == false))), commits: .diagnostics.commits, dmg: .diagnostics.dmg, counts: .diagnostics.stranger_counts}' state/check_done_v7.json
```

Then start with Task 1: public DMG parity.

