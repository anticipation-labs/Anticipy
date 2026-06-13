"""Room 1 clause-scope pins — vents silence themselves, never the command beside them.

Ledger F8: confident negatives fired at UTTERANCE granularity while positive shapes were
clause-scoped, so one vent clause deafened an explicit money command in the next clause —
the never_act tripwire was being passed by deafness, not judgment. Ledger C18: isolation
pins validate a family's REGEX, not its CATCH — a family can be present-but-inert behind
the utterance-level wall. So every SURVIVE pin here is IN SITU: the commitment embedded
behind a real vent/negative prefix (the F8 composition), not the family alone. The DROP
half is load-bearing: two holdout personas sit AT the interrupt ceiling (3.0), so one junk
pass per day on their days fails gate_P2, and an unmatched ACT is a false action.

Also pins ledger F9 end-to-end: a "send <person> <amount> over <rail>" money transfer
categorizes binding_send (not money) at the harm-line, which used to bypass Room 2.6's
retraction window — the named regression check is a two-line money-command-then-retraction
replay ending with ZERO surfaced asks.

Also pins ledger F11 (all-clauses-negative -> absolute False in live mode; the fail-open
tiebreak stays reserved for matched-nothing lines) and the families widened this lap
(causative-get participles, reminder-noun imperatives, errand head verbs/phrasals), each
SURVIVE pin in situ behind a real vent prefix and each new surface with a DROP half.

Also pins the lap-232257Z inventory sweep (223727Z verdict condition 2): every
_PHRASAL_IMP pair and _CAUSATIVE_GET participle swept in from the four cited public
errand/office/work/school lists ships an in-situ SURVIVE pin (vent-prefixed, the F8
composition) and a narration DROP pin; the bare directional causative-get (_GET_TO_TAIL)
is pinned on both sides of its clause-initial anchor; the inventory-borne vent idioms
("Turn in early...", "turn over a new leaf") are pinned excluded.

All pins self-authored shape-equivalents, never bank copies (C13; the pins the 131707Z
judge flagged as bank echoes — C19 — were rewritten with fresh content words, a fresh
timestamp, and names verified absent from the dev bank; the two sub-6-token near-echoes
the 223727Z judge flagged — C21 — were rewritten with the bank names removed, and the
file re-scanned at 4-token shingles plus a dev-bank proper-noun name scan).
Zero model calls; deterministic; CI-safe.
Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_triage_clause_scope.py
"""
import asyncio
import sys
import tempfile
from pathlib import Path

from anticipy_engine.core.bus import Bus
from anticipy_engine.core.envelopes import Event, EventSource, GoalState
from anticipy_engine.core.gateway import ModelGateway
from anticipy_engine.core.orchestrator import AutoApprover, Orchestrator
from anticipy_engine.core.proactive import ProactiveEngine
from anticipy_engine.core.store import GoalStore
from anticipy_engine.core.workers import BrowserStub, ChannelStub, ConnectorStub, MemoryStub
from anticipy_engine.proactive.debounce import AskDebounce
from anticipy_engine.proactive.triage import Triage

# (text, must_survive, shape) — labels NEVER enter triage.actionable(); used only to score.
CASES = [
    # --- F8 un-deafened: vent/negative clause + command clause -> the command is heard ---
    ("I'd be a wreck without him. Send Stefan forty bucks over paypal for the tailgate.",
     True, "bare-I'd + transfer command"),
    ("I told the league I'd cover my share of the jerseys. Send Marisol the sixty over venmo so the order ships Friday.",
     True, "reported-promise vent + transfer command"),
    ("I'll deal with that later. Remind me to pay the water bill tonight.", True, "deferral + remind-me"),
    ("She already handled the cake order. Book the photographer for Saturday.", True, "already-handled + imperative"),
    ("I'd never survive August without the AC. Put new filters on the shopping list.",
     True, "bare-I'd + list-put (the C18 present-but-inert family, now live in situ)"),
    # --- list-put alone (re-landed family; judge-verified to match a holdout miss in situ) ---
    ("Put paper towels on the grocery list.", True, "list-put"),
    ("Add sunscreen to the shopping list for the trip.", True, "list-put"),
    ("Jot that down before I forget.", True, "list-put/jot-down"),
    ("That goes on the list too.", True, "list-put/3rd-person"),
    # clock-time colons are NOT clause boundaries — splitting "7:40" shreds the idiom
    ("Sure - put hallway duty Friday 7:40 to 8:10 on my calendar.", True, "calendar-put spanning a clock range"),
    # --- the load-bearing DROP half: vents must still silence themselves ---
    ("Oh sure. I'll just duplicate myself by Friday.", False, "sarcasm frame poisons weak I'll across clauses"),
    ("Oh sure, I'll just grow a second pair of hands.", False, "sarcasm, single clause"),
    ("If one more thing breaks this week I'll lose it. I'll just quit.", False, "if-frame + weak continuation"),
    ("Maybe I'll frame it. Seriously.", False, "musing, clause-anchored"),
    ("I'll skim the packet during warmups. Probably.", False, "trailing hedge stays utterance-absolute"),
    ("Someday I'll organize the photo archive. We'll see.", False, "hedge + trailing hedge"),
    ("Hold it — don't send anything to the realtor yet. I'll email them my own answer.",
     False, "countermand stays utterance-absolute, beats later weak intent"),
    ("I'd be lost without her. Such a good kid.", False, "bare-I'd vent with NO command beside it"),
    ("I'd snap if the wifi died again. Look at this rain.", False, "vent + non-command clause (false-action surface)"),
    ("I'd lose my mind if one more thing broke today.", False, "bare-I'd, single clause"),
    ("I told him I'd think about it.", False, "reported deferral"),
    ("She already handled the inspection paperwork.", False, "already-handled alone"),
    ("I should clean out the basement someday.", False, "hedge alone"),
    ("Morgan can you pull the freight numbers for the Hudson job?", False, "vocative aside"),
    ("She can take the recycling run this week, one less thing.", False, "handled by someone else"),
    ("That one goes straight onto the bucket list.", False, "bucket list is a someday-vent"),
    ("Skydiving is on my bucket list for sure.", False, "bucket list narration"),
    # --- widened positive families (this lap), each in situ per C18(a) ---
    ("I'd scream if the dryer quits mid-cycle again. Get the vent hose replaced this week.",
     True, "causative-get, widened participle, in situ"),
    ("I'd sell the printer for parts some days. Get the mower blades sharpened before Saturday.",
     True, "causative-get, widened participle #2, in situ"),
    ("Honestly I'd forget my own head today. Set a reminder to renew the parking permit Friday.",
     True, "reminder-noun imperative, in situ"),
    ("Get me a reminder for the pharmacy pickup at noon.", True, "get-form reminder request"),
    ("I'd nap for a week if I could. Pick up the dry cleaning before six.",
     True, "errand phrasal imperative, in situ"),
    ("She's got the cones covered for drills. Bring the spare whistle to practice.",
     True, "widened head-verb imperative behind a handled clause"),
    ("Print the waiver for the field trip tonight.", True, "widened noun-prone verb with object"),
    # --- counterexamples for the widened surfaces: imperative-shaped vents stay vents ---
    ("Honestly? Bring it on.", False, "imperative-shaped vent idiom"),
    ("Ugh, bring it on, I guess.", False, "vent idiom + trailing hedge"),
    ("Check this out — the raccoon figured out the latch.", False, "attention-getter, not a command"),
    ("Print quality on the new copier is rough.", False, "widened verb in noun position"),
    ("Return policy here is brutal, honestly.", False, "widened verb in noun position #2"),
    ("File that under things I cannot control.", False, "imperative-shaped quip"),
    ("The mail came early today.", False, "widened verb as plain noun"),
    ("I never set an alarm on weekends.", False, "reminder noun in narration"),
    ("She got a reminder from the dentist this morning.", False, "reminder noun, third-person narration"),
    # --- inventory sweep, lap 232257Z (223727Z verdict cond. 2a): _PHRASAL_IMP pairs,
    # --- one in-situ SURVIVE (vent-prefixed) + one narration DROP per pair ---
    ("I'd lose my mind in that warehouse. Look for the silver toolbox near the loading door.",
     True, "look-for, in situ"),
    ("Spent the whole afternoon looking for parking downtown.", False, "look-for narration"),
    ("I'd never survive a mall in December. Pick out a birthday card for the principal.",
     True, "pick-out, in situ"),
    ("The wallpaper we picked out ages ago is peeling.", False, "pick-out narration"),
    ("She's got the bake sale covered. Stock up on napkins before the weekend rush.",
     True, "stock-up, in situ"),
    ("We're stocked up on batteries till spring.", False, "stock-up narration"),
    ("I'd faint at that invoice. Pay for the permit renewal before the late fee kicks in.",
     True, "pay-for, in situ"),
    ("Lunch was paid for by the vendor rep.", False, "paid-for: the experiential participle exclusion"),
    ("I'd melt in that fitting room. Try on the rental tux before Thursday.",
     True, "try-on, in situ"),
    ("He tried on four jackets and hated every one.", False, "try-on narration"),
    ("I'd scream if we kept that wobbly fan. Take back the leaf blower while the receipt is current.",
     True, "take-back, in situ"),
    ("That song takes me back to the lake summers.", False, "take-back idiom narration"),
    ("She's got the linens handled. Put away the holiday bins so the car fits.",
     True, "put-away, in situ"),
    ("Everything was put away by the time I got home.", False, "put-away narration (no get-frame)"),
    ("I'd nap till Monday if I could. Wrap up the donation receipts tonight.",
     True, "wrap-up, in situ"),
    ("Gift wrap at that kiosk costs twelve dollars.", False, "wrap in noun position"),
    ("I'd forget my own birthday this week. Note down the gate code for the movers.",
     True, "note-down, in situ"),
    ("The note down in the lobby says elevator two is out.", False, "note in noun position"),
    ("She's covering the morning shift. Call off the vendor walkthrough for Friday.",
     True, "call-off, in situ"),
    ("The street fair got called off for wind again.", False, "called-off narration (got, not get/gets)"),
    ("Honestly I'd cry at that inbox. Go through the receipts bin before tax season eats the weekend.",
     True, "go-through, in situ (pair reachable past the 'go' lead word)"),
    ("We go through three gallons of milk a week.", False, "go-through narration"),
    ("I told the front desk I'd handle it. Fill out the visitor log before security asks.",
     True, "fill-out, in situ"),
    ("The fill line on the tank is cracked.", False, "fill in noun position"),
    ("I'd combust reading another memo. Carry out the recall steps from the bulletin.",
     True, "carry-out, in situ"),
    ("Carryout from the thai place again, no shame.", False, "carryout in noun position"),
    ("I'd doodle through every meeting if I could. Draw up the chore chart for the cousins.",
     True, "draw-up, in situ"),
    ("The kids draw up such a storm after dinner.", False, "draw-up narration"),
    ("He's got the gate duty sorted. Hand over the spare fob to the night super.",
     True, "hand-over, in situ"),
    ("I won't hand over my Saturday without a fight.", False, "hand-over narration"),
    ("I'd never make it before close. Run by the pharmacy for the ear drops.",
     True, "run-by, in situ"),
    ("The summers just run by faster every year.", False, "run-by narration"),
    ("I'd doze off grading one more page. Turn in the field trip money before the office closes.",
     True, "turn-in, in situ"),
    ("He turned in around nine, lightweight.", False, "turn-in (go to bed) narration"),
    ("Turn in early tonight, you look beat.", False, "turn-in-early vent idiom excluded"),
    ("She's handling the inspection prep. Turn over the boiler room keys to the day porter.",
     True, "turn-over, in situ"),
    ("The engine turns over but won't catch.", False, "turn-over narration"),
    ("Ugh, turn over a new leaf, they keep telling me.", False, "turn-over-a-new-leaf vent idiom excluded"),
    ("I'd misplace my head before noon. Look over the consent forms before the field trip.",
     True, "look-over, in situ"),
    ("She kept looking over her shoulder the whole tour.", False, "look-over narration"),
    ("I'd lose half the stack in the hallway. Pass out the rubrics before the bell.",
     True, "pass-out, in situ"),
    ("I nearly passed out grading at midnight.", False, "passed-out: the experiential participle exclusion"),
    ("She already handled the seating chart. Hand out the visitor badges at the door.",
     True, "hand-out, in situ"),
    ("Handouts from last term are still in my trunk.", False, "handout in noun position"),
    # --- inventory sweep: _CAUSATIVE_GET participles, in-situ SURVIVE + narration DROP each ---
    ("I'd sleep through Friday otherwise. Get the timesheets turned in before payroll locks.",
     True, "get-turned-in, in situ"),
    ("My essay got turned in late and it haunts me.", False, "turned-in narration (got, not get/gets)"),
    ("She's got the lobby line handled. Get the intake packet filled out before the nurse calls us back.",
     True, "get-filled-out, in situ"),
    ("The forms were filled out in pencil, classic.", False, "filled-out narration"),
    ("I'd botch the wording for sure. Get the sublease drawn up before the first.",
     True, "get-drawn-up, in situ"),
    ("Plans got drawn up and abandoned twice this year.", False, "drawn-up narration"),
    ("I'll deal with it later. Get the recall steps carried out before the audit window.",
     True, "get-carried-out, in situ"),
    ("The drill was carried out without a hitch.", False, "carried-out narration"),
    ("I'd melt standing out there. Get the rooftop tasting called off before the heat spike.",
     True, "get-called-off, in situ"),
    ("Recess got called off for the third day straight.", False, "called-off narration"),
    ("I'd lose the thing in a day. Get the loaner badge handed over to security before my shift ends.",
     True, "get-handed-over, in situ"),
    ("The keys were handed over at closing, done deal.", False, "handed-over narration"),
    ("She's covering the door. Get the agendas handed out before the chair sits down.",
     True, "get-handed-out, in situ"),
    ("Flyers got handed out all morning at the corner.", False, "handed-out narration"),
    ("I'd misread page one anyway. Get the appraisal letter looked over before we sign anything.",
     True, "get-looked-over, in situ"),
    ("My transcript got looked over by three people already.", False, "looked-over narration"),
    ("I'd scramble the digits by dinner. Get the locker combo noted down somewhere safe.",
     True, "get-noted-down, in situ"),
    ("The combo was noted down years ago in some binder.", False, "noted-down narration"),
    ("I'd dither in that aisle for an hour. Get the thank-you card picked out before the shop shuts.",
     True, "get-picked-out, in situ"),
    ("The paint got picked out before I had a vote.", False, "picked-out narration"),
    ("I'd trip over that pile nightly. Get the camping gear put away before the cold snap.",
     True, "get-put-away, in situ"),
    ("The decorations got put away in March, a miracle.", False, "put-away narration"),
    ("I'd panic at an empty pantry. Get the formula stocked up before the long weekend.",
     True, "get-stocked-up, in situ"),
    ("We stayed stocked up all winter somehow.", False, "stocked-up narration"),
    ("I'd keep missing the return window. Get the modem taken back before the fee hits.",
     True, "get-taken-back, in situ"),
    ("The blender got taken back without the box.", False, "taken-back narration"),
    ("I'd guess the size wrong twice. Get the bridesmaid dress tried on before alterations close.",
     True, "get-tried-on, in situ"),
    ("The suit was tried on once and never worn.", False, "tried-on narration"),
    ("I'd stall on this till spring. Get the donation receipts wrapped up before the books close.",
     True, "get-wrapped-up, in situ"),
    ("Filming got wrapped up before the rain.", False, "wrapped-up narration"),
    ("I'd word it badly under pressure. Get the severance numbers run by counsel before anyone replies.",
     True, "get-run-by, in situ"),
    ("The numbers were run by legal months ago.", False, "run-by-participle narration"),
    ("I'd skim and miss the bad clause. Get the lease rider gone through before we initial it.",
     True, "get-gone-through, in situ"),
    ("That archive got gone through twice already.", False, "gone-through narration"),
    ("I'd tear the den apart for nothing. Get the spare fob looked for before we buy a replacement.",
     True, "get-looked-for, in situ"),
    ("The remote got looked for and never found.", False, "looked-for narration"),
    ("I'd hold the keys hostage by accident. Get the unit keys turned over to the manager before checkout.",
     True, "get-turned-over, in situ"),
    ("The shop got turned over to the nephew last fall.", False, "turned-over narration"),
    # --- bare directional causative-get (223727Z verdict cond. 2b): clause-initial anchor ---
    ("I'd be a zombie by the matinee. Get the spare inhaler to Tobias before curtain.",
     True, "directional get <thing> to <Name>, in situ"),
    ("Get the signed waivers to the front office before lunch.",
     True, "directional get <thing> to <determiner noun>"),
    ("I get the twins to school by eight most days.", False, "directional-get narration (subject, not clause-initial)"),
    ("Somehow we get the cousins to the airport every single visit.", False, "directional-get narration #2"),
    ("Get back to me when the quote lands.", False, "get-back-to-me idiom excluded by the object slot"),
    ("Get dinner to go from the noodle place.", False, "to-go idiom excluded by the recipient shape"),
    # --- benefactive-staging imperative (232257Z verdict cond. 2 / F15a): clause-initial
    # --- imperative or causative-get, det-fronted object, benefactive "for me/us" tail.
    # --- Open-vocabulary heads: every SURVIVE head below is in NO imperative lexicon.
    ("If one more binder walks off I'll lose it. Collate the orientation packets for me with the cover sheet filled in.",
     True, "benefactive-staging imperative, out-of-lexicon head + prefill tail, in situ"),
    ("She's got the signage handled. Box up the leftover programs for me before the custodian locks the gym.",
     True, "benefactive imperative with particle, out-of-lexicon pair, in situ"),
    ("I'd misnumber the lockers for sure. Get the roster sheets collated for me by the morning bell.",
     True, "causative-get with an OUT-of-lexicon participle riding the benefactive tail, in situ"),
    ("Relabel the allergy bins for me before the new aide starts.",
     True, "benefactive imperative, bare"),
    ("I'd misread the totals at midnight. Go over the reimbursement sheet for me before it heads to finance.",
     True, "go-headed benefactive phrasal survives the lead-word skip (F14 discipline), in situ"),
    ("Run the projector queue list past the AV desk for me.",
     True, "benefactive tail with an open-vocabulary head and a long object"),
    # --- the load-bearing DROP half: the three judge-enumerated junk classes + denies ---
    ("She collated the festival packets for me before she clocked out.",
     False, "subject-ful narration (benefactive junk class 1)"),
    ("Pray for me, the auditors land at nine.",
     False, "no object between verb and for-me (benefactive junk class 2)"),
    ("Root for us at the tournament tonight!",
     False, "benefactive vent, no det-fronted object"),
    ("Soren from facilities did the whole printer run for me, total lifesaver.",
     False, "third-person did-X-for-me gratitude narration (benefactive junk class 3)"),
    ("Made the entire morning smoother for me, honestly.",
     False, "dropped-subject past-head gratitude narration"),
    ("Covering the early shift for me was huge of her.",
     False, "gerund head narration"),
    ("Saves a whole hour for me every single week.",
     False, "third-person-s head stative narration"),
    ("Practice the day after was brutal for me.",
     False, "appositive noun head + finite verb in the tail (gap deny)"),
    ("Quite the week for me already.",
     False, "degree-word head vent"),
    ("Eat a beignet for me at the festival.",
     False, "vicarious-enjoyment benefactive well-wish"),
    ("Hold the elevator for me!",
     False, "present-company physical favor excluded"),
    ("Feed the sourdough starter for me while I'm gone.",
     False, "present-company favor excluded (F13's verb stays junk-bounded here too)"),
    ("Cover the closing shift for me Saturday?",
     False, "shift-swap request to present company excluded"),
    ("Say a word to the manager for me.",
     False, "say-head courtesy excluded"),
    ("Put in a good word for me with the committee.",
     False, "good-word idiom excluded by surface"),
    ("Break a leg out there for me!",
     False, "well-wish idiom excluded by surface"),
    ("Go the extra mile for me on this one.",
     False, "go-headed benefactive requires a particle (extra-mile idiom stays out)"),
    # --- reported promise (ledger F21): "I told/promised <person> (that) I'd <verb> ..."
    # --- is a commitment the speaker already owns; the bare-I'd vent alternative was
    # --- eating the clause. The frame cancels that reading and counts as a positive.
    # --- Every SURVIVE head below is open-vocabulary; every deny class has a DROP pin.
    ("Edwin needs the corrected estimate before Tuesday; I told him I'd send it.",
     True, "third-person need + bare reported promise (the F21 shape itself)"),
    ("I'd cry if the printer jams again. I told Imani I'd reprint the banquet signs tonight.",
     True, "reported promise behind a bare-I'd vent clause, in situ"),
    ("I promised Renata I'd circulate the visit recap before standup.",
     True, "promised + name, out-of-lexicon committed verb"),
    ("I told the landlord I'd drop the signed addendum at the office Saturday.",
     True, "told + role noun (multi-token gap)"),
    ("I said I'd cover the carpool run on Wednesday.",
     True, "said-frame, zero gap"),
    ("I told them that I'll bring the folding tables tomorrow.",
     True, "that-complementizer + unbackshifted I'll"),
    ("I told her I'd put the rebate forms in the mail Monday.",
     True, "base==participle ambiguity fails toward catch (the frame vouches)"),
    # the deny half: each class keeps today's silence
    ("I told her I'd sent the corrected invoice already.",
     False, "irregular participle: 'd = had, the thing is done (narration)"),
    ("I told the super I'd emailed about the leak twice.",
     False, "regular -ed participle: 'd = had"),
    ("I told him I'd never co-sign that loan.",
     False, "negated complement is a refusal, not a promise"),
    ("I told her I'd probably swing by after the gym.",
     False, "probability hedge in the verb slot"),
    ("I told dispatch I'd deal with it.",
     False, "reported deferral idiom over a bare pronoun"),
    ("I told her I'd get back to her after payroll clears.",
     False, "get-back-to meta-communication deferral"),
    ("I told him I'd go.",
     False, "no content after the committed verb (conservative floor)"),
    ("She told me she'd send the spreadsheet tonight.",
     False, "someone else's promise, not the speaker's"),
    ("They told me I'd need a permit for the shed.",
     False, "third-person matrix subject: no first-person frame"),
    ("Oh sure, I told him I'd teleport the samples by noon.",
     False, "open sarcasm frame outranks the promise frame"),
    ("I told her I'd swing by the depot. We'll see.",
     False, "trailing hedge stays utterance-absolute over the promise frame"),
    # adversarial-probe deny families (each closed-class, deny-direction)
    ("I told you I'd finish the slides, didn't I?",
     False, "tag-question retort: a KEPT promise being cited, not an open one"),
    ("Wish I told her I'd come along.",
     False, "counterfactual regret"),
    ("I told him I'd send it and I did.",
     False, "resolved: the loop is already closed"),
    ("I said I'd help with the move but my back gave out.",
     False, "but-failure: narrating why the promise fell through"),
    ("I told her I'd love to but I can't make it.",
     False, "polite refusal wearing a promise frame"),
    ("I promised myself I'd unplug this weekend.",
     False, "a promise to oneself is resolution-talk, not a handoff"),
    ("Every week I told him I'd quit smoking.",
     False, "habitual narration of a pattern"),
    ("I told him I'd do my best.",
     False, "vow idiom: a feeling, not a deliverable"),
    ("I said I'd always listen, and I always do.",
     False, "always-vow"),
    ("I told him I'd rather die than apologize.",
     False, "I'd-rather refusal vent"),
    ("I told them I'd be there for them.",
     False, "emotional be-there-for vow"),
    ("I told him I'd be a better person about deadlines.",
     False, "unanchored be-vow: character talk, not an attend commitment"),
    ("I promised her I'd cry at the wedding either way.",
     False, "vow/vent head verb: a feeling, not a deliverable"),
    # ...while the guards stay structural, not topical:
    ("I told the coach I'd be there by six to set up.",
     True, "be-there with a concrete anchor is an attend commitment"),
    ("The hallway smells like paint again, but I told the super I'd drop off the spare key Saturday.",
     True, "a but BEFORE the frame is discourse contrast, not failure narration"),
]

AMBIENT = {"observed_at": "2026-06-10T07:55:10-07:00"}
# F8+F9 composition: vent clause + binding_send-shaped transfer ("send ... over <rail>"
# has no _HARD money verb, so the harm-line reads it as a send) heard ambiently
TRANSFER_SEND = ("The streamers are Ferda's thing, I told her I'd handle the cups and plates. "
                 "Send Ferda the eighteen over venmo so she can restock tonight.")
RETRACT = "Actually hold off, I want to compare prices first."


class FakeGlass:
    def __init__(self):
        self.entries = []

    def log(self, kind, data):
        self.entries.append((kind, data))

    def kinds(self):
        return [k for k, _ in self.entries]


class FakeScore:
    def __init__(self):
        self.decisions = []

    def record_decision(self, decision, event_id, reason):
        self.decisions.append(decision)

    def record_goal(self, goal_id, outcome, cost):
        pass


def make():
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-clausescope-"))
    bus = Bus()
    for w in (ChannelStub(), MemoryStub(), ConnectorStub(), BrowserStub()):
        bus.register_worker(w)
    gw = ModelGateway()
    glass, score = FakeGlass(), FakeScore()
    orch = Orchestrator(bus, gw, GoalStore(data_dir=tmp), glassbox=glass, scorecard=score,
                        approver=AutoApprover(True))
    pro = ProactiveEngine(bus, gw, orch, glassbox=glass, scorecard=score)
    return bus, glass, orch, pro, score


def triage_pins() -> list:
    tri = Triage(gateway=None)  # stub: deterministic, no tiebreak possible
    fails = []
    for text, want, shape in CASES:
        got = tri.actionable(text)
        if got != want:
            fails.append(f"  [{shape}] expected {'SURVIVE' if want else 'DROP'}: {text!r}")
    if tri.smart_calls != 0:
        fails.append(f"  [cost-spine] smart_calls={tri.smart_calls}, must be 0")
    return fails


class _NoThinkGateway:
    """No .think attribute: forces the live tiebreak's exception path, deterministically
    (no event loop entered, no network, no model)."""


def f11_pins() -> list:
    """Ledger F11: clause-scoping widened the live fail-open tail — an utterance whose
    every clause was consumed by a confident negative used to fall through to _tiebreak,
    which fails OPEN, so a pure vent could reach the decider during a gateway outage.
    Pin: all-clauses-negative -> absolute False even in live mode; the fail-open tail
    stays reserved for lines that matched NOTHING (F6's deliberate high-recall bias)."""
    fails = []
    live = Triage(gateway=_NoThinkGateway(), mode="live")
    pure_vents = [
        "Oh sure. Maybe I'll teleport to the depot.",
        "I'd lose it if the boiler dies tonight. I should just move.",
        "She already handled the venue. I'll deal with that later.",
    ]
    for text in pure_vents:
        if live.actionable(text):
            fails.append(f"  [F11] pure vent must be absolute False in live mode: {text!r}")
    if not live.actionable("The depot smelled like burnt toast this morning."):
        fails.append("  [F11] matched-nothing live line must still fail open to the decider")
    if live.smart_calls != 0:
        fails.append(f"  [F11] smart_calls={live.smart_calls}; the exception path must count 0")
    return fails


def debounce_pins() -> list:
    fails = []
    checks = [
        # F9: binding_send WITH a transfer rail, ambient -> held
        (("Send Yusuf the forty over zelle so he can cover the permit", "binding_send", AMBIENT), True),
        # typed/API stays deliberate -> no debounce hold (the engine blocks money rails immediately)
        (("Send Yusuf the forty over zelle so he can cover the permit", "binding_send", None), False),
        # an ordinary send (no rail) must NOT be debounced
        (("Send the signed lease over to the landlord tonight", "binding_send", AMBIENT), False),
        (("Email the team the new schedule", "binding_send", AMBIENT), False),
        # the original ambient money-transfer hold path is unchanged
        (("Just wire the mason her retainer tonight", "money", AMBIENT), True),
        # any other category never holds, rail or not
        (("Wire the refund over paypal", "calendar_hold", AMBIENT), False),
    ]
    for args, want in checks:
        got = AskDebounce.should_hold(*args)
        if got != want:
            fails.append(f"  should_hold{args} = {got}, want {want}")
    return fails


async def replay_pins() -> list:
    """F9's named regression check: a two-line money-command-then-retraction replay must
    end with ZERO surfaced asks — and the un-deafened command must reach the harm-line
    (held, goal paused) rather than being triage-dropped (F8)."""
    fails = []
    # A) command then retraction -> silence end to end
    bus, glass, orch, pro, score = make()
    await bus.start()
    try:
        out = await pro.on_event(Event(source=EventSource.app, text=TRANSFER_SEND, meta=dict(AMBIENT)))
        if out["decision"] != "held" or out["ask_id"]:
            fails.append(f"  transfer-send must be HELD (heard, not asked): {out}")
        elif orch.store.load(out["goal_id"]).state != GoalState.waiting:
            fails.append("  held goal must stay paused (never executed)")
        out2 = await pro.on_event(Event(source=EventSource.app, text=RETRACT, meta=dict(AMBIENT)))
        if out2["decision"] != "ignore" or out2.get("retracted_goal_ids") != [out["goal_id"]]:
            fails.append(f"  retraction must cancel the held ask: {out2}")
        if "ask_sent" in glass.kinds() or pro.pending or pro.debounce.has_held():
            fails.append("  command-then-retraction replay surfaced an ask; window broken")
        if "ask" in score.decisions:
            fails.append("  scorecard saw an ask decision in the retraction replay")
        if out["goal_id"] and orch.store.load(out["goal_id"]).state != GoalState.failed:
            fails.append("  retracted goal must end failed (silence), never executed")
    finally:
        await bus.stop()
    # B) no retraction -> the same held money transfer hits the terminal block late
    #    (one-way safety: held can only become silence or a block, never an act)
    bus, glass, orch, pro, score = make()
    await bus.start()
    try:
        out = await pro.on_event(Event(source=EventSource.app, text=TRANSFER_SEND, meta=dict(AMBIENT)))
        await pro.on_event(Event(source=EventSource.app, text="The hallway echo in here is unreal.",
                                 meta=dict(AMBIENT)))
        await pro.on_event(Event(source=EventSource.app, text="Bram's desk fan squeaks on every turn.",
                                 meta=dict(AMBIENT)))
        if "ask_blocked" not in glass.kinds() or pro.pending:
            fails.append("  surviving binding_send hold must hit the money wall late")
        if out["goal_id"] and orch.store.load(out["goal_id"]).state != GoalState.failed:
            fails.append("  blocked goal must end failed, never awaiting approval")
    finally:
        await bus.stop()
    return fails


def main() -> int:
    fails = triage_pins() + f11_pins() + debounce_pins() + asyncio.run(replay_pins())
    if fails:
        print(f"FAIL test_triage_clause_scope: {len(fails)} pins broken")
        print("\n".join(fails))
        return 1
    print(f"PASS test_triage_clause_scope: {len(CASES)} triage pins + debounce + replay, 0 smart calls")
    return 0


if __name__ == "__main__":
    sys.exit(main())
