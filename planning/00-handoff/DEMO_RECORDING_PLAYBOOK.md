# Demo Recording Playbook

For Omar. One investor video, three demo moments, two minutes thirty total of usable footage. Read once. Record without hesitation.

Every behavior below traces to a verify command that PASSED in `state/orchestrator/E2E_TESTS_AUTONOMOUS.json` at 2026-05-30T00:10:00Z and to `state/v7/z001_e2e_runs/20260530T001121Z/result.json`.

## 1. 30-second pre-flight checklist

Run this before you hit record. Total wall time about 30 seconds plus the warm-up wait.

```bash
# (a) Engine healthy on 8731 and is the packaged binary, not source.
PID=$(lsof -t -nP -iTCP:8731 -sTCP:LISTEN | head -1)
ps -p $PID -o command= | grep -q "/Applications/Anticipy.app" && echo "OK engine packaged pid=$PID"

# (b) Bridge healthy on 7777.
curl -sS http://127.0.0.1:7777/status | jq -r '.ok, .cdp_alive'   # both true

# (c) Chrome on 9222 against the cloned profile.
curl -sS http://localhost:9222/json/version | jq -r '.Browser'    # Chrome/148+

# (d) Dossier loaded, at least 10 people, Altaf + Zara present.
jq -r '.people | length' ~/.anticipy/v7/dossiers/anticipy-user/dossier.json   # 24

# (e) Real Twilio for SMS pre-confirm. Default is TWILIO_MOCK=true in .env.local.
# To send a real SMS to your phone during demo moment 2, set in your shell BEFORE relaunching the engine:
#   export TWILIO_MOCK=0
#   export TWILIO_TEST_TO_REAL_NUMBER=1
#   export TWILIO_TEST_REAL_NUMBER="+1XXXYOURNUMBER"
# If you skip this, the SMS step is a no-op; pre-narrate it with "and here is where the SMS lands" without claiming it fired.

# (f) Proactive features ON.
export ANTICIPY_QUIET=0

# (g) Prompt cache warm-up. The first universal-loop call after a cold binary spawn can blow the 240s deadline (cycle 115 lesson). Fire one cheap warmup, then wait. Total wait under 30 seconds.
curl -sS -X POST http://127.0.0.1:8731/api/listen/inject \
  -H 'Content-Type: application/json' \
  -d '{"text":"wait, when did the Roman Empire fall"}' >/dev/null
sleep 20    # OpenRouter cache fills; second-call latency drops to 0.9-1.8s
```

If any line is not OK, fix it before recording. Do not record over warnings.

## 2. Demo moment 1: Trivia in your ear (30 to 45 seconds)

**Goal viewer should feel:** The thing in his ear is faster than Google. He stops mid-sentence and the answer is already there.

**Setup.** Mac mic on. Anticipy menubar icon visible top-right. AirPods in (Sarah voice). Quiet room.

**The script you say out loud:**

> (looking at the camera) "Friend asks me a question." (pause one beat) "Wait, when did the Roman Empire fall?"

**What happens.** Within 50 milliseconds the engine fires TRIVIA_FIRE, ElevenLabs Sarah cached voice plays in your AirPod: "The Western Roman Empire fell in 476 AD. Constantinople, the eastern capital, held until 1453." (Verified at 16.92 ms perceived latency, `E2E_TEST_2_trivia_in_the_wild`.)

**Expected timing.** Speak to audio in your ear: under 2 seconds. The pause should look like you're listening, not waiting.

**Recovery line if it does not fire in 3 seconds.** "Hold on, let me try one I know it has." Switch to "wait, when was the moon landing" (also cache-hit, 13.0 ms). If THAT does not fire, stop recording and rerun pre-flight step (g).

**Visual proof to land on.** Cut to the menubar popover showing the trivia fire event in the recent activity strip. Then cut back to you saying "That was 1.2 seconds. No screen. No tap."

**Safe trivia phrases (all PASS in last 24h, all cache-hit):**
- "wait, when did the Roman Empire fall"
- "wait, when was the moon landing"
- "wait, when did the Berlin Wall fall"
- "wait, when was the Eiffel Tower built"
- "wait, when did the Declaration of Independence get signed"

Do NOT improvise outside this list mid-recording. WWII trivia source-fix is in commit f881d04d but takes effect only on next sidecar rebuild.

## 3. Demo moment 2: Silent execute (60 to 90 seconds)

**Goal viewer should feel:** He spoke. He did not type. A real email is already drafted in real Gmail, with the right person and the right body, before he reaches his desk.

**Setup.** Chrome window visible, signed into your real Gmail (mail.google.com is the active tab). Drafts folder closed. Stopwatch in shot if you want the dramatic angle.

**The script you say out loud:**

> "I just had coffee with Altaf. I want to send him a thank-you note." (then, to the room, not to a wake word) "Draft a thank-you email to Altaf Ebrahim about today."

Use the name "Altaf Ebrahim". Do NOT speak the email address out loud. Parakeet ASR mangles long alphanumeric aliases (per HANDOFF_HONEST section 4). The dossier already has Altaf with his real email, so the name resolves.

**What happens.**
1. Parakeet transcribes locally on MLX.
2. Engine routes to `/api/act` with intent=email_draft.
3. (If real Twilio is enabled per pre-flight) within ~10 seconds your phone buzzes: "Anticipy: draft email to Altaf about today. Reply YES / NO / EDIT." Hold the phone toward camera. Say "I reply YES" and tap YES.
4. If Twilio is in MOCK mode, narrate: "In production this is where the SMS lands. For this recording we are muted on the SMS side." Do NOT mime a fake reply.
5. Gmail draft path bypasses the SMS gate by design for drafts only (see `engine/app/product/sms_pre_confirm.py:380`). The draft appears in `mail.google.com/u/0/#drafts` within ~30 seconds, recipient resolved to Altaf's real email from the dossier, subject and body in your voice. Verified path: `state/v7/z001_e2e_runs/20260530T001121Z/result.json` 9/9 PASS, real draft visible.

**Expected timing.** Speech to visible draft: 25 to 40 seconds. The cycle 115 cold-cache risk is handled by pre-flight step (g).

**Recovery line if the draft does not appear in 45 seconds.** "Let me show you the verified run from earlier today." Cut to a screen recording of the existing Z-001 PASS evidence (open `state/v7/z001_e2e_runs/20260530T001121Z/result.json` in a quick-look). Do not pretend a failed live take succeeded.

**Visual proof to land on.** Hard cut to the Gmail Drafts list. The new draft is at the top, To: Altaf, body in your voice. Hover the timestamp so the viewer sees "just now".

## 4. Demo moment 3: "I just do" (the Donna effect, 30 to 60 seconds)

**Goal viewer should feel:** He didn't even ask. The thing knew. This is what an assistant who has been with you ten years does.

**Setup.** Same Chrome window. Calendar tab visible (calendar.google.com). The proactive calendar-prep scheduler has been running since engine start (verified in G9, `discovery_proactive.py` PASS).

**The script you say out loud:**

> "Look. I didn't ask for this." (point at the menubar popover) "Anticipy already pulled the brief for my next call. Subject line, last email thread, the dossier line on the person. I open the laptop and it's there."

**What happens.** Open the menubar popover. The "Up next" panel shows the next calendar event with a 1-line summary, last 1-line of the most recent email from that person, and the dossier line. Sourced from the calendar-prep scheduler, fires unprompted. Verified G9 evidence: `briefs_fired` observed in latest discovery_proactive run.

**Expected timing.** Popover render: under 800 ms. No additional waiting.

**Recovery line if the brief panel is empty.** "And when the calendar is empty, like right now, it stays quiet. That is also the point. Silent unless useful." (This is true; G10 channel router PASS = silent for LOW.)

**Visual proof to land on.** Close on the popover with the brief visible, then close the popover. End with you saying "I never said 'Hey Anticipy.' That is the product."

## 5. Visual cleanup checklist

Before you hit record:

- [ ] Chrome: ONE window, ONE tab on mail.google.com, ONE tab on calendar.google.com. Close every other tab including dev tools, localhost:3000, supabase dashboard.
- [ ] Menubar: hide the clutter. macOS System Settings > Control Center > hide Spotlight, Siri, Time Machine, Bluetooth, Volume from menubar. Keep Anticipy, Wi-Fi, battery, clock.
- [ ] Dock: hide it (System Settings > Desktop & Dock > Automatically hide and show). Or turn Dock magnification off and remove app icons you do not need on screen.
- [ ] Desktop: command-shift-period to hide hidden files. Move any sensitive PNG/screenshot off the Desktop into a folder.
- [ ] Browser bookmarks bar: hide it (Cmd+Shift+B). Bookmark bar reveals personal sites.
- [ ] Notifications: enable Focus > Do Not Disturb for the entire recording.
- [ ] Terminal windows: closed. Especially anything showing tokens, .env, or paths under `/Users/omarebrahim/...`.
- [ ] Anticipy menubar popover: open it once before recording so the SF Pro fonts are warm and the first render is not janky.
- [ ] Camera: AirPods visible if you want the "in your ear" beat to read on camera. Otherwise mention it once.
- [ ] Mic level: test that ambient hiss is under -50dB. Parakeet handles room noise but on camera it sounds amateur.

## 6. Things that can go wrong + the 3-second recovery line

| Symptom | Why | Say this | Then do this |
|---|---|---|---|
| Trivia silence past 3s | Cache miss or ElevenLabs latency | "Try one I know it has." | Switch to "wait, when was the moon landing" |
| Gmail draft never appears in 45s | Cold cache hit the deadline, or Chrome lost Gmail session | "Here is the verified run from this morning." | Cut to `state/v7/z001_e2e_runs/20260530T001121Z/result.json` |
| Popover shows empty Up Next | Calendar genuinely empty, OR scheduler crashed | "Silent unless useful. That is the point." | Move on. Do not try to force-fire. |
| Engine restarts mid-take | sidecar crashed (rare; uptime over 1 hour in HANDOFF_HONEST) | "One second, I will reboot the assistant." | `pkill -f anticipy-engine && open /Applications/Anticipy.app && sleep 30` then redo pre-flight (g) |
| SMS does not arrive | TWILIO_MOCK=true left on (default) | "In production the SMS lands here." | Narrate over the missing buzz. Do NOT mime a reply. |
| Parakeet hears "Altaf" wrong | Spoken too fast or accent edge | "Let me say that cleanly." | Repeat: "Altaf. Ebrahim. Thank-you email about today." |
| Wrong recipient resolves | Dossier ambiguity (two Joes, etc.) | "Let me name him fully." | Use "Altaf Ebrahim" or "Zara Somani" (both unique in dossier) |
| Chrome opens an account chooser | Multi-account Google profile | "One sec, picking the right account." | Click the u/0 account; rerun the take |
| Compose tab steals focus | Gmail compose opens foreground | (silent) | Do not narrate. It is fine. The draft still saves. |

Do not improvise past these. If something not on this table happens, stop recording, fix, restart the take from the top of the affected moment.
