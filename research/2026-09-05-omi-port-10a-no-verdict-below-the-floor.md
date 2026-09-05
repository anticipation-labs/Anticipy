# Omi port 10a — no verdict is below the floor

Built 2026-09-05 from the port-10a brief's ATTACK `corrected_mechanism`
(design verdict BUILD, attack verdict NEEDS-REWORK; the corrected version is
what shipped). Ledger row: research/2026-09-04-omi-port-coverage.md row 10 —
the integrator flips it; this file is what it flips on.

## What was missing

Every dedicated single-question verdict already fell quiet on absence
(party_verdict, calendar_plan_verdict, ends_in_the_world, work_is_licensed,
plan_is_settled), but the PRIMARY triage verdict's routing fields fell on the
ACT side when absent, by documented design:

- `addressee=None` was in neither AMBIENT_ADDRESSEES nor anything else, so it
  skipped the ambient gate and took the direct lane — an immediate
  `notify_owner` text with no quiet hours, no meeting posture, no shard floor,
  and the ask branch's "Quick question". Stated outright in the code: "None
  (field missing or invalid) fails open to the behaviour she had before this
  field existed" and "(No classification at all keeps the old texting
  behaviour: the honesty wall cuts both ways.)"
- `owes=None` passed both fences (`in NOT_HIS`, `== "other"`), so a consequential
  goal with no verdict on whose errand it was reached the act lane as if he
  had said it was his.
- `clock_tick` read `initiate`/`say` by truthiness, so the STRING "false" (or
  "no", or 1) passed and the `say` beside it was texted about an old loop.
- The strong second opinion's `except Exception: pass` left the cheap "act"
  standing when the frontier re-judgement raised or was unreadable — a floor
  lifting itself the moment the strong model was down.

Omi's mechanism (missing confidence -> 0.5 < 0.80) has nothing to port
literally: `grep -rn -i confiden brain/*.py` finds only memory.py's fact-ranking
floor. The four-state verdict is the analog and the POLARITY is the port.

## The measured failure it pins

2026-08-23 (research/evals/call-2026-08-23-tejas/): 137 decisions, 6 acts,
5 wrong, 0 asks, speaker/attribution absent on every line. NOT CLAIMED: the
six acts carried positive labels (self x5, person x1), so this port does not
fix them — their fix is speaker attribution (04b) plus ANTICIPY_STRONG_MODEL set
in prod, which this port makes safe to turn on (an outage no longer hands the
day back to the cheap model).

## What replaced it — two floors, each refusing only what it authorizes

1. `DIRECT_ADDRESSEES = ("assistant",)` in brain/orchestrator.py beside
   AMBIENT_ADDRESSEES. The lane gate in brain/anticipy_core.py became
   `if addressee not in DIRECT_ADDRESSEES and decision.decision in ("act","ask")`:
   a None addressee on a non-explicit line takes the ambient lane (shard floor,
   ends_in_the_world, quiet research, held card with lane=desk and ONE
   `ambient_act` text, the parked-ask valve). `who = addressee or
   "unattributed"` feeds every reason string so the record never calls a
   silence "person-directed". Explicit lines are forced to "assistant" above
   the gate and are unchanged.
2. HANDS FLOOR: `no_owes = decision.owes is None and addressee not in
   DIRECT_ADDRESSEES`; the not-his fence became `(owes in NOT_HIS or no_owes)`.
   An absent owes takes the nobody treatment (quiet lookup at most, nothing
   prepared, nothing texted) ONLY when no positive addressee verdict
   authorizes her voice. `may_look` and `settled` widened to `owes in
   ("nobody", None)`; `settled` compares `addressee not in DIRECT_ADDRESSEES`
   (was `in AMBIENT_ADDRESSEES`) so a None addressee reaches the one positive
   tiebreaker. The None reason begins "no verdict" and never says "nobody";
   the returned Decision carries owes=None.
3. CLOCK FLOOR: `initiate is not True or not isinstance(say, str) or not
   say.strip()` -> print + return None. An honest JSON false stays silent
   without a complaint, as before.
4. STRONG FLOOR: a configured, live strong look that raises or returns no
   readable `decision` demotes a NON-explicit cheap act/ask/quiet-goal to
   decision="ignore", goal=None, reason "no verdict from the strong second
   opinion — not acting on the cheap verdict alone". Explicit lines keep the
   cheap verdict. Inert while ANTICIPY_STRONG_MODEL is unset (prod today).

Nothing reads a word. Every new comparison is a closed-set label read, a
type check on a JSON transport contract, or a key's presence.

Deleted, with "WHAT WAS HERE UNTIL 2026-09-05, Omi port 10a" comments at each
site: the "fails open" sentence, the "honesty wall cuts both ways" sentence,
the `except Exception: pass`, the truthiness read, and the honesty-wall comment
on `owes = None` in triage.

## When an ordinary day changes

- Both labels present (the ordinary case; 94/94 non-fallback Tejas rows had an
  addressee): nothing. No new model call, no new text, no new latency —
  pinned by `test_a_clean_verdict_pays_nothing_new`.
- addressee absent on a non-explicit act/ask: the ambient lane instead of the
  direct one. A read-only goal may spend one ends_in_the_world call; a
  consequential one spends the governed text instead of the ungoverned one.
- owes absent on a non-explicit act/ask NOT aimed at her: the nobody treatment.
  A consequential goal spends one plan_is_settled call (and ends_in_the_world
  if the wording reads read-only) where a text was about to go out. The
  read-only case queues the same quiet ambient job it did before.
- owes="nobody" with addressee=None (previously silent, tiebreaker
  unreachable): now consults plan_is_settled and can reach the held card.
- clock reply with non-boolean initiate or non-string/empty say: nothing this
  tick (was: a text).
- strong look configured+live+unanswered: demotion (was: cheap act stands).

Tape note for the ledger: the None-owes branch routes more goals through
`is_consequential()` inside `may_look`, i.e. through the registered
`[tape:read_only_re]` regex. Not a new violation; the tape's reach grew; its
expiry is unchanged; no TAPE: comment was added and tape_gate.py is untouched
(`RED LEGS: 2 (by design)`).

## Tests

New: tests/test_no_verdict_is_below_the_floor.py — 41 legs driving the real
hear() with `_decide` stubbed and pb monkeypatched (jobs really post), the
real clock_tick with a prompt-routed double, the real Brain.triage with a fake
strong model.

Reversed pins, each with the old ruling quoted in its docstring:
- tests/test_owes.py `test_a_missing_verdict_changes_nothing` ->
  `test_a_missing_verdict_withholds_her_hands`; `test_a_garbage_verdict_changes_nothing`
  -> `test_a_garbage_verdict_withholds_her_hands`.
- tests/test_strong_goal_second_look.py
  `test_unanswered_strong_model_leaves_the_cheap_candidate_for_existing_floors`
  -> `test_unanswered_strong_model_demotes_the_cheap_candidate`.

Fixtures that stated the verdict they relied on (owes="owner" added; the
behaviour they pin is unchanged): tests/test_silence_means_stillness.py,
tests/test_grounded_text.py, tests/test_question_not_a_form.py,
tests/test_self_talk_question.py (all four behaviour legs; the None leg of
`test_a_question_aimed_at_her_is_always_asked` is kept and now goes through
the governed lane — the attack's suggested edit dropped it, but with the
corrected mechanism it is green and pins that an unattributed question is
not silenced). tests/test_lane_routing.py's two channel legs script their
Decision (addressee="assistant", owes="owner") instead of riding the offline
`_decide` arm, which emits neither field and must not be given defaults.
tests/test_memory_knows_who_spoke.py: untouched, green.

Full suite: `3 failed, 2494 passed` — the same three environment failures as
baseline on this HEAD (`3 failed, 2453 passed` before the port: roster_parity
x2 numpy, segmenter_link_tape py3.9), nothing else red.
tejas_gate: leg 6 red by design, nothing new.

## Mutations (all run; file backed up to an absolute path, mutated, run,
restored, `diff -q` byte-identical, run green)

| mutation | red | restored |
|---|---|---|
| M1 named: lane gate reverted to `addressee in AMBIENT_ADDRESSEES` | `4 failed, 37 passed` (a, b, read-only, settled-both-blank) | `41 passed` |
| M2 never consulted: `no_owes = False` | `5 failed, 49 passed` (c, quiet lookup, settled-both-blank, both test_owes pins) | `54 passed` |
| M3 tiebreaker unreachable: `settled` back to `in AMBIENT_ADDRESSEES` | `1 failed, 40 passed` (d) | `41 passed` |
| M4 wall: DIRECT term dropped from `no_owes` | `3 failed, 49 passed` (e, act twin, test_speaker_tag direct question) | `52 passed` |
| M5 polarity inversion: lane gate `addressee in DIRECT_ADDRESSEES` | `9 failed, 32 passed` | `41 passed` |
| M6 clock: truthiness read restored | `10 failed, 31 passed` | `41 passed` |
| M7 strong: demotion branch unreachable | `8 failed, 36 passed` (h legs + reversed pin) | `44 passed` |

## The live leg

overnight/unattributed_lane_live.py — are_the_ears_live's UNPROVEN pattern.
Control: transcript rows with decision in (act, ask), addressee "" and explicit
false over the window. RED on a same-goal job minted within 90s of the row's
stamp with no params.lane (the direct lane's signature), or a goalless
anticipy_says ask within 15s of the stamp (the parked valve waits ASK_QUIET_S
= 120s of silence). GREEN only with a non-zero control, no hits, and
`--fingerprint` equal to the tree's `_brain_fingerprint()` (Law 3). It never
requests `text`. Self-test 10/10.

Run 2026-09-05 against production, read-only, 7 days:

    act/ask rows WITH an addressee     2
    act/ask rows with NO addressee     0 (the control)
    quiet ambient ignore bucket        163 (upper bound on owes-blank drops)
    tree fingerprint                   c1044df8f54e (pre-commit tree)
    verdict                            UNPROVEN, exit 2

It is a tripwire that will read UNPROVEN until an unattributed act/ask occurs
live; the offline mutation suite is the proof of record until then. The
owes-blank drop count is not derivable from stored fields (reason is not
stamped by mark_processed); the exact count is
`grep -c "no verdict on whose errand" <worker log>`.

## Not done, plainly

- Not verified live (Law 3): the worker has not been deployed with this code;
  after deploy, run the leg with `--fingerprint` from the worker's startup
  log. The leg cannot go green until an unattributed act/ask occurs.
- The ledger row (research/2026-09-04-omi-port-coverage.md row 10) is the
  integrator's to flip; docs/BRIEF.html's stale "valve is welded / 0 asks" line
  was corrected in this change.
- `uninvited_sent_today` returning 0 on a failed read stays flagged for port
  10b. conversation.py's `intent = parsed.get("intent", "chat")` was named in
  the brief's evidence but not in the corrected mechanism and is untouched.
