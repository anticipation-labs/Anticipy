# Anticipy Demo-Readiness Audit

Auditor: demo-readiness pass
Date: 2026-05-07
Target flow: `/engine` (https://www.anticipy.ai/engine) → install Chrome extension → talk into mic → confirm intent → extension acts.
Scope: every issue a non-technical investor will hit. Severity: blocker / major / minor / cosmetic.

Counts:
- Blocker: 8
- Major: 14
- Minor: 9
- Cosmetic: 6
- Total: 37

---

## TOP-OF-FUNNEL & ONBOARDING

### 1. Access code "123" is for `/internal`, not `/engine`. Demo prompt is wrong. [BLOCKER]
- File: `src/app/internal/layout.tsx:26` hardcodes `cleaned === "123"`. The `/engine` flow has NO "123" access code anywhere. The 10-char per-user access code is generated server-side in `src/app/api/extension/access-code/route.ts:7-17` (alphabet `ABCDEFGHJKMNPQRSTUVWXYZ23456789`, length 10) and is for the **extension popup**, not for unlocking the page.
- What the user sees vs expected: If the demo script says "enter 123 on /engine," the investor sees a Sign in / Create account form (`page.tsx:1175-1539`) and is stuck. If the script means "/internal is the demo," the rest of the flow (record, intents, extension) doesn't exist there.
- Repro: Open `https://www.anticipy.ai/engine`; you get an email/password auth form, not an access-code prompt.
- Fix: Either align the demo script (sign up with a throwaway email; the 10-char code shown post-sign-in is for the extension), or pre-create a demo Supabase auth user and pre-pin its access code. Don't use `/internal` for the public demo.

### 2. First-time visitor has no "what is Anticipy" hook above the auth form. [MAJOR]
- File: `src/app/engine/page.tsx:1212-1234`. Tagline is "Your AI that acts, not just answers." Subtitle: "Sign in to record a conversation, see the actions Anticipy picks up, and connect the Chrome extension that runs them for you." There's no 1-line product explanation, no example, no demo video.
- Investor reaction: clicks the page → sees a sign-up wall before knowing what they're signing up for. High bounce risk.
- Fix: Add a 30-second loom or a 3-bullet "you talk → we extract actions → your Chrome runs them" above the auth card.

### 3. Page does not require / mention installing the Chrome extension before sign-up. [MAJOR]
- File: `src/app/engine/page.tsx:1510-1524`. The hint "After signing in, you'll receive your extension access code and a download link" is pre-auth, but the order is exactly backwards from what the user logically should do (install first, then sign in is fine; sign in first is also fine — but the page doesn't TELL them either way). Plus on Safari/Firefox the install will fail (see #6).
- Fix: Add a "Requires Google Chrome" badge to the auth screen. Add an "Install extension" button visible pre-auth that opens the install guide.

### 4. Install guide URL `/engine/extension` is not linked from the unauthenticated auth screen. [MINOR]
- File: `src/app/engine/page.tsx` — the install-guide links (lines 1849, 2506) are only visible after sign-in. A skeptical investor who reads the auth wall and bounces never sees the install path.
- Fix: Add "Install guide" link in the pre-auth tagline area.

---

## AUTH

### 5. Email/password sign-up requires email confirmation — investor cannot demo immediately. [BLOCKER]
- File: `src/app/engine/page.tsx:306-308`: when sign-up returns no session, page renders "We sent a confirmation link." If Supabase project has email confirmations enabled (typical default), the investor must open their inbox, click a link, come back. Demo blocks for >30 seconds at best, or fails entirely if email is greylisted.
- Fix: Disable email confirmation for the demo Supabase project, OR pre-create a known demo account (e.g., `demo@anticipy.ai` / `anticipy123`) and document it.

### 6. Sign-in UI says nothing about which browser to use. Safari/Firefox users hit a hard wall. [MAJOR]
- File: `src/app/engine/page.tsx:577-580`. `MediaRecorder` is created with `audio/webm`. Safari (iOS + macOS) does NOT support `audio/webm` — `isTypeSupported` returns false and the constructor throws `NotSupportedError`. Firefox supports it, but the rest of the demo (Chrome extension) requires Chromium.
- The error reaches `friendlyError()` which translates `NotSupportedError` to "Something didn't go through. Give it another sec and try again." — wrong, it'll never work in Safari.
- Fix: At page mount, detect `!MediaRecorder.isTypeSupported("audio/webm")` and show a "Please open in Chrome" banner. Also add `audio/mp4` fallback: `MediaRecorder.isTypeSupported("audio/mp4") ? "audio/mp4" : "audio/webm"`.

### 7. "Forgot password" sends a Supabase email; reset flow drops user back into recovery mode and forces them to sign in twice. [MINOR]
- File: `src/app/engine/page.tsx:354-364`. After password update, user is dropped into sign-in screen with no auto-fill. Fine, but wastes 30s mid-demo.

### 8. Wrong-format access code on the extension popup → opaque "Error 401" message. [MINOR]
- File: `extension/popup.js:74` shows `Error 401` from `data.error` (or fallback). Users see "Invalid access code" — fine — but if the API server is down they see a raw HTTP code.
- Fix: Show "Couldn't reach Anticipy. Check connection." for non-401 errors.

---

## MIC / RECORDING UX

### 9. Recording state has no MIME-fallback for Safari/iOS — silent crash. [BLOCKER on Safari]
- File: `src/app/engine/page.tsx:577-580`. Same as #6. `new MediaRecorder(stream, {mimeType: "audio/webm"})` throws on Safari.
- Repro: Open `/engine` on iPhone or macOS Safari, sign in, hit record. Page goes to "Let's try that again" with a generic error.
- Fix: Add `audio/mp4` MIME fallback and gracefully error message.

### 10. AudioContext sampleRate:16000 may be rejected on some Safari versions. [MAJOR]
- File: `src/app/engine/page.tsx:461`. Older Safari rejects non-default sample rates. Combined with #9, makes Safari unusable.
- Fix: Wrap in try/catch; fall back to `new AudioContext()` and let Deepgram resample.

### 11. Recording-button has no "Click to allow microphone" pre-state. [MINOR]
- File: `src/app/engine/page.tsx:2108-2161`. First-time mic permission prompt fires inside `getUserMedia`. If user denies, `friendlyError` says "Microphone access is blocked. Allow the mic in your browser and try again." — good — but the recording button just snaps back to idle with no visible inline help.
- Fix: Show an inline "Open browser site settings" link when error contains "permission".

### 12. Live transcript card is hidden during `state==="recording"` until first segment arrives. Looks broken if you talk for 5 seconds. [MAJOR]
- File: `src/app/engine/page.tsx:2213`. Condition `(segments.length > 0 || liveText)` means the live-transcript card DOES NOT RENDER until Deepgram returns its first result, which is typically 1-3 seconds after speech starts. During that window the page shows "Listening… Recording — 0:03" but no visible feedback that audio is being captured. Investor will tap the dot a second time, accidentally stopping.
- Fix: Always render the empty live-transcript shell during recording; show a placeholder "Listening for speech…" until `liveText` has content.

### 13. No live captions for Speaker 0 vs Speaker 1; speaker numbering shows raw `Speaker 0`. [COSMETIC]
- File: `src/app/engine/page.tsx:2236, 2343`. "Speaker 0" / "Speaker 1" — investor expects "You" / "Other" or named labels.
- Fix: Map `speaker_id===0` → "You", others → "Speaker 2"/3 etc.

---

## INTENT DISPLAY

### 14. Intent card during `state==="recording"` shows ONLY summary — no buttons, no evidence. [MAJOR]
- File: `src/app/engine/page.tsx:2287-2311`. Live intents during recording have no "Yes, do it" button. The user has to STOP RECORDING first to act — which destroys the "ambient agent" promise the demo is supposedly selling.
- Fix: Allow confirm directly from the live intent card.

### 15. Intent confidence + raw `action_type` are not shown. Investor cannot tell why this thing fired. [MINOR]
- File: `src/app/engine/page.tsx:2363-2400`. Card renders summary + evidence quote + importance badge tint. But the popup (`extension/popup.js:188-192`) DOES show confidence percent and action_type — inconsistent surface.
- Fix: Add subtle "via voice · 92%" footnote on each card.

### 16. Importance badge has tint but no LABEL on the engine page. [COSMETIC]
- File: `src/app/engine/page.tsx:2354-2399`. The card's bg/border tints based on importance, but the `IMPORTANCE_STYLES` `label` value ("CRITICAL"/"Important"/"Standard"/"Low") at lines 86-110 is never rendered. So investor sees a red-tinted card without knowing why.
- Fix: Render the badge label as a small uppercase tag.

### 17. Evidence quote uses smart quotes "&ldquo;...&rdquo;" — when the quote contains apostrophes/quotes, layout looks ragged. [COSMETIC]

---

## CONFIRM FLOW (the critical post-yes window)

### 18. After "Yes, do it" the page shows static "Sent to your extension" pill forever. No progress, no result, no error surface. [BLOCKER]
- File: `src/app/engine/page.tsx:2402-2417`. The `decideIntent` callback only updates local `intentDecisions[id]` state. There is ZERO subscription to Supabase Realtime / agent_status / execution_result. After the click, the page is dead.
- Investor sees: agent is silently working in another window for 60-180 seconds while the engine page just says "Sent to your extension" — looks broken / stalled.
- Fix: Subscribe to Supabase `anticipy_intents` UPDATEs for the user's session; render `running…/done/failed` in the intent card with the `execution_result` text.

### 19. CLARIFICATION LOOP IS COMPLETELY MISSING — exact gap from the demo failure. [BLOCKER]
- Files: `extension/agent.js:115` (REQUIRED-SLOT prompt), `extension/agent.js:331-333` (returns `{success:false, message:<question>}`), `extension/background.js:354-363` (writes `execution_result: result.message` to Supabase), `src/app/engine/page.tsx` (NO subscription to that field, NO clarification UI, NO reply input).
- Behavior today: agent sees "book a flight" with no destination → returns `success:false, message:"Where would you like to fly from and to, and on which dates?"` → message lands in `anticipy_intents.execution_result` → /engine never reads that → user sees the same "Sent to your extension" pill forever. The popup briefly shows "Agent failed: Where would you like to fly..." but that is in the extension popup, not on the demo page the investor is watching.
- Fix (the actual one):
  1. /engine page subscribes to UPDATEs on `anticipy_intents` for the active session.
  2. When `status==='failed'` AND `execution_result` looks like a question (ends with `?`, or use a structured `clarification_question` field), render an inline question card with a text input + "Reply" button.
  3. POST the reply to a new endpoint `/api/engine/clarify` that re-runs the agent with the prior intent + the user's answer merged into parameters (or creates a new linked intent with `parent_intent_id`).
  4. Re-broadcast `confirmed_intent` so the extension picks it up and continues.
- Without this, every "book a flight" / "schedule a meeting" / "send an email" without all slots ends in a frozen pill.

### 20. No detection of "extension not installed". CTA is a perpetual footnote. [MAJOR]
- File: `src/app/engine/page.tsx:2462-2518`. The "No Chrome extension yet?" card renders unconditionally, even after the user has installed and signed in. Comment in code explicitly says "we can't reliably detect the extension". This means an investor who DID install will still see the install CTA — looks unfinished.
- Fix: Have the extension's content script set `window.__anticipy_ext_installed__ = true` on `/engine` (or post a `MessageChannel` ping). Page hides the CTA when ping arrives within 1s.

### 21. Extension never "acks" the confirmed-intent broadcast back to /engine. [MAJOR]
- File: `extension/background.js:285-321` runs `BrowserAgent` synchronously inside the SW message handler with no ack. The `/engine` page has no way to know if the broadcast was actually received. If the SW is asleep (MV3 kills it after 30s idle) the keep-alive alarm fires every 24s — but at the moment of confirm there's a 1-3s window where the SW is dead. The realtime WS reconnect then fires (background.js:131-247).
- Fix: Page should query `chrome.runtime.sendMessage({extensionId, ping:true})` post-confirm; show "Extension running" badge.

### 22. Double-click protection on confirm is half-done. [MINOR]
- File: `src/app/engine/page.tsx:2429, 2444`. Buttons are `disabled={decision === "loading"}`, good. But the API `GET /api/engine/confirm` is idempotent only at the DB level (`status==='pending'` guard at confirm/route.ts:32-35). A truly racy double-tap before the React state flips to "loading" CAN fire two requests; the second returns "handled" and bytes back through the catch handler. End result is fine but the spinner can jump.
- Fix: Set decision to "loading" synchronously before the await.

---

## ACTION PROGRESS / MULTI-STEP

### 23. While the agent is running (10-90s), /engine has no progress indicator. [BLOCKER]
- File: `src/app/engine/page.tsx`. Same root cause as #18.
- The popup shows step counter "Step 5/60…" (popup.js:140-149), but a presenting investor stays on /engine, NOT on the popup. They see frozen state.
- Fix: Subscribe to Realtime; surface agent step counter via the broadcast channel.

### 24. Multi-step task (3-5 minutes for flights) UI unchanged. [MAJOR]
- Same as #23. After 3 minutes of nothing happening, the audience assumes failure. Demo dies in the silence.
- Fix: Show a live "Searching flights…" / "Comparing prices…" feed pulled from the agent's recent step verbs.

### 25. Single popup window is the only place to see the agent working — mostly hidden during demo. [MAJOR]
- The popup auto-closes when the user clicks anywhere else. So as soon as the user clicks "Yes, do it" and the popup opens then they look at the slide deck, the popup closes. There is no persistent in-page surfacing.

---

## FAILURE SURFACING

### 26. When agent fails, message has technical debug suffix appended. [MAJOR]
- File: `extension/agent.js:175-191`. On failure, message is augmented with `"... | last:✗click(sel=...) ✗type(sel=...) | data:{...}"`. This is INTENDED for debugging but lands in `anticipy_intents.execution_result` which is shown in the extension popup notification (background.js:323-330). Investor reads "Task could not be completed | last:✗click(sel=button.cdx-button) ✗type(sel=input[name=q]) | data:{}".
- Fix: Strip the debug suffix in production; keep it behind a `localStorage.anticipy_debug` flag.

### 27. "Reached max 60 steps" / "timed out" / "LLM did not return a valid action" messages reach the user verbatim. [MAJOR]
- File: `extension/agent.js:211, 247, 355`. These error strings are not friendly. They should be user-facing variants.
- Fix: Map agent failure modes to friendly text via a table: timeout → "That took longer than expected — try a simpler ask." / step limit → "I got stuck on the page — let me try a different approach next time."

### 28. Captcha / login-wall / DataDome failures are not specifically detected for messaging. [MAJOR]
- The agent prompt says "if you see a password field on a path you can't bypass, end with done success:false explaining the wall." (agent.js:113) — relies on the LLM to phrase it well.
- Fix: detect failure messages containing "sign in"/"log in"/"captcha"/"verify"/"blocked" and surface a structured "I need you to sign in to that site first" message with a deep-link button.

### 29. `result.message = "Failed to send SMS: ..."` exposes raw provider error. [MINOR]
- File: `src/lib/execute-action.ts:451`. Twilio errors leak to user.

---

## EDGE CASES

### 30. Silent recording → "We didn't catch any speech" but no retry-with-mic-test prompt. [MINOR]
- File: `src/app/engine/page.tsx:746-749`. Calmly says "We didn't catch any speech" — fine — but the user might just be in a loud room with weak input gain. No "test your mic" affordance.

### 31. Auto-analyze fires every 30s and re-extracts duplicates server-side, but doesn't tell the user nothing was found. [MINOR]
- File: `src/app/engine/page.tsx:596-631`. After 60s of recording with zero detectable intents, the user sees "Listening… 1:00" and nothing else. They don't know the system is working.
- Fix: Subtle "Listening — no actions yet" microcopy below the live transcript.

### 32. Manual transcript path doesn't validate emptiness; pasting whitespace bypasses the trim. [COSMETIC]
- File: `src/app/engine/page.tsx:826`. Already trims — fine — but the analyze button only renders on non-trimmed content (line 2274). Edge case minor.

### 33. Intent fires while user has NO extension installed → confirmed status broadcast goes nowhere. [MAJOR]
- File: `src/app/api/engine/confirm/route.ts:97-124`. The broadcast happens regardless. The note fallback (`src/lib/execute-action.ts:256-261`) does save the task to `anticipy_notes` — good. But the user just sees "Sent to your extension" with no "we couldn't reach your extension; the action is saved as a note here" follow-up.
- Fix: After 30s of no extension ack, surface "Looks like your extension isn't connected — install it to actually run this."

### 34. Realtime broadcast fails (SUPABASE service-role key missing in env) — silent. [MAJOR]
- File: `src/app/api/engine/analyze/route.ts:351-377` and `src/app/api/engine/confirm/route.ts:97-124`. Both broadcasts have `if (supabaseUrl && serviceKey)` guards. If `SUPABASE_SERVICE_ROLE_KEY` is missing, broadcast silently skipped. Page never knows.
- Fix: Surface a server-config check on app boot; alert when keys are missing.

### 35. Confirm returns 500 → user sees "Confirm failed" message in the catch but state resets, no retry button. [MINOR]
- File: `src/app/engine/page.tsx:909-916`. Catch resets the decision so the user CAN re-click. But there's no toast / no error tag — they have to figure out the click silently failed.

---

## EXTENSION POPUP

### 36. Popup says "Load unpacked from chrome://extensions · Developer mode on" at the bottom — looks unfinished. [COSMETIC]
- File: `extension/popup.html:259-261`. This dev-only note is shipped to investors.
- Fix: Hide unless `chrome.runtime.id` is set to a known dev id.

### 37. Popup connection-status badge is "Connecting…" by default and stays gray for ~3s. [COSMETIC]
- File: `extension/popup.html:204` shows "Connecting…" while `popup.js:38-42` waits for background to respond. In practice the user sees a gray dot for the first few hundred ms. Minor polish.

---

## MOBILE / RESPONSIVE

### 38. /engine renders on mobile but the demo flow is unusable. [BLOCKER for mobile demo]
- The Chrome extension cannot install on iOS Safari at all, and on Android Chrome only with side-loading. The page itself renders fine (uses fluid tailwind), but the entire flow is desktop-Chrome-only.
- Fix: Detect mobile UA and show "Anticipy needs desktop Chrome — open this on your laptop." banner.

### 39. Mobile auth screen padding is tight; inputs touch the screen edge on iPhone SE. [COSMETIC]

---

## SUMMARY TABLE OF BLOCKERS

| # | Blocker | One-line fix |
|---|---------|--------------|
| 1 | "123" code is wrong for /engine | Align demo script; use real per-user code |
| 5 | Email confirmation gates sign-up | Disable email confirm OR ship a known demo account |
| 9 | Safari MediaRecorder crashes | Add audio/mp4 MIME fallback + browser detect |
| 18 | Confirm pill shows forever, no progress | Subscribe to Realtime intent updates on /engine |
| 19 | Clarification loop entirely missing | Subscribe + render question + reply input + clarify endpoint |
| 23 | No progress feedback during 10-90s agent run | Same Realtime subscription + step verb broadcast |
| 38 | Mobile demo unusable | Detect mobile, show "open on laptop" banner |
| 33 (effective blocker) | Extension-not-installed → silent failure on confirm | Detect extension; show fallback message |

Investor will trip on blockers 1 + 5 + 19 + 18 within the first 90 seconds.
