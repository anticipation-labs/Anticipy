# The Tejas call — the product's first real paired eval

2026-08-23, ~6:02–6:30 PM PDT. Omar on Google Meet (MacBook Air speakers at
100%), iPhone running build 75 less than 1 cm away. We hold BOTH sides:
Omar's verbatim ground-truth transcript of the call, and every event the
system produced. Nothing else the product owns can say "here is what was
said, and here is what she did about it."

## Measured

- **~33% of words captured** (1,271 of ~3,900). 137 transcript lines.
- **54% of captured lines are ≤4-word shards** ("New Jersey" = "Gen Z";
  "Into this new"; "Then be now").
- **speaker is empty on all 137** — the far-end voice through the laptop
  speakers is merged into Omar's stream with no attribution.
- **spoken_at is empty on all 260 events of the day** — the capture-time
  architecture (CAPTURE-ARCHITECTURE.md) is designed and unbuilt. This
  misled even the analyst before it misled the brain.
- Decisions on the call: 131 ignore, **6 act**. Zero ask.

## The six acts, each with its defect

1. **"anticipate.com" domain purchase** — ASR mangled "anticipy growth …
   dot com" and she proposed buying a mis-spelling of HER OWN PRODUCT'S
   NAME. No cross-check against the one proper noun the system should
   know best.
2. **"confirm who 'him' refers to"** — 'him' was the CMO, named seconds
   earlier; and the sentence was Omar talking TO Tejas, not tasking her.
3. **Tuesday call** — broadly correct, the one defensible act.
4. **"Convert 5 PM CST to PST" → a HELD job** — a pure computation put
   behind the confirmation gate ("i'm holding the 5 pm cst conversion to
   pst"), and the answer sent was a converter-page summary with a 6 AM
   example instead of the number: **3 PM**.
5. **"What was your email again"** — Omar asking TEJAS for Tejas's email.
   She retrieved OMAR's own address and asked him to confirm it.
6. **"At 5:15" → "meeting with Dr. Evans, Monday 5:15 PM"** — a 3-word
   shard of TEJAS saying when HIS OWN meeting ends, turned into a meeting
   for Omar with a person who does not exist anywhere in the call.

## The unifying diagnosis

Four of the six bad acts are the same failure: **the system does not know
Omar is in a two-way conversation.** The triage prompt has the rule —
"questions aimed at other people: ignore" — but with no speaker
attribution and 54% shards, the model cannot apply it. Capture quality is
upstream of decision quality; no prompt fixes it.

## The spam channel, separately

Unsolicited check-ins fired the same evening ("grab drinks idea from
yesterday", "the Amy deal" — which then triggered research into a TV
contestant named Amy McCoy). Omar's replies were "What" and "Yes what is
that" — the direct trust cost, in his own words, in the log.

## Also on file

Three ownerless owner_profile rows still share Omar's phone number in
production — the inbound-SMS routing hazard Jose's hook now refuses to
create but does not clean up.
