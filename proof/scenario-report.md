# Real-world scenario demos — live model + visible browser agent

Every line below went through the LIVE pipeline: overheard sentence →
DeepSeek V3.2 (OpenRouter) triage → action. Browser runs were visible
on-screen and are in the recording.

## 1. Small talk — "that ending was ridiculous"
brain: **ignore** — stayed silent. Knowing when to shut up: PASS.

## 2. Dinner — "we should grab Italian downtown this weekend"
brain: **ask** (it wants date/party size — correct for ambiguity), then the
browser agent researched anyway (action-first):

![agent on restaurant directory](/home/ubuntu/screenshots/ss_fb25f8f5.png)

Agent's own report: searched DuckDuckGo, opened eatingvancouver.ca, found
**Romano's Pizza, Straight Brooklyn Pizza, Lupo Restaurant & Vinoteca** —
real Vancouver restaurants. Would text: "Found 3 spots. Want me to check
availability and book?"

## 3. Price mention — "let me check what mystery novels go for"
brain: **ignore** ("user is browsing, no clear task") — the model judged the
user is already doing it themselves. Honest note: I expected "act" here; this
is the kind of boundary we tune with your feedback.

## 4. Pitch deck — "I'll send you the pitch deck right after this call"
brain: **act**. Draft job created and HELD:

```
job oc3sza2vocgl8dc status: awaiting_confirm | goal: draft_and_send_document
```

Nothing sends until you reply YES (by SMS through the live Twilio webhook, or
tapping "Send it" in the app) — the confirmation gate is enforced in the job
queue, outside the model.

## Verdict
Triage, action-first research, and the irreversibility gate all work live,
end to end, with the real model and a real browser.
