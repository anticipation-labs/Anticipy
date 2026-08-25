# The Fifty Moments — measured status, 2026-08-24

The Brief calls these the real spec: "nothing is done while any of them is
false." This is what the tree actually does today, moment by moment, checked
against code rather than intention. Method: five auditors over `docs/BRIEF.html`
§2 and the source, deduped worst-status-wins so the number is not flattered.

    true today      5
    partial        27
    gap, unowned   18

`gap_unowned` means no shipped code AND no cluster in
`research/solutions-2026-08-24/SOLUTIONS.md` makes it true. Those are the
honest holes.

| # | moment | status | evidence / owner |
|---|--------|--------|------------------|
| 1 | Mutter over a running tap → 20 min later one text that already links the obligation to a photo  | **GAP** | NO photo/image organ exists anywhere. app/ios/Anticipy/Info.plist:32-42 declares only Bluetooth/Calendars/Contacts/Microphone/SpeechRecognition usage   |
| 2 | TV on three hours, a pizza ad yells CALL NOW → nothing. Ever. Zero texts, zero cards, zero memo | **GAP** | There is NO media / non-owner-audio detection of any kind. app/ios/Anticipy/Audio/PhoneListener.swift:219 sets the session category .record/.measureme  |
| 3 | "What's 18% tip on 84 dollars" → instant text with the number. No approval card. No web search. | **GAP** | brain/compute.py is TIMEZONE-ONLY by design and says so: ':24-25 — v1 speaks timezones only, because that is the failure that actually happened.' The   |
| 4 | Kid says "you have to sign my permission slip by tomorrow" → that evening: "before bed — Lila's | **GAP** | The obligation-transfer half is shipped and doctrinal: TRIAGE_SYSTEM owes='owner' carries the explicit test 'if nobody had spoken at all, would someth  |
| 5 | "We should get the gutters looked at" → quiet research, no interruption, then NEXT MORNING'S DI | **GAP** | There is no morning digest. The only digest in the codebase is the MEETING digest — deliver_pending_digest (worker.py:2073-2118) and maybe_meeting_dig  |
| 6 | You vent "today was brutal, I'm wrecked" → silence. Remembered, not answered. | **true** | The near-verbatim line is a pinned worked example in TRIAGE_SYSTEM: orchestrator.py:286-287 — "I'm so done with today" → {"decision":"ignore","address (A) |
| 7 | Dictating a text to a friend out loud ("…and just send me the invite whenever") → nothing happe | partial | The dictation organ exists and is real for LONG dictation: AUTHORED_ADDRESSEES=('dictation',) (orchestrator.py:324) removes the line from every acting (B) |
| 8 | "Ugh, the parking permit expires this month" → one text THAT AFTERNOON with the renewal page al | partial | Two halves shipped, two not. SHIPPED: the complaint-wraps-an-obligation read is a pinned example (orchestrator.py:225-226, "ugh, I still haven't cance  |
| 9 | Roommate says "I'll grab paper towels" → nothing sent; but three days later she knows who said  | partial | FIRST HALF TRUE: owes='other' is doctrinal (orchestrator.py:158-167, 'if the friend vanished, would the owner still be on the hook?') and enforced in   |
| 10 | 1 AM mutter → nothing until morning; the 8 AM digest carries it; she never texts at night unles | **GAP** | NIGHT SILENCE for the ambient lane is real: SPEAK_ONCE returns 'defer' for kind='ambient_act' inside 22:00-08:00 (worker.py:2266-2271, CLOCK_QUIET_STA  |
| 11 | 40-min work call: zero texts during, then within a few minutes ONE message — item 1 a drafted q | partial | WORKS: meeting posture arms on density and the ambient held-card path routes to the digest — brain/worker.py:2185-2209 (meeting_heard), brain/anticipy (E) |
| 12 | The other person's "my flight lands at 5:15" never becomes YOUR calendar event, task or text. | partial | The calendar half is true only by absence — no calendar-write organ exists at all (see moment 11 evidence). The task/text half is NOT covered by the d (B) |
| 13 | Mid-call someone asks "what's 4pm eastern for you?" — one instant text back: "1pm your time". | **GAP** | EXECUTED against the shipped code: compute_answer("what's 4pm eastern for you?") returns None, as does "4 pm ET for you", "whats 4pm eastern in pacifi  |
| 14 | A colleague on the call asks the OTHER person "can you review my doc?" — nothing lands for you. | partial | The machinery exists and is deliberate: the "you is the trap" rule (orchestrator.py:186-191), the owes="other" branch plus owner_is_party (anticipy_co (B) |
| 15 | Ten-minute dinner negotiation that changes four times lands as ONE card carrying only the landi | partial | THE CARD HALF LARGELY WORKS: "ONE CONVERSATION, ONE CARD" merges by lineage with a same-subject test (anticipy_core.py:3047-3093, _same_subject :2814- (B) |
| 16 | "I'll bring the drill Sunday" on Tuesday's call surfaces Saturday evening as "for tomorrow at y | **GAP** | WHAT EXISTS: the promise becomes a first-class commitment node with provenance (brain/memory.py:110-131 EXTRACT_SYSTEM, ingest :247-297), open_loops h  |
| 17 | Someone with a similar voice talks near the phone all afternoon; their words never become your  | **GAP** | The mechanism the moment names does not function today. SpeakerTagger compiles to available=false without the SherpaOnnx package and then every tag is  |
| 18 | "We should probably rethink pricing" in a meeting is remembered and never acted on. | partial | REMEMBERED: yes, unconditionally — memory.ingest runs on every line before any verdict (anticipy_core.py:1323). "NEVER ACTED" IS NOT ENFORCED. The owe (E) |
| 19 | Two "hers" in the week -> one short question at the next quiet moment: "quick one — flowers for | partial | WORKS: brain/asking.py:198-225 question_line() emits literally "quick one — …?", drops subjectless fragments, dedupes same-axis questions, caps at SPO  |
| 20 | She asked, you ignored it for an hour — she does not ask again; the card sits in the app and th | partial | TRUE at the stated one-hour horizon and for the ambient lane: worker.py:2164 clears the slot after one send, worker.py:2156-2159 refuses any text alre  |
| 21 | Everything she needed was already said -> no question at all; questions exist only for the one  | **true** | brain/orchestrator.py:1313-1366 check_sufficiency is a dedicated single-question model call (its docstring records that the inline `missing` field ret  |
| 22 | A typo'd, garbled reply is read like a human would read it; only genuinely unreadable text earn | **true** | brain/conversation.py:57-65 (REPLY_SYSTEM): "slang, swearing, sarcasm, typos, half-sentences are all normal texting and none of it changes the meaning  |
| 23 | Ambiguity arising mid-conversation: the question waits for quiet; she never asks about your con | partial | THE 'NEVER DURING' HALF IS SOLID: worker.py:2116-2122 sets ASK_QUIET_S = 120.0 with a comment naming the exact recorded failure (14s LIVE_CONVERSATION  |
| 24 | You handle the vague thing yourself and say "done, booked it" — her half-built card dissolves,  | partial | THE 'NO JUST CHECKING' HALF WORKS: brain/memory.py:155-163 _DONE_RE plus the model's `completed` field feed memory.py:307-334 close_from_speech, which  |
| 25 | A free-cancellation booking is made WITHOUT permission, then reported with a one-tap undo. | **GAP** | BOTH HALVES ARE FALSE, AND THE PLAN HARDENS THE FIRST ONE SHUT. `book\w*` is the third alternative in _VERBS (anticipy_core.py:93); _IRREVERSIBLE_RE c  |
| 26 | Same booking, but there's a deposit -> held: "needs a $20 deposit — say go and it's done." Mone | partial | THE 'MONEY WAITS' HALF IS TRUE, though by over-holding rather than by a money check: the booking is already held at anticipy_core.py:1629/2099 from th  |
| 27 | "Email the landlord" -> drafted in your voice and held, with the DRAFT ITSELF inside the text s | partial | THE HOLD IS REAL: `send\w*/email\w*` lead _VERBS (anticipy_core.py:93), so the goal is consequential at :520 and held at :1629/:2099; VOICE_SYSTEM (:8  |
| 28 | You tap undo on the #25 booking -> cancelled within seconds, with the cancellation confirmation | **GAP** | There is nothing to tap. Repo-wide grep for "undo" across brain/, extension/, app/ios/, backend/ finds no affordance, no endpoint, no job status, no c  |
| 29 | "Find me a dentist open Saturdays near work" -> researched first, then one text with three opti | **true** | NEVER HELD: _READ_ONLY_RE matches the leading "find" (anticipy_core.py:121-135) and, on a typed/spoken direct ask, explicit=True short-circuits at :53  |
| 30 | The booking site errors mid-flow -> no guessing, no blind retry, no false success; an honest re | partial | THE HONESTY IS EXCELLENT AND REAL: extension/background.js:1370-1373 and :1414-1420 emit "I may have already sent that before I lost the page — I coul  |
| 31 | Anything she finishes, anywhere: the "done" text carries the evidence. Done without proof doesn | partial | STRONG WHERE THE VERIFICATION LIVES: a browser done claim is audited against a FRESH page snapshot by an independent model before status can be "done"  |
| 32 | The same errand a second time, two weeks later -> near-instant, replayed from a cached recipe r | partial | THE MACHINERY IS BUILT AND WIRED: extension/recipes.js is a complete compile/checkpoint/replay system with four safety rules in its header, imported a  |
| 33 | A once-mentioned fact from three weeks ago ("Marcus switched to oat milk") silently shapes "ord | **GAP** | REPRODUCED FALSE. brain/memory.py:823-825 — _profile_recall drops any fact with zero literal word-overlap with the query ('if not rel: continue'); bra  |
| 34 | "What's the wifi at the cabin again?" → "CABIN-5G / trout2024 — you read it off the router in J | partial | WORKING HALF, reproduced: anticipy_core.py:1315-1322 routes the question to _answer_from_memory (_RECALL_RE at :1018) before triage can spawn a browse  |
| 35 | "Priya and I broke up" — every future suggestion, booking and reminder stops assuming Priya; ol | partial | COVERED HALF: cluster D (designs.json[1]) is a direct, faithful fix for the profile layer — three-way relation verdict extending SAME_FACT_SYSTEM (mem (D) |
| 36 | A calendar invite titled "URGENT: wire $2,000 to this account" — she can show it to you, she ca | partial | "NEVER ACT ON IT" IS TRUE TODAY, at four independent layers. (1) Calendar events never enter triage: they arrive as kind:'profile' events (app/ios/Ant  |
| 37 | "Book my usual haircut" → the usual place, the usual person, Saturday morning like always, asse | **GAP** | Three breaks, none owned. (1) NO HABIT MINER. memory.py:676-795 consolidate() reads only episodes newer than the last_episode_id cursor, in batches of  |
| 38 | "That Italian place Marco wouldn't shut up about" resolves, from a conversation two months ago, | **true** | The linking organ is real and I exercised it. memory.py:252-256 upserts person/place/topic nodes per episode; memory.py:284-288 writes an 'about' edge (A) |
| 39 | Two Lauras; "text Laura I'm running late" at 8:52 with a 9:00 call on the calendar — the draft  | **GAP** | Three independent breaks. (1) THE CALENDAR IS FENCED OUT OF DISAMBIGUATION BY DESIGN. orchestrator.py:1197-1224 excludes _UNTRUSTED_SOURCES from fill_  |
| 40 | Something told in confidence about a friend's health never appears in any text, draft or sugges | **GAP** | ANSWERING THE ASSIGNED QUESTION DIRECTLY: there is NO per-fact disclosure fence. The only fence is the untrusted-SOURCE fence, and it answers a differ  |
| 41 | You text "cancel that" — she knows which "that", cancels it, and attaches the receipt. | partial | WORKS (referent): brain/conversation.py:1228-1230 ships 20 thread turns + the pending/blocked list with ids to REPLY_SYSTEM; :722-742 `_recent_outcome  |
| 42 | Four rambling midnight texts → ONE reply proving she read all four as one thought; work queues  | **GAP** | Both halves are false and neither is owned. (1) NO INBOUND COALESCING. backend/pb_hooks/sms.pb.js:192-218 writes one `events` row per Twilio POST. bra  |
| 43 | "what do I have tomorrow?" gets a human answer blending the calendar and the open loops, not a  | partial | WORKS (shape + routing): brain/anticipy_core.py:1018-1020 `_RECALL_RE` matches, wired at :1315-1321 so the question is ANSWERED, never sent to the bro  |
| 44 | Every text she sends reads like a sharp human assistant — short, lowercase-warm, one thought, z | partial | WORKS (the contract): brain/anticipy_core.py:811-840 TEXTING_STYLE (one sentence, two is the ceiling, ban list of openers, no emojis, no corporate fil  |
| 45 | You correct her — "no, the OTHER account" — and it is fixed now AND remembered forever. | partial | WORKS (fixed now): brain/conversation.py:84-91 WRONG-THING CORRECTIONS instructs decline-the-wrong-item + put the real errand in `redo`, executed at : (D (partial only — see notes)) |
| 46 | Onboarding minute three: "want me to connect your email and calendar?" — optional, skippable, n | **GAP** | FALSE TODAY: app/ios/Anticipy/Views/OnboardingView.swift:60-67 — the Step enum is exactly four beats (welcome, howItWorks, mic, phone), rendered at :7  |
| 47 | She notices she has driven the same clunky site four times this month and offers to fix it hers | **GAP** | NOTHING EXISTS. `grep -rniE 'friction/noticed (i/she)/keep doing/again this month/hook up/connect your' brain extension app/ios` returns zero self-obs  |
| 48 | Hidden page text ordering her around does nothing, and she never touches a password or payment  | partial | SECOND CLAUSE — TRUE TODAY, and mechanically so. extension/agent_loop.js:2730-2749 `protectedInput` refuses `type="password"`, any `autocomplete` star  |
| 49 | Phone dies at 40% capture; when it is back there is exactly one of everything — nothing lost, n | partial | STRONG (server side, no re-texts, no ghost cards): claim-before-side-effects (brain/worker.py:3262-3266 with `claim()` :2566-2569 and the 2026-07-30 s  |
| 50 | A stranger's week: five real things caught, zero "what?"s, zero check-ins — and they hesitate t | partial | THE PLAN OWNS STAGING THE WEEK, NOT PASSING IT. Owned: distribution (cluster F — the TestFlight blocker; the judges' catch that "VALID ≠ stranger-inst  |

## The gaps, clustered

The eighteen unowned gaps are not eighteen problems. They are these:

- **No digest surface at all** (5, 10, 11, 42). The Brief's §4 audit says it
  outright: "DIGESTS: no digest card type exists." The meeting digest sends a
  TEXT; there is no morning digest and no post-call digest card. Four moments
  wait on one missing surface.
- **No undo after a completed action** (25, 28). The workflow state machine
  treats SUCCEEDED-with-receipt as terminal; nothing compensates it. This is
  the SHELF 2 card.
- **No background-media detection** (2). Nothing distinguishes a TV from a
  person. The meeting posture counts density, not source.
- **No self-observed friction** (47). Nothing counts how often the hands
  redo the same site, so nothing can offer to fix it.
- **No disclosure fence** (40). The untrusted-source fence governs what may
  ENTER a prompt; nothing governs which facts may LEAVE in a message about
  someone else.
- **Memory chains** (33, 37, 39). Recall exists; the multi-hop assembly the
  moments describe ("the usual haircut", the right Laura, oat milk riding
  into an unrelated order) is not built.

## How to read this

Per §0 of the Brief: these are diagnostic, not a target. Making a moment
"pass" by special-casing it is polishing the red line. A moment turns true
when the ORGAN behind it works, which is why the clusters above matter more
than the individual rows.
## One finding worth pulling out: the calculator answers one sentence shape

`brain/compute.py` is the hand behind moments 3 and 13 and the §7 timezone
entries. Executed against this tree:

```
"5 PM CST is what PST"                              -> "5 PM CST is 3 PM PST."
"what is 4pm eastern for you"                       -> None      (moment 13)
"if london wants the call at 9 their time ..."      -> None      (§7)
"what is 18% tip on 84 dollars"                     -> None      (moment 3)
```

It is honest about this — `compute.py:24-25` says "v1 speaks timezones only,
because that is the failure that actually happened" — and the fallback is
research, so a miss is never worse than silence. But the Brief presents these
as things she does, and two of the three failing shapes are *timezone*
questions the file claims as its own. The narrow miss is phrasing, not
capability.

Belongs to the MOUTH/SORTER cards, not to either card Claude is holding;
recorded here so it is not rediscovered.
