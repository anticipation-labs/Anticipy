# realdays — the fuel for the judge, and the human's marks

This folder is how the loop is judged against reality instead of against examples the builder wrote. Real, messy, full days are the only honest test of whether the system finds the real need in the noise and stays quiet on the rest.

## Folders
- `realdays/raw/` — the human drops real days here: MP3 recordings of a whole day, or typed transcripts. The human does not have to sort or label them. The loop transcribes MP3s itself.
- `realdays/holdout/` — days reserved for the judge. The builder must NEVER read these. They are how the judge tests on days the system has never seen, so a memorized trick dies on the next day.
- `realdays/marked/` — days the human has marked for the taste judge (see below).

## How the loop uses them
- The builder may use days in `raw/` to develop against.
- The judge uses days in `holdout/` to rule on reality, and days in `marked/` to grade judgment.
- When the judge fails a day, that day (or the failing part) is copied into `tests/realday/regressions/` as a permanent case the loop must never regress on.

## Marking, for the taste judge (act vs ask vs silent)
Some of the product is a pure judgment call: was that a real task, or just venting. No app can prove "that was a vent." The only ground truth is the human's mark.
To mark a day, for each meaningful line, label it:
- `act` — a real thing to just do (safe, no money).
- `ask` — do it, but confirm first (the only required ask is anything that spends money; the human may mark others).
- `silent` — leave it completely alone (venting, wishing, joking, talking about people, half-decisions).
Put marked days in `realdays/marked/` in whatever simple format is easy (the line, then the label).

## The honest dependency
Until there are enough marked days to hold some out, the taste judge runs at LOW confidence and the loop may not claim any progress on judgment. The reality judge (did the real thing happen in the real app) does not need marks and runs from day one. Be honest in the scorecard about which is which. Inventing a judgment score from days the human never marked is the exact failure this whole system exists to prevent.
