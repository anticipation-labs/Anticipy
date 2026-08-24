# Exemplars — what she hears, what she pulls, what she does

The triage prompt is 120 lines of rules and **zero worked examples**. The
planner runs on the cheapest model. Cheap models copy examples far better than
they follow prose, so this file is the biggest quality lever in the product.

Every entry is the same shape:

```
HEARD     the line off the pendant
AROUND    the last few lines, because they change the answer
MEMORY    what surfaced from what she already knows
→         ignore | ask | act | answer
GOAL      the machine goal string, when it's "act"
WHY       one sentence
TRAP      what a cheap model gets wrong here, and why
```

**AROUND and MEMORY are not decoration.** They are the whole difference between
a good call and an embarrassing one, and about half the entries here flip
depending on them. That is the point of the file.

Everything is remembered regardless of the decision. `ignore` means *no action*,
never *no memory*.

---

## 1. A promise made to nobody

The core case. Someone says a thing they have to do, out loud, to no one.

```
HEARD     "ugh, I still haven't cancelled that free trial"
AROUND    —
MEMORY    —
→         act
GOAL      "cancel the free trial he mentioned — find which one, open the cancel page"
WHY       An obligation he stated. That it's his and unaddressed is the reason to
          get involved, not a reason to stay out.
TRAP      Reads as venting because of "ugh". The complaint is the wrapper; the
          task is inside it.
```

```
HEARD     "I've gotta call the dentist back"
AROUND    —
MEMORY    —
→         act
GOAL      "find the dentist's number and hours, ready for him to call"
WHY       A real errand, voiced the way people actually voice errands.
TRAP      "I've gotta" sounds like thinking aloud. It isn't. This exact shape —
          "I have to / I've gotta / I still need to" — is the single most
          common way a genuine task arrives.
```

```
HEARD     "I should really email Priya about the invoice"
AROUND    —
MEMORY    Priya Shah — invoices, Devon project
→         act
GOAL      "draft an email to Priya Shah about the outstanding invoice"
WHY       Named person, named subject, stated obligation.
TRAP      "should really" reads as hypothetical. With a proper noun attached it
          is not.
```

```
HEARD     "I keep forgetting to book the car in"
AROUND    —
MEMORY    —
→         ask
GOAL      —
WHY       Real task, one blocking unknown: which garage, or when.
ASK       "Which garage do you use?"
TRAP      Acting here means inventing a garage. One missing fact is exactly what
          "ask" is for — but only ONE. If you'd need two, ask the more useful.
```

---

## 2. Things that sound like tasks and are not

```
HEARD     "my back is killing me"
AROUND    —
MEMORY    —
→         ignore
WHY       A complaint about a state, not an intention.
TRAP      Cheap models book physiotherapy. There is no plan here, no anchor, no
          verb of intent.
```

```
HEARD     "I should just quit and move to Bali"
AROUND    laughter in the room
MEMORY    —
→         ignore
WHY       A joke. Nobody is moving to Bali.
TRAP      It has a place and an action, which looks like an anchored plan. Tone
          and the surrounding laughter are the signal.
```

```
HEARD     "we really need to fix the onboarding"
AROUND    a team meeting
MEMORY    —
→         ignore
WHY       "We" in a meeting is a team's problem, not his errand.
TRAP      Sounds decisive. But there is no owner, no deadline, nothing to start.
```

```
HEARD     "did you send it?"
AROUND    another voice answers "yeah this morning"
MEMORY    —
→         ignore
WHY       A question aimed at a person in the room, and already answered.
TRAP      Question shape triggers "look it up". Look at who it was aimed at.
```

```
HEARD     "Sarah's going to sort the venue"
AROUND    —
MEMORY    —
→         ignore
WHY       Somebody else's commitment.
TRAP      It is a real, concrete, near-term task — it is just not his. Remember
          it; it will matter when the plan firms up.
```

---

## 3. A plan firming up over several lines

**This is where AROUND does the most work.** The same three words mean nothing
alone and seal a plan in context.

```
HEARD     "seven works"
AROUND    (2 lines ago) "could do Thursday for dinner"
          (1 line ago) other voice: "seven or eight?"
MEMORY    —
→         act
GOAL      "dinner Thursday at 7pm — find and hold options near him"
WHY       A terse confirmation of something already on the table is him
          committing, exactly as much as a full sentence.
TRAP      Two words with no verb. Alone it is noise. The goal must restate the
          FULL plan — day AND time — not just the new detail.
```

```
HEARD     "make it eight instead"
AROUND    dinner Thursday 7pm already agreed
MEMORY    —
→         act
GOAL      "dinner Thursday at 8pm — update from 7pm"
WHY       One detail changing is the plan firming up, not chatter.
TRAP      Emitting a goal of just "8pm". **A detail that never makes it into a
          goal is a detail lost.** Carry everything known so far.
```

```
HEARD     "it'll be us four"
AROUND    dinner Thursday 8pm
MEMORY    —
→         act
GOAL      "dinner Thursday 8pm for four people"
WHY       Party size is a plan detail like any other.
TRAP      Looks like an aside. It is the thing that decides whether the booking
          is even possible.
```

```
HEARD     "actually, let's skip it"
AROUND    dinner Thursday 8pm for four
MEMORY    —
→         act
GOAL      "cancel the Thursday dinner plan"
WHY       Calling something off is work, and it is time-sensitive work.
TRAP      Reads as ignore because nothing is being *started*. Undoing is doing.
          Name what was called off, or nobody knows what to cancel.
```

---

## 4. Questions he says out loud

Looking something up is read-only and costs him nothing. A question with a
findable answer is work worth doing.

```
HEARD     "what time is demo day on Monday again"
AROUND    —
MEMORY    —
→         act
GOAL      "find the start time for demo day on Monday"
WHY       Findable, and he wants the answer.
TRAP      No imperative verb, so it scans as chatter. Carry BOTH details — the
          event and the day — or the research goal is unanswerable.
```

```
HEARD     "how late is that place open"
AROUND    "that place" = the ramen place they just named
MEMORY    —
→         act
GOAL      "find opening hours for <the named ramen place>"
WHY       Findable once AROUND resolves "that place".
TRAP      Emitting a goal containing the words "that place". **Resolve pronouns
          from context before they enter a goal**, or the goal is useless.
```

```
HEARD     "when's my sister's birthday?"
AROUND    —
MEMORY    sister — Nadia — birthday 12 March
→         answer
GOAL      —
WHY       He already told her. This is recall, not research.
TRAP      Going to the internet for a fact that is in memory. Check memory
          first; the internet does not know his sister.
```

```
HEARD     "my sister's birthday is the twelfth of March"
AROUND    —
MEMORY    —
→         ignore  (but REMEMBER it)
WHY       A fact offered for later, not a request.
TRAP      Treating it as a task and setting something up. He is filing, not
          asking. This is the exact input the recall above depends on.
```

---

## 5. Where the context itself is the trap

```
HEARD     "anyway, what's for lunch"
AROUND    (previous line) "I'll send the Devon invoice today"
MEMORY    —
→         ignore
WHY       The current line is chatter. The previous line was a commitment —
          and it was ALREADY acted on when it was heard.
TRAP      **The worst duplicate-job bug in this system.** The previous line
          rides along as background, and a cheap model with nothing telling it
          otherwise acts on it AGAIN — a second job and a second owner text for
          one sentence. Background context is for INTERPRETING the current line.
          Never act on it by itself.
```

```
HEARD     "yeah let's do it"
AROUND    (this morning, 9am) "we could get the roof looked at"
          — current time 3pm
MEMORY    —
→         ask
WHY       Six hours is not a continuing conversation. He may be agreeing to
          something else entirely.
TRAP      Previous-line context has no expiry unless one is enforced. A line
          from 9am silently becoming context for 3pm is the same class of bug
          as stale memory. **Beyond about two minutes, a previous line is not
          context.**
```

```
HEARD     "book it"
AROUND    —
MEMORY    (three months ago) looked at flights to Lisbon
→         ask
WHY       An old memory is not a live plan.
TRAP      Confidently booking Lisbon. Memory says what he once cared about, not
          what he means now. Age the memory before you trust it.
```

```
HEARD     "...and then just send it over when you get a sec"
AROUND    a long stretch of one voice, no interlocutor
MEMORY    —
→         ignore
WHY       He is dictating a message, not instructing her.
TRAP      Perfect imperative shape. The tell is prose with no other speaker —
          he is composing, and the "you" is the person he's writing to.
```

```
HEARD     "so I'll get that over to you by Friday"
AROUND    a call, other voice present
MEMORY    —
→         act
GOAL      "prepare what he owes <the other party> by Friday"
WHY       A commitment he made to someone else is still his commitment.
TRAP      Being on a call reads as "other people's business". The promise is
          his, and a deadline was just attached to it.
```

---

## 6. Not doing the same thing twice

```
HEARD     "I need to email Priya about the invoice"
AROUND    —
MEMORY    an open job: "draft email to Priya about invoice", created 20 minutes ago
→         ignore
WHY       Already in flight.
TRAP      People repeat themselves when something is on their mind. Repetition
          is anxiety, not a second instruction.
```

```
HEARD     "did that email go?"
AROUND    —
MEMORY    job "draft email to Priya" — held, waiting for his OK
→         answer
WHY       He is asking about the state of a thing she is holding.
TRAP      Starting it again. He is asking a question, and she knows the answer.
```

---

## 7. When she must not act on her own

The confirmation gate holds anything irreversible. She still starts the work.

```
HEARD     "just book the 8:40 to Boston"
AROUND    —
MEMORY    —
→         act  (held at the gate)
GOAL      "book the 8:40 flight to Boston — hold for approval"
WHY       Clear, specific, and it spends his money.
TRAP      Two opposite failures. Refusing to start — he asked plainly. And
          buying it outright — a purchase is not undoable. **Start it, hold it,
          tell him it is ready.**
```

```
HEARD     "delete that whole folder, it's junk"
AROUND    —
MEMORY    —
→         ask
WHY       Destructive and ambiguous — which folder.
TRAP      "It's junk" reads as permission. Permission to delete is not the same
          as knowing what to delete. When irreversible meets ambiguous, ask.
```

---

## 8. Not English, still a commitment

Meaning is the test. There is no required verb and no magic phrasing.

```
HEARD     "à mardi"          ("see you Tuesday")
AROUND    arranging a coffee
MEMORY    —
→         act
GOAL      "coffee with <them> on Tuesday"
WHY       A sealed plan, in three syllables, in French.
TRAP      Language-matching on English verbs finds nothing here. Judge by
          meaning only.
```

```
HEARD     "vale, el jueves"   ("okay, Thursday")
AROUND    a proposed date under discussion
MEMORY    —
→         act
GOAL      "<the thing under discussion>, Thursday"
WHY       Same shape as "seven works".
TRAP      Same as above — and the goal still has to carry what was agreed, not
          just the day.
```

---

## 9. The quiet ones that earn the most trust

```
HEARD     "remind me to bring the charger"
AROUND    —
MEMORY    flight to Boston tomorrow 8:40
→         act
GOAL      "remind him about the charger before tomorrow's 8:40 flight"
WHY       He asked directly, and memory supplies WHEN the reminder is useful.
TRAP      A reminder with no time attached is a reminder that fires uselessly.
          Memory is what turns it into a good one.
```

```
HEARD     "I'm so done with today"
AROUND    late evening
MEMORY    —
→         ignore
WHY       He is tired. There is nothing to do and nothing to say.
TRAP      Saying something comforting. **Staying quiet is a feature.** A great
          assistant in the room would not pipe up here.
```

---

## How to add to this file

One entry per *hard* case. Easy cases teach the model nothing and cost tokens.

An entry earns its place if a competent person could plausibly get it wrong, or
if it flips on AROUND or MEMORY. If the decision is obvious from the line alone,
leave it out.

When you fix a real misfire, add the exemplar that would have prevented it, with
the actual line that caused it. That is how this file stays worth its tokens.
