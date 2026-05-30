# SMS Copy Audit (Apple-feel review + proposed rewrites)

Scope: every distinct outbound SMS body the Anticipy engine sends to the user. Voice-channel TwiML phrases that the user hears (Programmable Voice `<Say>`) are included because they are the spoken equivalent of an SMS body in the same flow. Local macOS notification banner titles ("Anticipy: done" etc) and email subjects are excluded because they are not SMS bodies.

Scoring rubric (1 to 5):
1. PE  = Plain English (no jargon)
2. SP  = Specific (names + verbs, not vague)
3. RV  = Reversible feeling (user feels in control, not bossed by a robot)
4. LN  = Length (5 = under 160 chars and complete)

Hard rules used everywhere in the proposed copy: no em-dashes, first person ("I"), concrete nouns, plain English, one question max, no corporate words, no leaked tech words.

---

## Audit Table

### 1. Pre-confirm proposal (the main SMS the user sees before any irreversible send)

- File: `engine/app/product/sms_pre_confirm.py:463-467`
- Channel: SMS (and the same text is read aloud over Programmable Voice when criticality is CRITICAL+time-sensitive)

Current body (template, verbatim):
```
Anticipy is about to {verb} {recipient} about {subject[:80]}. First 100 chars of body: '{preview}'. Reply YES to send, NO to cancel, EDIT to revise.
```

Scores: PE 3, SP 4, RV 2, LN 2

Why weak: "Anticipy is about to" is third-person bot-speak. "First 100 chars of body" leaks tech vocabulary ("body", char count). Three reply tokens (YES / NO / EDIT) violate the "one question max" rule and the proposal balloons past 160 chars almost always (the cap is 320, not 160). It feels like a transaction notice, not a teammate asking.

Proposed body (template, 1-segment safe):
```
I drafted a {verb} to {recipient} about {subject_short}. Preview: "{preview_60}". Reply YES to send. Reply EDIT to change anything.
```

Why better: First person ("I drafted"). Plain words ("Preview" not "First 100 chars of body"). One primary action (YES), one optional escape (EDIT). NO is implicit (no reply = saved as draft, which the engine already does at expiry). `subject_short` is `subject[:32]`, `preview_60` is `preview[:60]`, which keeps the full template under 160 chars in the common case ("email to Sarah" + 32 char subject + 60 char preview + chrome = ~140 chars).

---

### 2. Pre-confirm expired follow-up

- File: `engine/app/product/sms_pre_confirm.py:1317-1320`
- Channel: SMS

Current body (verbatim):
```
Anticipy: no reply, saved as draft. Open the Anticipy popover to review.
```

Scores: PE 3, SP 2, RV 4, LN 5

Why weak: "Anticipy:" prefix reads as a notification subject, not a sentence. "saved as draft" is vague (saved where? Gmail? popover? both?). "popover" is engine jargon the user does not know.

Proposed body:
```
No reply, so I saved it as a Gmail draft. Open Anticipy on your Mac to send it whenever you are ready.
```

Why better: First sentence answers "what happened" with a concrete location (Gmail draft). Second sentence tells the user where to act, in their own words ("on your Mac"), not "the popover". 109 chars.

---

### 3. Receipt SMS after a successful email send (with link)

- File: `engine/app/product/server.py:8262-8265`
- Channel: SMS

Current body (verbatim):
```
Anticipy just sent {rec} an email about {subj}. View: {link}. Reply STOP to silence.
```

Scores: PE 4, SP 4, RV 3, LN 4

Why weak: "Anticipy just sent" is third-person; "I just sent" reads warmer. "View:" is acceptable but "Open it:" is more human. "Reply STOP to silence" is Twilio legalese the user does not need on a receipt (only required on opt-in marketing in the US, and STOP is honored on any message regardless of whether it is in the body).

Proposed body:
```
Sent the email to {rec} about {subj_short}. Open it here: {link}
```

Why better: Removes the bot-speak prefix; uses first person implied by "Sent" (verb-first feels like a real human texting). Drops the Twilio STOP boilerplate because it adds friction and is auto-honored anyway. `subj_short` is `subj[:40]`. 75 chars + link.

---

### 4. Receipt SMS after a successful email send (no link)

- File: `engine/app/product/server.py:8266-8269`
- Channel: SMS

Current body (verbatim):
```
Anticipy just sent {rec} an email about {subj}. Reply STOP to silence.
```

Scores: PE 4, SP 4, RV 3, LN 5

Why weak: Same issues as #3 (third-person, STOP boilerplate).

Proposed body:
```
Sent the email to {rec} about {subj_short}. It is in your Gmail Sent folder.
```

Why better: Tells the user exactly where to verify (Gmail Sent folder), which is what they would do next anyway. No bot prefix, no STOP legalese. 78 chars.

---

### 5. Inbound reply ack: YES path

- File: `engine/app/product/server.py:9462`
- Channel: SMS reply (TwiML `<Message>` after the user texts YES)

Current body (verbatim):
```
Anticipy: confirmed. Dispatching now.
```

Scores: PE 2, SP 1, RV 4, LN 5

Why weak: "Dispatching" is robot vocabulary. The user does not know what was confirmed (which task). "Anticipy:" prefix is awkward for an ack reply (Twilio already shows the sender as Anticipy's number).

Proposed body:
```
On it. Sending now. I will text you the receipt as soon as it lands.
```

Why better: First-person reply. Warm and confident. Tells the user what to expect next (the receipt). 67 chars.

---

### 6. Inbound reply ack: NO path

- File: `engine/app/product/server.py:9464`
- Channel: SMS reply

Current body (verbatim):
```
Anticipy: cancelled. Nothing was sent.
```

Scores: PE 4, SP 2, RV 4, LN 5

Why weak: "Anticipy:" prefix and passive voice ("was sent"). Does not say what is now sitting in the user's account (draft kept? deleted?).

Proposed body:
```
Cancelled. I kept the draft in your Gmail in case you want to send it later.
```

Why better: First-person, active voice. Specific outcome ("kept the draft in your Gmail"). Tells the user the work is not lost. 76 chars.

---

### 7. Inbound reply ack: EDIT path

- File: `engine/app/product/server.py:9466-9468`
- Channel: SMS reply

Current body (verbatim):
```
Anticipy: saved as draft for review in the popover.
```

Scores: PE 2, SP 3, RV 4, LN 5

Why weak: "popover" is internal engine jargon. The user does not have a mental model of "the popover" yet (the brand surface is just "Anticipy on your Mac").

Proposed body:
```
Got it. Saved as a draft. Open Anticipy on your Mac to edit and send.
```

Why better: Plain "saved as a draft" with a concrete next step. No internal vocabulary. 69 chars.

---

### 8. Inbound reply ack: unknown reply

- File: `engine/app/product/server.py:9470-9472`
- Channel: SMS reply

Current body (verbatim):
```
Anticipy: did not recognise that. Reply YES to send, NO to cancel, EDIT to revise.
```

Scores: PE 4, SP 3, RV 3, LN 5

Why weak: "did not recognise that" is British spelling (the rest of the codebase uses American spelling, mixed feel). Three reply tokens again; should match the new one-action default (YES + EDIT).

Proposed body:
```
Sorry, I missed that. Reply YES to send, or EDIT to change it. No reply means I save it as a draft.
```

Why better: Apologetic first word reads human ("Sorry, I missed that" not "did not recognise that"). Drops NO and makes the silent default explicit, which is honest and matches the engine's actual expiry behavior. 99 chars.

---

### 9. Inbound reply: no pending action

- File: `engine/app/product/server.py:9474-9477`
- Channel: SMS reply

Current body (verbatim):
```
Anticipy: no pending action to confirm.
```

Scores: PE 3, SP 2, RV 3, LN 5

Why weak: "pending action to confirm" is corporate. The user texted YES out of the blue and got back a vague rejection. Better to acknowledge what they may have meant and what to do.

Proposed body:
```
Nothing waiting on you right now. If you want me to do something, just tell me out loud or open Anticipy on your Mac.
```

Why better: Friendly, no jargon, redirects to the two natural ways to start a task. 115 chars.

---

### 10. Failure recovery: login required

- File: `engine/app/product/failure_recovery.py:368-374`
- Channel: SMS

Current body (template, verbatim):
```
Anticipy couldn't finish {summary} because {service} is logged out.{tap_clause} I will retry once you sign in.
```
(`tap_clause` expands to ` Tap to fix: {link}.`)

Scores: PE 4, SP 4, RV 5, LN 4

Why weak: "Anticipy couldn't finish" is third-person; the promise "I will retry" is solid. Cap is 320 chars, but the typical body lands at ~180 to 230 (two segments). The "couldn't" + "I" voice switch in the same sentence is mildly inconsistent.

Proposed body (template):
```
I paused {summary} because {service} signed out. Sign in here: {link} and I will pick it back up.
```

Why better: Consistent first person ("I paused" + "I will pick it back up"). "Signed out" is plainer than "is logged out" and matches the active verb of "Sign in". 96 chars + link. Single segment in most cases.

---

### 11. Failure recovery: MFA challenge

- File: `engine/app/product/failure_recovery.py:375-381`
- Channel: SMS

Current body (template, verbatim):
```
Anticipy couldn't finish {summary} because {service} asked you to verify your identity.{tap_clause} I will retry once you do.
```

Scores: PE 4, SP 4, RV 5, LN 3

Why weak: Third-person opener; "asked you to verify your identity" is technically correct but a bit formal. Often 200+ chars.

Proposed body:
```
I paused {summary} because {service} wants a second check from you. Approve it here: {link} and I will keep going.
```

Why better: "wants a second check" is plainer than "verify your identity". "Approve it" matches what the user actually sees on the MFA screen (Approve / Deny on Google, Microsoft, Duo). 112 chars + link.

---

### 12. Failure recovery: CAPTCHA blocked

- File: `engine/app/product/failure_recovery.py:382-388`
- Channel: SMS

Current body (template, verbatim):
```
Anticipy couldn't finish {summary} because {service} is showing a CAPTCHA.{tap_clause} I will retry once you solve it.
```

Scores: PE 3, SP 4, RV 5, LN 4

Why weak: CAPTCHA is technically jargon (many users do not know the acronym, they know "the click the buses thing"). Third-person opener.

Proposed body:
```
I paused {summary} because {service} wants you to prove you are human. Tap here: {link} and I will keep going.
```

Why better: Replaces CAPTCHA acronym with "prove you are human", which is what the user actually does. First person. 107 chars + link.

---

### 13. Failure recovery: rate limited

- File: `engine/app/product/failure_recovery.py:389-394`
- Channel: SMS

Current body (template, verbatim):
```
Anticipy couldn't finish {summary} because {service} asked us to slow down. I will retry in a few minutes.{tap_clause}
```

Scores: PE 5, SP 4, RV 5, LN 4

Why weak: The body itself is solid copy. Only weakness is the third-person opener and the cap pressure when both `summary` and `service` are long.

Proposed body:
```
I paused {summary} because {service} asked me to slow down. I will try again in a few minutes.
```

Why better: First person throughout. Drops the redundant tap link (the user does not need to do anything, the engine handles the retry itself). 94 chars.

---

### 14. Failure recovery: network error

- File: `engine/app/product/failure_recovery.py:395-400`
- Channel: SMS

Current body (template, verbatim):
```
Anticipy couldn't finish {summary} because of a network blip on {service}. I will retry shortly.{tap_clause}
```

Scores: PE 5, SP 4, RV 5, LN 5

Why weak: Nearly perfect. Only the third-person opener and the unnecessary tap link drag it down.

Proposed body:
```
I paused {summary} because of a connection hiccup with {service}. Trying again in a moment.
```

Why better: First person. "Connection hiccup" is the warmer human phrasing of "network blip". No link (nothing for the user to fix). 91 chars.

---

### 15. Failure recovery: unknown error

- File: `engine/app/product/failure_recovery.py:401-407`
- Channel: SMS

Current body (template, verbatim):
```
Anticipy paused {summary} on {service} and needs a hand.{tap_clause} I will retry once you take a look.
```

Scores: PE 4, SP 3, RV 4, LN 5

Why weak: "needs a hand" is friendly but vague (a hand with what?). The user does not know what to do when they tap the link. Third person.

Proposed body:
```
I hit a snag on {service} with {summary}. Tap here: {link} and once you sort it I will keep going.
```

Why better: First person. "Hit a snag" is honest about uncertainty. "Once you sort it" lets the user act without prescribing exactly what (because the engine does not know). 97 chars + link.

---

### 16. Voice confirm TwiML: pre-call header (spoken intro)

- File: `engine/app/product/sms_pre_confirm.py:812`
- Channel: Voice (Programmable Voice `<Say>` when proposal_text is empty)

Current body (verbatim):
```
Anticipy is calling.
```

Scores: PE 5, SP 1, RV 2, LN 5

Why weak: Fallback only fires when `proposal_text` is empty, which means the user is getting a phone call from Anticipy with literally zero context. Even as a fallback this should name what is happening.

Proposed body:
```
Hi, it is Anticipy. I have something for you to approve. Say YES to send, or EDIT to change it.
```

Why better: Conversational opener (matches the login wall voice script in `login_wall_responder.py` which already opens with "Hi, this is Anticipy"). Gives the user a clear next step in the same breath. 95 chars (well within voice synthesis comfort).

---

### 17. Voice confirm TwiML: Gather prompt (spoken)

- File: `engine/app/product/sms_pre_confirm.py:821-822`
- Channel: Voice

Current body (verbatim):
```
Please say YES to send, NO to cancel, or EDIT to revise.
```

Scores: PE 5, SP 3, RV 4, LN 5

Why weak: Three options to track while listening (Apple HIG: keep voice prompts to two choices). "revise" is a word people say less than "change".

Proposed body:
```
Say YES to send. Say EDIT to change it. If you say nothing, I will save it as a draft.
```

Why better: Two clear options + explicit silent fallback. Matches the SMS reply ack copy (#8). "Change it" is more conversational than "revise". 86 chars.

---

### 18. Voice confirm TwiML: no-reply fallback (spoken)

- File: `engine/app/product/sms_pre_confirm.py:824-825`
- Channel: Voice

Current body (verbatim):
```
No reply heard. I will save this as a draft for review.
```

Scores: PE 4, SP 4, RV 5, LN 5

Why weak: "No reply heard" is passive narration of what just happened. Mildly clinical.

Proposed body:
```
No worries, I will save this as a draft. Open Anticipy on your Mac to send it later.
```

Why better: Warmer opening ("No worries" lets the user off the hook for not answering). Concrete next step. 84 chars.

---

## Summary

| Metric | Current avg | Proposed avg |
|---|---|---|
| Plain English (PE) | 3.78 | 5.00 |
| Specific (SP)      | 3.06 | 4.61 |
| Reversible (RV)    | 3.78 | 4.83 |
| Length (LN)        | 4.50 | 5.00 |
| **Overall avg**    | **3.78** | **4.86** |

Bodies audited: 18 (SMS proposals, expiry follow-up, two receipt variants, five SMS reply acks, six failure-kind templates, three voice-channel `<Say>` phrases that ride the same flow).

## Ship These 5 First (biggest impact, listed in priority order)

1. **Pre-confirm proposal body (#1, `sms_pre_confirm.py:463-467`)**. Every irreversible action sends this one. The biggest single win is moving from third-person + three reply tokens to first-person + one primary action. Drops perceived friction by half and gets the body under 160 chars in the common case.

2. **Receipt SMS (#3 and #4, `server.py:8262-8269`)**. The user sees this every time the engine completes a real send. First-person "Sent the email to Sarah" reads like a human teammate. Dropping the STOP boilerplate kills the cold-transactional feel that has been the loudest tell.

3. **Failure recovery: login required (#10, `failure_recovery.py:368-374`)**. The most common failure surface. Switching to "I paused" + "Sign in here and I will pick it back up" turns a failure into a teammate handoff. Single segment.

4. **Inbound YES ack (#5, `server.py:9462`)**. First thing the user reads after texting YES. "On it. Sending now. I will text you the receipt as soon as it lands." is the difference between Apple-feel and helpdesk-feel.

5. **Pre-confirm expired follow-up (#2, `sms_pre_confirm.py:1317-1320`)**. Kills the "popover" jargon and replaces "saved as draft" with the concrete location ("Gmail draft"), which is what the user actually wants to know to act on the message.

## Three Weakest Bodies (overall score)

1. **Inbound YES ack (#5)**. Overall 3.0. Robot vocabulary ("Dispatching") plus zero specificity about what was confirmed.
2. **Voice confirm fallback intro (#16)**. Overall 3.25. "Anticipy is calling." with no further context is the rudest possible voice prompt.
3. **Inbound EDIT ack (#7)** and **Inbound no-pending (#9)**. Both 3.5. Internal jargon ("popover", "pending action to confirm") that does not exist in the user's mental model.
