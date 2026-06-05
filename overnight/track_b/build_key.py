"""Track B — build the ANSWER KEY (human-rule ground truth the decider never sees).

The line that matters is COMMITMENT, not topic. Marked by the seed rule:
  ACT    = a clear first-person commitment / explicit request to do a concrete, safe, reversible
           thing (self-task, reminder, add-to-list, check on a live loop).
  ASK    = a real action whose binding step commits them to a person/thing (book, cancel on someone,
           send/email a real person, pay) OR a half-formed request with unchosen options -> confirm.
  SILENT = no decision to act on: vent, wish/someday, joke/hyperbole, opinion/reaction, or a remark
           ABOUT a person rather than a thing they will DO. When unsure it's a real commitment -> SILENT.

Seed rows are the human's 12 (marked verbatim). The rest I wrote to be varied + near-the-line; many
are deliberately ambiguous (flagged `nearline`) and are exactly the rows the human should red-pen.
Emits answer_key.jsonl {id,line,label,split,source,nearline}. Held-out = ~40%, stratified; the
decider is only ever iterated against the TRAIN slice and reported on HELD-OUT.
"""
from __future__ import annotations

import json

# (line, label, source, nearline)
ROWS = [
    # ---- SEED (the human's 12, verbatim) ----
    ("I'll send Sarah the Q3 deck tonight.", "ACT", "seed", False),
    ("Remind me to call the accountant before Friday.", "ACT", "seed", False),
    ("Add milk and coffee to the list.", "ACT", "seed", False),
    ("Did the dispute ever get filed? I should chase it.", "ACT", "seed", False),
    ("Let's grab dinner Friday, I'll book somewhere.", "ASK", "seed", False),
    ("Cancel my 3pm, something came up.", "ASK", "seed", False),
    ("I'll email the landlord about the leak, or maybe just call.", "ASK", "seed", False),
    ("Ugh, my gym is such a ripoff.", "SILENT", "seed", False),
    ("I should get back into Spanish someday.", "SILENT", "seed", False),
    ("We should move to Lisbon, haha.", "SILENT", "seed", False),
    ("Mark's been so flaky lately.", "SILENT", "seed", False),
    ("This podcast is incredible.", "SILENT", "seed", False),

    # ---- ACT (clear, safe, reversible self-tasks / explicit requests) ----
    ("Remind me to take out the trash tonight.", "ACT", "mine", False),
    ("Add 'renew passport' to my todo list.", "ACT", "mine", False),
    ("Put 'submit the expense report' on my list for Monday.", "ACT", "mine", False),
    ("I'll write up the meeting notes after lunch.", "ACT", "mine", False),
    ("Remind me to water the plants when I get home.", "ACT", "mine", False),
    ("Add eggs, bread, and butter to the shopping list.", "ACT", "mine", False),
    ("Find me the cheapest flight to Denver next month.", "ACT", "mine", False),
    ("Look up what time the hardware store closes today.", "ACT", "mine", False),
    ("I'll draft the thank-you note to the team tonight.", "ACT", "mine", False),
    ("Remind me to send the invoice on the first.", "ACT", "mine", False),
    ("Don't let me forget to pay rent this week.", "ACT", "mine", False),
    ("Can you check if my package shipped yet?", "ACT", "mine", False),
    ("I need to follow up with the plumber tomorrow — remind me.", "ACT", "mine", False),

    # ---- ASK (real action; binding step / half-formed) ----
    ("Book us a table for four on Saturday night.", "ASK", "mine", False),
    ("Send the signed contract back to the agency.", "ASK", "mine", False),
    ("Reply to Priya and tell her we're in.", "ASK", "mine", False),
    ("Cancel the gym membership, I'm done with it.", "ASK", "mine", False),
    ("I'll RSVP yes to the wedding for both of us.", "ASK", "mine", False),
    ("Forward the contract to legal.", "ASK", "mine", False),
    ("Move my 2pm to 4pm and let Sam know.", "ASK", "mine", False),
    ("Schedule the kickoff with the client for next week.", "ASK", "mine", False),

    # ---- SILENT (no decision: vent / wish / joke / opinion / about-a-person) ----
    ("I'm so done with this weather.", "SILENT", "mine", False),
    ("Honestly the new update is kind of ugly.", "SILENT", "mine", False),
    ("Maybe I'll start running again at some point.", "SILENT", "mine", False),
    ("Wouldn't it be nice to just quit and sail around the world.", "SILENT", "mine", False),
    ("That restaurant was a huge letdown.", "SILENT", "mine", False),
    ("My boss is impossible sometimes.", "SILENT", "mine", False),
    ("I kind of want a dog eventually.", "SILENT", "mine", False),
    ("Traffic was insane today.", "SILENT", "mine", False),
    ("We really should hang out more.", "SILENT", "mine", False),
    ("I can't believe it's already June.", "SILENT", "mine", False),
    ("She never texts back, it's so annoying.", "SILENT", "mine", False),
    ("I'd kill for a vacation right now.", "SILENT", "mine", False),
    ("If I won the lottery I'd buy an island.", "SILENT", "mine", False),
    ("The Wi-Fi here is garbage.", "SILENT", "mine", False),
    ("He's always late, every single time.", "SILENT", "mine", False),
    ("That movie did not deserve the hype.", "SILENT", "mine", False),
    ("I wish my apartment had more light.", "SILENT", "mine", False),
    ("Our team's been killing it lately.", "SILENT", "mine", False),
    ("Ugh, Mondays.", "SILENT", "mine", False),

    # ---- NEAR-THE-LINE (deliberately ambiguous — red-pen candidates) ----
    ("I really need to call my mom.", "SILENT", "mine", True),         # felt obligation, not an explicit request
    ("We should book that trip soon.", "SILENT", "mine", True),        # vague "should...soon", no concrete commit
    ("I might email the professor about the deadline.", "SILENT", "mine", True),  # "might" = not a commitment
    ("I keep meaning to cancel that subscription.", "SILENT", "mine", True),      # unfulfilled intention, not now
    ("I've got to get back to the dentist one of these days.", "SILENT", "mine", True),  # someday
    ("Maybe we grab coffee this week?", "SILENT", "mine", True),       # tentative, unconfirmed
    ("I'll probably tidy up the garage this weekend.", "ACT", "mine", True),  # soft but a real self-task w/ a when
    ("I told Jen I'd send her the photos.", "ACT", "mine", True),      # a promise to a person (photos = safe to draft)
]


def main():
    rows = []
    # stratified held-out: every 3rd row within each label -> heldout (~33-40%)
    counters = {}
    for line, label, source, nearline in ROWS:
        i = counters.get(label, 0)
        counters[label] = i + 1
        split = "heldout" if i % 3 == 2 else "train"
        rows.append({"id": f"{label[:1]}{i:02d}", "line": line, "label": label,
                     "split": split, "source": source, "nearline": nearline})
    with open("overnight/track_b/answer_key.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from collections import Counter
    print("rows:", len(rows), "by label:", dict(Counter(r["label"] for r in rows)),
          "| heldout:", sum(1 for r in rows if r["split"] == "heldout"),
          "| nearline:", sum(1 for r in rows if r["nearline"]))


if __name__ == "__main__":
    main()
