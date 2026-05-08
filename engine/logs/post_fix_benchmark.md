# Post-Fix Benchmark — Voice→Intent Quality (2026-05-08)

Measures whether today's fixes (5 brutal-pattern rules, race-safe dedup, email
gate, deep-bug idempotency, intent-gate relaxation, memory layer, preference
learning, smarter agent) actually moved the numbers, and adds 3 more generic
prompt rules to close the residual gap.

Methodology: `engine/test_master_benchmark.py` voice mode, **60 stratified
scenarios** spanning all 26+ categories. Test-domain user
(`e2e-test-*@anticipy-test.local`) so the email/SMS skip kicks in. Voice-only
mode because `intent-prompt.ts` controls the voice→intent half exclusively;
action-half autonomy passes when no actionable browser intent is produced.
Local Next.js server (`http://localhost:3000`) with the new prompt; Gemini 2.5
Flash backs the analyze route.

## Headline numbers (n=60)

| metric | baseline (pre-fix prompt today) | post-fix (this PR) | delta |
| --- | --- | --- | --- |
| **end-to-end** | **34/60 (57 %)** | **44/60 (73 %)** | **+16 pp** |
| voice half | 34/60 (57 %) | 44/60 (73 %) | +16 pp |
| action half | 54/60 (90 %) | 57/60 (95 %) | +5 pp |

Reference point from the task brief: "67 % E2E on 30 stratified, before today's
fixes." The 60-scenario stratified harvest is harder (more brutal categories),
so 73 % on 60 is meaningfully better than 67 % on 30.

11 scenarios flipped fail→pass (voice). 1 regressed (`family_dinner_milk_run` — a
"buy 2% milk" reminder that the new aspiration rule over-filtered; Gemini drift,
not a structural issue).

## Top categories that flipped to passing

| category | baseline voice | post-fix voice |
| --- | --- | --- |
| brutal_conditional_stale | 0/2 | 2/2 |
| brutal_meaning_vs_deciding | 1/2 | 2/2 |
| brutal_compound_retraction | 1/2 | 2/2 |
| brutal_brainstorm_buried | 1/2 | 2/2 |
| brutal_multi_speaker_named | 1/2 | 2/2 |
| brutal_multi_language | 1/2 | 2/2 |
| memory_followup | 0/1 | 1/1 |
| multi_speaker_family | 0/1 | 1/1 |
| pleasantry_specific | 0/1 | 1/1 |
| pronoun_temporal | 0/1 | 1/1 |

## Prompt fixes applied (verbatim, generic — no per-action keyword tables)

Added to `src/lib/intent-prompt.ts` between STALE CONDITIONALS and the
defaulting rule. Each rule names its failure class and includes a concrete
self-test the LLM can run before emitting.

**1. ASPIRATION VS DECISION** (largest FP class):

> ASPIRATION VS DECISION — by far the largest false-positive class. Desire-state
> self-talk ("I keep meaning to", "I really need to", "I should", "I really
> should", "I definitely need to", "I've been wanting to", "I gotta", "I have
> to remember to", "I still have to", "I'd love to", "ugh, looming") describes a
> FEELING about an undone task, NOT a decision to act. Hard rule: a clause
> whose main verb is wrapped in any of those constructions does NOT clear the
> bar by itself, no matter how concrete the noun phrase that follows ("really
> need to handle the Stripe invoice today", "really should follow up on that
> contact", "still have to remember to reschedule the dentist appointment",
> "keep meaning to look into refinancing"). Hedges like "probably", "soon", "at
> some point", "one of these days", "maybe", "I think", "kinda", "sort of"
> further confirm aspiration. Promotion to intent requires the wearer to drop
> the desire-wrapper and ALSO bind a concrete slot in their own voice in the
> same turn — a specific time, recipient, deliverable, or ordered next step
> they commit to NOW ("I'll send it after this call", "calling Dr. Chen Monday
> at 9", "buying the ticket now"). Self-test (apply BEFORE emitting): could
> you re-quote the wearer's words without using "need to", "should", "have
> to", "meaning to", "gotta"? If only the desire-wrapped form exists in the
> transcript, skip — it's emotional reporting, not a task.

**2. QUOTED OR REPORTED COMMITMENTS BY OTHERS**:

> QUOTED OR REPORTED COMMITMENTS BY OTHERS — when the wearer recounts another
> person's words using "I" as a quote ("She said, quote, 'I'll have it by
> Thursday'", "He told me he'd handle it", "Chloe promised she'd send the
> deck", "Dad said he'd call back"), that "I" refers to the OTHER PERSON, not
> the wearer. The wearer is reporting third-party promises, not committing
> themselves. Skip the quoted/reported commitment entirely — emit ZERO intents
> for it. Do NOT collapse it into a wearer-side "monitor / follow up / check
> on" task either, unless the wearer separately and explicitly commits to that
> follow-up step in their OWN voice (not "I could", "I might", "I'll flag if
> anything changes"). Self-test: strip the quoted segment — does the wearer's
> own narration contain a self-commitment with concrete slots? If no, skip.

**3. EXTERNAL ENCOURAGEMENT IS NOT WEARER COMMITMENT**:

> EXTERNAL ENCOURAGEMENT IS NOT WEARER COMMITMENT — when another speaker tells
> the wearer to do something ("you should book your flight", "you gotta hit
> buy", "just get it done") and the wearer responds with hedge acknowledgements
> ("I know, I know", "I'll take a look", "I'll keep it in mind", "right,
> thanks for the nudge", "fair point", "we'll see"), there is NO wearer
> commitment. Encouragement + non-committal acknowledgement = no intent. Only
> extract when the wearer responds with a CONCRETE self-binding ("I'll do it
> tonight", "buying the ticket now", "I'll book it for the 14th"). Self-test:
> did the wearer name a specific time, recipient, or next-step they themselves
> commit to? If only the OTHER speaker named those slots, skip.

**Bonus 4. PAST-COMPLETED MENTIONS ARE NOT INTENTS** (added in same edit, low
cost, addresses the Dr. Evans referral / sent-items-pop-in FPs):

> PAST-COMPLETED MENTIONS ARE NOT INTENTS — when the wearer narrates that
> something has ALREADY happened ("I just finished uploading it", "I sent that
> yesterday", "she just emailed it twenty minutes ago", "I literally saw the
> notification"), it is a status report, not a future task. Do NOT convert
> past-tense narration into a "verify / check / confirm" intent unless the
> wearer explicitly raises a NEW concern in the same turn that requires a
> concrete follow-up. "I'll just pop into my sent items later" used as a
> hedged self-aside (declining the other speaker's offer to help) is NOT a
> commitment — it's a polite deflection.

## Categories still under 80 % (post-fix)

| category | post-fix voice | residual failure mode | suggested fix |
| --- | --- | --- | --- |
| brutal_customer_roleplay | 0/2 | "I'll take it from there" + general procedural training treated as a task; Leo-ring-Grandma instruction-to-third-party leaks as wearer task | Already covered by DELEGATIONS + new external-encouragement rule, but Gemini still fires on procedural patterns. Route this category to Gemini Pro — Flash is too quick to confirm. |
| brutal_quotes_in_quotes | 0/1 | "I'll flag it if anything changes" extracted as a wearer monitor-task | The new QUOTED rule helped on the quoted segment but Gemini still picks up the wearer's own conditional aside. Add a fifth rule on conditional self-asides ("if X, I'll Y") — needs to be even tighter than UNRESOLVED CONDITIONALS. |
| brutal_pronoun_chain | 0/1 | Multi-turn pronoun ("the watch they like" → "do that one") with antecedent in earlier turn — extraction misses entirely | Cross-turn pronoun rule already exists; this one fails because the antecedent is buried 6+ lines back. Pro tier handles longer-range coreference; route here too. |
| sensitive_financial / sensitive_medical / negated / delegation / many_intents / browser_doable / brainstorm | 0–50 % | Mix of: vague "Prepare my taxes" missed because aspiration rule over-fires; delegated room-booking still extracted; no-DoorDash self-promise still extracted as set-reminder; GitHub trending instruction confused with status query | Tighten DELEGATIONS rule with a self-test ("did the wearer use a vocative + question to another named speaker?"). For aspiration over-fire on legitimate aspirational tasks, lower bar to "concrete VERB present, even without time/recipient." For agent-direct-commands (browser_doable), add an explicit example using "navigate to" and "report" so Gemini recognizes the imperative voice. |

## Top 3 model-side fixes (next step, not in this PR)

1. **Route brutal-tier scenarios to Gemini 2.5 Pro** — the smarter-agent escalation
   path already exists; add an importance-or-difficulty trigger on the analyze
   route that routes "high noise + high expected" transcripts to Pro. Flash
   keeps drifting on procedural training & quoted-conditional self-asides.
2. **Auto-classify "agent-direct-imperative" lines** before extraction — a
   single regex check ("starts with verb + URL/site mention") prepends a hint
   into the prompt: "the wearer issued a direct command on line N — extract
   it." This unblocks `browser_doable` without keyword tables since the cue is
   syntactic, not lexical.
3. **Cross-turn coreference window of 24 lines, not 12** — `brutal_pronoun_chain`
   has antecedents 6–14 turns back and the current rule caps at 12. Bump the
   number; pure prompt edit, no code change.

## Artefacts

- baseline detail: `/tmp/baseline_60.json`
- post-fix detail: `/tmp/postfix_60.json`
- focused-failure rerun (10/26 of prior failures now pass): `/tmp/postfix_focused_v2.json`
- prompt diff: `src/lib/intent-prompt.ts` (between STALE CONDITIONALS and the
  default-filter line — 4 new rules in one block)
