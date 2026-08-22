"""Author proof/ambient/corpus.json — the overheard-speech test set.

WHY A BUILDER AND NOT HAND-EDITED JSON: the balance IS the test. 45% silence,
18+ walks of life, every hard-case kind present, conversations whose turns stay
in order. Those are invariants, and an invariant that is not asserted is a
wish. Running this file re-derives the JSON and refuses to write it if the
composition has drifted.

    ~/.anticipy-rig/venv/bin/python proof/ambient/build_corpus.py

SCHEMA — deliberately overnight/gold_dev.json's vocabulary wherever the two
sets are asking the same question, so numbers stay comparable:

  id            corpus-local stable id ("amb-0001"); overnight used PocketBase
                ids because its lines were real rows. These are written, not
                overheard, so they get their own namespace.
  text          the words, exactly as a recognizer would hand them over.
  gold          ignore | ask | act  — the decision the WORKER stamps on the
                event row (brain/worker.py:2586-2594). overnight/gold_*.json
                labelled a four-way LANE instead; that lane is kept below as
                `gold_lane` so the two corpora can still be read side by side.
  gold_lane     silent | quiet | desk | text — overnight's vocabulary
                (overnight/label_corpus.py:45-68). The mapping is not cosmetic:
                worker.py:1971-1984 files quiet background work as
                decision="ignore" CARRYING A GOAL, so silent and quiet share a
                stamp and are only told apart by whether events.goal came back
                empty.
  goal          expected-goal description for act/ask; "" for silent ignores.
  family        task family (food, vehicle, compliance, ...); "" for ignores.
  field         walk of life the line comes out of.
  whose         owner | other | machine | nobody — overnight's `whose`, the
                axis that actually separates "his errand" from "her promise"
                from "he is voice-typing".
  why           <8 words, overnight's field, same purpose.
  register      how it was said: realisation | worry | complaint | aside |
                thinking_aloud | direct | fragment. The product claim is that
                she catches intent with NO imperative, so the register has to
                be recorded or that claim cannot be measured.
  hard          bool — deliberately adversarial case.
  hard_kind     other_commitment | hypothetical | past_done | retraction |
                ack | in_flight | question_to_person | media | asr_mush
  convo         conversation id, "" for standalone lines.
  turn          1-based position inside the conversation, 0 for standalone.
  source        "authored" — overnight's `source` was "model"/"anchor". These
                lines were written against the rubric rather than sampled from
                a real day, and saying so is the honest version.
"""
from __future__ import annotations

import json
import os
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))

_LANE_FOR = {"ignore": "silent", "ask": "text", "act": "desk"}

ROWS: list[dict] = []


def U(text, gold, *, goal="", family="", field="none", whose="owner", why="",
      register="direct", hard=False, hard_kind="", convo="", turn=0, lane=""):
    ROWS.append({
        "text": text, "gold": gold,
        "gold_lane": lane or _LANE_FOR[gold],
        "goal": goal, "family": family, "field": field, "whose": whose,
        "why": why, "register": register, "hard": hard, "hard_kind": hard_kind,
        "convo": convo, "turn": turn, "source": "authored",
    })


# =====================================================================
# 1. THE ANCHOR. The owner's own example, verbatim. Ambient, no
#    imperative, no wake word — the whole product in one sentence.
# =====================================================================
U("Oh my goodness, I forgot to cook for my kids this afternoon.", "act",
  goal="arrange food for the kids this afternoon",
  family="food", field="parent", why="his kids, unmet need, today",
  register="realisation")

# =====================================================================
# 2. ACT / ASK — the same register as the anchor, across walks of life.
#    A realisation, a worry, a complaint, an aside. Never an instruction.
# =====================================================================

# ---- finance -------------------------------------------------------
U("Damn, the Hendricks review is Thursday and I still have not pulled the Q3 numbers.",
  "act", goal="assemble Q3 performance figures for the Hendricks client review",
  family="work_deliverable", field="finance", why="his deliverable, dated deadline",
  register="realisation")
U("I keep meaning to re-run the retirement projection on the Alvarez file before we meet.",
  "act", goal="re-run the retirement projection for the Alvarez file",
  family="work_deliverable", field="finance", why="his task, repeatedly deferred",
  register="worry")
U("I should get the CFA level three booked but I have lost track of the window.",
  "ask", goal="book the CFA level three exam",
  family="compliance", field="finance", why="real intent, exam window unknown",
  register="thinking_aloud")

# ---- accounting ----------------------------------------------------
U("Oh no, the VAT return is due on the seventh and I have not touched the card statements.",
  "act", goal="reconcile the card statements before the VAT return deadline",
  family="compliance", field="accounting", why="his filing, hard deadline",
  register="realisation")
U("I told Priya I would send her the payroll journal and it completely went out of my head.",
  "act", goal="send Priya the payroll journal",
  family="communication", field="accounting", why="his promise to a person",
  register="realisation")
U("The practice indemnity renewal quote came in at nearly double what we paid last year.",
  "act", goal="get alternative professional indemnity quotes",
  family="finance_admin", field="accounting", why="cost shock invites shopping around",
  register="complaint")

# ---- medicine ------------------------------------------------------
U("My medical indemnity lapses next month and I have not looked at renewing it.",
  "act", goal="renew medical indemnity cover before it lapses",
  family="compliance", field="medicine", why="his cover, dated lapse",
  register="worry")
U("Somebody needs to chase the lab about Mr Okonkwo's bloods, I think they went to the wrong practice.",
  "ask", goal="chase the laboratory about a misrouted blood result",
  family="communication", field="medicine", why="real need, no lab named",
  register="worry")
U("The appraisal portfolio deadline is creeping up on me again.",
  "act", goal="look up the appraisal portfolio deadline and what is outstanding",
  family="compliance", field="medicine", why="his revalidation obligation",
  register="worry")

# ---- nursing -------------------------------------------------------
U("My revalidation is due and I have not logged a single hour of CPD.",
  "act", goal="look up NMC revalidation requirements and the deadline",
  family="compliance", field="nursing", why="his registration at risk",
  register="realisation")
U("I am on nights all next week and I have not sorted anything for the kids.",
  "act", goal="arrange childcare for next week's night shifts",
  family="childcare", field="nursing", why="dated need, nobody else named",
  register="worry")
U("These agency shifts pay more than I do and I am the one holding the ward together.",
  "ignore", field="nursing", why="venting, no obligation created",
  register="complaint")

# ---- law -----------------------------------------------------------
U("The bundle for the Prentice hearing has to be filed by four and I am nowhere near.",
  "act", goal="prepare and file the hearing bundle for the Prentice matter by four",
  family="work_deliverable", field="law", why="his filing, hard deadline",
  register="worry")
U("I ought to get the practising certificate renewed, the window opens about now.",
  "ask", goal="renew the practising certificate",
  family="compliance", field="law", why="intent real, window date unknown",
  register="thinking_aloud")
U("The client care letter for the Duffy file never went out, did it.",
  "act", goal="send the client care letter on the Duffy file",
  family="communication", field="law", why="his omission, named file",
  register="realisation")

# ---- civil engineering ---------------------------------------------
U("The site cannot pour on Friday if that rebar inspection is not booked.",
  "act", goal="book the rebar inspection before Friday's pour",
  family="scheduling", field="civil_engineering", why="his blocker, dated",
  register="worry")
U("The revised drainage calcs still have not gone to the contractor and design freeze is Monday.",
  "act", goal="send the revised drainage calculations to the contractor",
  family="communication", field="civil_engineering", why="his deliverable, dated freeze",
  register="realisation")

# ---- mechanical engineering ----------------------------------------
U("I keep putting off sending the rig two vibration data to the bearing supplier.",
  "act", goal="send the rig two vibration data to the bearing supplier",
  family="communication", field="mechanical_engineering",
  why="his task, repeatedly deferred", register="complaint")
U("We are going to be short on the test cell booking if nobody puts a date in.",
  "ask", goal="book test cell time",
  family="scheduling", field="mechanical_engineering", why="need real, date unknown",
  register="worry")

# ---- software engineering ------------------------------------------
U("Staging is throwing cert errors, I bet I never renewed that domain.",
  "act", goal="check the domain and certificate expiry for the staging environment",
  family="admin", field="software_engineering", why="diagnosable cause, his account",
  register="realisation")
U("I said I would tell Dan when his pull request lands and I have gone quiet on him.",
  "act", goal="message Dan about when his pull request will be reviewed",
  family="communication", field="software_engineering", why="his promise to a person",
  register="realisation")
U("Whoever wrote this test suite hated joy.",
  "ignore", field="software_engineering", why="joke, no obligation",
  register="complaint")

# ---- teaching ------------------------------------------------------
U("Parents evening slots go live tomorrow and I have not set my availability.",
  "act", goal="set parents evening availability before slots open",
  family="scheduling", field="teaching", why="his admin, dated",
  register="realisation")
U("We are four copies short of the Steinbeck for Year Nine.",
  "act", goal="order additional copies of the Steinbeck set text for Year Nine",
  family="procurement", field="teaching", why="concrete shortfall, his class",
  register="aside")
U("Half of them did not even open the booklet.",
  "ignore", field="teaching", why="venting about a class", register="complaint")

# ---- plumbing ------------------------------------------------------
U("I am going to run out of twenty two mil compression fittings before Thursday's job.",
  "act", goal="order twenty two millimetre compression fittings before Thursday",
  family="procurement", field="plumbing", why="concrete shortfall, dated job",
  register="realisation")
U("The van's MOT is end of the month and I have not rung anyone.",
  "act", goal="book the van in for its MOT before the end of the month",
  family="vehicle", field="plumbing", why="his vehicle, dated expiry",
  register="worry")
U("That loft conversion was a nightmare, never again.",
  "ignore", field="plumbing", why="venting about finished work", register="complaint")

# ---- electrical ----------------------------------------------------
U("My eighteenth edition update expires this year and courses book up fast.",
  "act", goal="find and book an eighteenth edition update course",
  family="compliance", field="electrical", why="his qualification, dated",
  register="worry")
U("The calibration certificate on the loop tester ran out in March.",
  "act", goal="arrange recalibration of the loop tester",
  family="compliance", field="electrical", why="his kit out of certification",
  register="realisation")

# ---- HVAC ----------------------------------------------------------
U("The Mitsubishi units for the Croydon install have not been ordered, have they.",
  "act", goal="order the Mitsubishi units for the Croydon installation",
  family="procurement", field="hvac", why="his order, named job",
  register="realisation")
U("Refrigerant prices are insane this year.",
  "ignore", field="hvac", why="market grumble, no action", register="complaint")

# ---- retail --------------------------------------------------------
U("We are going to be short on till float over the bank holiday.",
  "act", goal="arrange extra till float for the bank holiday weekend",
  family="admin", field="retail", why="foreseeable shortfall, his store",
  register="worry")
U("The rota for next week still is not up and everyone keeps asking me.",
  "act", goal="publish next week's staff rota",
  family="scheduling", field="retail", why="his job, staff waiting",
  register="complaint")
U("Third shoplifter this week.",
  "ignore", field="retail", why="observation, no obligation", register="aside")

# ---- logistics and trucking ----------------------------------------
U("My digital tacho card runs out in about six weeks.",
  "act", goal="apply to renew the digital tachograph card",
  family="compliance", field="logistics_trucking", why="his licence, dated expiry",
  register="thinking_aloud")
U("I cannot do the Dover run until the trailer has had its brake test.",
  "act", goal="book the trailer brake test before the Dover run",
  family="vehicle", field="logistics_trucking", why="his blocker, named run",
  register="worry")
U("The M6 was solid from junction twelve.",
  "ignore", field="logistics_trucking", why="past traffic, no action",
  register="aside")

# ---- farming -------------------------------------------------------
U("If the BPS claim is not in by the fifteenth I lose the whole payment.",
  "act", goal="submit the Basic Payment Scheme claim before the fifteenth",
  family="compliance", field="farming", why="his claim, hard deadline",
  register="worry")
U("The TB test is due and I still have not rung the vet.",
  "act", goal="book the vet for the herd TB test",
  family="pets", field="farming", why="his herd, statutory test",
  register="realisation")
U("Rain is not letting up at all.",
  "ignore", field="farming", why="weather remark", register="aside")

# ---- hospitality ---------------------------------------------------
U("We are catering forty on Saturday and the fish order is still not confirmed.",
  "act", goal="confirm the fish order for Saturday's forty covers",
  family="procurement", field="hospitality", why="his service, dated",
  register="worry")
U("Someone really should chase the linen company about Tuesday.",
  "ask", goal="chase the linen supplier about the Tuesday delivery",
  family="communication", field="hospitality", why="need real, supplier unnamed",
  register="complaint")
U("Table six sent it back twice.",
  "ignore", field="hospitality", why="service grumble, no action", register="aside")

# ---- real estate ---------------------------------------------------
U("The EPC on the Kingsway flat expired, I cannot list it without one.",
  "act", goal="arrange a new EPC for the Kingsway flat",
  family="property", field="real_estate", why="his listing blocked",
  register="realisation")
U("The Hartleys cannot do Thursday for the viewing after all.",
  "act", goal="rearrange the Hartley viewing away from Thursday",
  family="scheduling", field="real_estate", why="his diary, named clients",
  register="aside")
U("That vendor is never going to accept.",
  "ignore", field="real_estate", why="opinion about a deal", register="complaint")

# ---- insurance -----------------------------------------------------
U("The broker never sent the revised schedule for the fleet policy.",
  "act", goal="chase the broker for the revised fleet policy schedule",
  family="communication", field="insurance", why="outstanding item on his policy",
  register="complaint")
U("I have not done the CII structured hours for this year at all.",
  "act", goal="find CII structured CPD hours to complete this year",
  family="compliance", field="insurance", why="his CPD requirement",
  register="realisation")

# ---- government and public admin -----------------------------------
U("The FOI response deadline is twenty working days and we are on eighteen.",
  "act", goal="get the FOI response finished before the twenty working day deadline",
  family="compliance", field="government_admin", why="statutory clock nearly out",
  register="worry")
U("Another reorganisation, marvellous.",
  "ignore", field="government_admin", why="sarcastic venting", register="complaint")

# ---- student -------------------------------------------------------
U("My ethics form was supposed to go in last Friday and it is still sat in drafts.",
  "act", goal="submit the overdue dissertation ethics form",
  family="education", field="student", why="his submission, already late",
  register="realisation")
U("Student finance still have not paid and rent goes out on the first.",
  "act", goal="find out how to chase a late student finance payment",
  family="finance_admin", field="student", why="his money, dated pressure",
  register="worry")
U("I have read the same paragraph four times.",
  "ignore", field="student", why="tiredness, no obligation", register="complaint")

# ---- parent --------------------------------------------------------
U("World book day is Thursday and we have not got a costume.",
  "act", goal="sort a world book day costume before Thursday",
  family="shopping", field="parent", why="his child, dated need",
  register="realisation")
U("Ellie's swimming subs are overdue again.",
  "act", goal="pay the overdue swimming subscription for Ellie",
  family="finance_admin", field="parent", why="his child, overdue payment",
  register="complaint")
U("He has been on that tablet for three hours.",
  "ignore", field="parent", why="observation, no errand", register="complaint")

# ---- retiree -------------------------------------------------------
U("My prescription is down to two days and the pharmacy shut early.",
  "act", goal="arrange a repeat prescription before it runs out",
  family="health_admin", field="retiree", why="his medication, running out",
  register="worry")
U("That TV licence renewal letter has been on the side a fortnight.",
  "act", goal="renew the TV licence",
  family="admin", field="retiree", why="his renewal, being avoided",
  register="realisation")
U("Bowls was cancelled, wet green.",
  "ignore", field="retiree", why="past event, no action", register="aside")

# ---- no professional context ---------------------------------------
U("I have just realised the car insurance ran out on the twelfth.",
  "act", goal="sort car insurance cover that expired on the twelfth",
  family="vehicle", field="none", why="his cover, already lapsed",
  register="realisation")
U("There is a leak under the sink and it is getting worse.",
  "act", goal="get a plumber out to a worsening leak under the sink",
  family="home_maintenance", field="none", why="worsening problem in his home",
  register="worry")
U("I would love to get away for a weekend but I have no idea what is affordable.",
  "ask", goal="find affordable weekend away options",
  family="travel", field="none", why="wish plus a blocker, no dates",
  register="thinking_aloud")
U("The washing machine has started making that noise again.",
  "act", goal="arrange a repair for the washing machine",
  family="home_maintenance", field="none", why="recurring fault in his home",
  register="complaint")
U("Mum's birthday is Saturday and I have absolutely nothing for her.",
  "act", goal="find and order a birthday present for his mother by Saturday",
  family="gifts", field="none", why="dated, his family, nothing bought",
  register="worry")

# ---- veterinary ----------------------------------------------------
U("The practice controlled drugs register audit is overdue by a fortnight.",
  "act", goal="complete the overdue controlled drugs register audit",
  family="compliance", field="veterinary", why="his audit, overdue",
  register="realisation")
U("We are nearly out of the feline vaccine and the rep never called back.",
  "act", goal="reorder feline vaccine stock and chase the supplier rep",
  family="procurement", field="veterinary", why="stock out, supplier silent",
  register="worry")

# ---- journalism ----------------------------------------------------
U("Copy deadline is six and I have not got the second source to say yes.",
  "act", goal="secure a second source before the six o'clock copy deadline",
  family="work_deliverable", field="journalism", why="his copy, hard deadline",
  register="worry")
U("My press card expired and I need it for the conference.",
  "act", goal="renew the press card before the conference",
  family="compliance", field="journalism", why="his accreditation, dated need",
  register="realisation")

# ---- fitness and personal training ---------------------------------
U("My first aid certificate runs out before the summer bootcamps start.",
  "act", goal="book a first aid requalification before the summer bootcamps",
  family="compliance", field="fitness", why="his certification, dated",
  register="worry")
U("Three clients cancelled on me this week.",
  "ignore", field="fitness", why="venting about the week", register="complaint")

# ---- carpentry -----------------------------------------------------
U("The kitchen worktops are on a ten day lead and I promised them fitted by the end of the month.",
  "act", goal="order the kitchen worktops accounting for the ten day lead time",
  family="procurement", field="carpentry", why="his promise, lead time bites",
  register="worry")

# ---- social work ---------------------------------------------------
U("The case review write up was due yesterday and I have not opened the file.",
  "act", goal="complete the overdue case review write up",
  family="work_deliverable", field="social_work", why="his record, already late",
  register="realisation")

# ---- aviation ------------------------------------------------------
U("My medical certificate lapses in November and the AME books up months out.",
  "act", goal="book an aviation medical examination before November",
  family="compliance", field="aviation", why="his licence, long lead booking",
  register="worry")

# ---- pharmacy ------------------------------------------------------
U("The CD cabinet key audit has not been signed off since I went on leave.",
  "act", goal="complete the controlled drugs cabinet key audit sign off",
  family="compliance", field="pharmacy", why="his sign off, lapsed",
  register="realisation")

# ---- hairdressing --------------------------------------------------
U("I am nearly out of the six point six tint and Saturday is packed.",
  "act", goal="reorder the six point six tint before Saturday",
  family="procurement", field="hairdressing", why="stock out before a busy day",
  register="worry")

# ---- charity and non profit ----------------------------------------
U("The Charity Commission annual return is open and nobody has started it.",
  "act", goal="start the Charity Commission annual return",
  family="compliance", field="charity", why="his organisation, statutory return",
  register="realisation")
# =====================================================================
# 2b. MORE ACT / ASK. The corpus needs the noise floor at ~45%, and a
#     45% floor with only seventy errands would mean the errands were
#     the thin part of the test. Depth per walk of life matters as much
#     as breadth: one line per trade measures whether the WORD is
#     recognised, several measure whether the SITUATION is.
# =====================================================================

# ---- finance -------------------------------------------------------
U("The ISA allowance resets in April and I have not used half of mine.",
  "act", goal="review the unused ISA allowance before the April reset",
  family="finance_admin", field="finance", why="his allowance, dated reset",
  register="realisation")
U("My FCA fee invoice is sat unopened somewhere.",
  "act", goal="locate and pay the FCA fee invoice",
  family="finance_admin", field="finance", why="his regulator fee, unpaid",
  register="aside")

# ---- accounting ----------------------------------------------------
U("The confirmation statement is due and I have not checked the PSC register.",
  "act", goal="check the PSC register and file the confirmation statement",
  family="compliance", field="accounting", why="his filing, dated",
  register="worry")
U("The client keeps sending receipts as photos and I have nowhere sensible to put them.",
  "ask", goal="set up a way to collect client receipt photos",
  family="admin", field="accounting", why="real problem, no tool chosen",
  register="complaint")

# ---- medicine ------------------------------------------------------
U("The flu jab rota needs sorting before October and nobody has started it.",
  "act", goal="set up the autumn flu vaccination rota",
  family="scheduling", field="medicine", why="his practice, seasonal deadline",
  register="worry")
U("The defibrillator pads in room three are out of date.",
  "act", goal="order replacement defibrillator pads",
  family="procurement", field="medicine", why="safety kit expired",
  register="realisation")

# ---- nursing -------------------------------------------------------
U("My DBS is three years old, I think it needs redoing for the bank shifts.",
  "act", goal="renew the DBS check needed for bank shifts",
  family="compliance", field="nursing", why="his clearance, work blocked",
  register="thinking_aloud")
U("The ward has run out of the small gloves again.",
  "act", goal="reorder small size gloves for the ward",
  family="procurement", field="nursing", why="recurring stock out",
  register="complaint")

# ---- law -----------------------------------------------------------
U("The anti money laundering training has not been assigned to anyone in the team.",
  "act", goal="assign the AML training module to the team",
  family="compliance", field="law", why="his firm, mandatory training",
  register="realisation")
U("Counsel's fee note is unpaid and they will stop taking my calls.",
  "act", goal="get counsel's fee note paid",
  family="finance_admin", field="law", why="his liability, relationship at risk",
  register="worry")

# ---- civil engineering ---------------------------------------------
U("The temporary works design has not been signed by anyone competent.",
  "act", goal="get the temporary works design signed by a competent engineer",
  family="compliance", field="civil_engineering", why="unsigned safety-critical design",
  register="worry")
U("We cannot pour at the weekend without the road closure permit.",
  "act", goal="apply for the weekend road closure permit",
  family="compliance", field="civil_engineering", why="his blocker, dated",
  register="realisation")

# ---- mechanical engineering ----------------------------------------
U("The pressure vessel inspection is due and the paperwork is nowhere to be found.",
  "act", goal="arrange the pressure vessel inspection and find the records",
  family="compliance", field="mechanical_engineering", why="statutory inspection due",
  register="worry")
U("That gearbox supplier never sent the datasheet.",
  "act", goal="chase the gearbox supplier for the datasheet",
  family="communication", field="mechanical_engineering", why="outstanding, blocks him",
  register="complaint")

# ---- software engineering ------------------------------------------
U("The SOC 2 evidence collection is due next month and nobody owns it.",
  "act", goal="start the SOC 2 evidence collection",
  family="compliance", field="software_engineering", why="dated, unowned",
  register="worry")
U("The on call rota has me down for Christmas week again.",
  "act", goal="get the Christmas week on call shift swapped",
  family="scheduling", field="software_engineering", why="his shift, wants it changed",
  register="complaint")
U("I still have not booked the conference and early bird ends Friday.",
  "act", goal="book the conference before the early bird deadline on Friday",
  family="travel", field="software_engineering", why="his booking, price deadline",
  register="realisation")

# ---- teaching ------------------------------------------------------
U("The trip risk assessment has to be with the head before the letters go out.",
  "act", goal="complete the trip risk assessment for the head teacher",
  family="work_deliverable", field="teaching", why="his paperwork blocks the trip",
  register="worry")
U("I need cover for the Thursday I am away on the course.",
  "act", goal="arrange supply cover for Thursday",
  family="scheduling", field="teaching", why="his absence, class uncovered",
  register="realisation")

# ---- plumbing ------------------------------------------------------
U("Gas Safe renewal is this month and I always leave it far too late.",
  "act", goal="renew the Gas Safe registration this month",
  family="compliance", field="plumbing", why="his registration, dated",
  register="worry")
U("The customer in Beeston still has not paid the deposit invoice.",
  "act", goal="chase the unpaid deposit invoice from the Beeston customer",
  family="finance_admin", field="plumbing", why="his money, overdue",
  register="complaint")

# ---- electrical ----------------------------------------------------
U("The apprentice needs his college enrolment sorted before term starts.",
  "act", goal="sort the apprentice's college enrolment before term",
  family="education", field="electrical", why="his apprentice, dated",
  register="realisation")
U("I promised the shop a quote for the rewire and it is still only in my head.",
  "act", goal="write and send the rewire quote to the shop",
  family="work_deliverable", field="electrical", why="his promise, undelivered",
  register="realisation")

# ---- HVAC ----------------------------------------------------------
U("My F gas certificate expires in the spring.",
  "act", goal="renew the F gas certification before spring",
  family="compliance", field="hvac", why="his certification, dated",
  register="thinking_aloud")
U("Croydon want a service contract quote by the end of the week.",
  "act", goal="prepare the Croydon service contract quote by end of week",
  family="work_deliverable", field="hvac", why="his quote, dated",
  register="aside")

# ---- retail --------------------------------------------------------
U("The card machine contract auto renews in a fortnight at a worse rate.",
  "act", goal="review or switch the card machine contract before it auto renews",
  family="finance_admin", field="retail", why="dated auto renewal, worse terms",
  register="worry")
U("We have nothing booked for the Christmas window display.",
  "act", goal="arrange the Christmas window display",
  family="procurement", field="retail", why="seasonal, nothing arranged",
  register="realisation")

# ---- logistics and trucking ----------------------------------------
U("My Driver CPC hours are seven short and the cutoff is September.",
  "act", goal="book the outstanding Driver CPC hours before September",
  family="compliance", field="logistics_trucking", why="his licence, dated shortfall",
  register="worry")
U("I have not claimed the night out expenses for two months.",
  "act", goal="submit two months of night out expense claims",
  family="finance_admin", field="logistics_trucking", why="his money, unclaimed",
  register="realisation")

# ---- farming -------------------------------------------------------
U("The sprayer test certificate runs out before harvest.",
  "act", goal="book the sprayer test before harvest",
  family="compliance", field="farming", why="his kit, seasonal deadline",
  register="worry")
U("The fencing on the top field is going to let them straight through.",
  "act", goal="arrange fencing repair on the top field",
  family="home_maintenance", field="farming", why="foreseeable escape, his stock",
  register="worry")

# ---- hospitality ---------------------------------------------------
U("The hygiene re-inspection could come any week and the fridge log is a mess.",
  "act", goal="bring the fridge temperature log up to date before re-inspection",
  family="compliance", field="hospitality", why="his records, inspection risk",
  register="worry")
U("We have a wedding party of sixty and no second chef booked.",
  "act", goal="book a second chef for the wedding party of sixty",
  family="scheduling", field="hospitality", why="his service, understaffed",
  register="realisation")

# ---- real estate ---------------------------------------------------
U("The client money account audit needs an accountant and I have not appointed one.",
  "act", goal="appoint an accountant for the client money account audit",
  family="compliance", field="real_estate", why="his obligation, unappointed",
  register="realisation")
U("The board outside the Willow Road place has been down since the storm.",
  "act", goal="get the Willow Road for sale board reinstated",
  family="property", field="real_estate", why="his listing, lost visibility",
  register="complaint")

# ---- insurance -----------------------------------------------------
U("The flood cover renews next week and they still have not sent the survey.",
  "act", goal="chase the survey needed before the flood cover renewal",
  family="communication", field="insurance", why="dated renewal, missing document",
  register="worry")
U("The complaints return has to be filed and the spreadsheet is out of date.",
  "act", goal="update the complaints spreadsheet and file the return",
  family="compliance", field="insurance", why="his return, stale data",
  register="realisation")

# ---- government and public admin -----------------------------------
U("The equality impact assessment for the new policy has not been started.",
  "act", goal="start the equality impact assessment for the new policy",
  family="work_deliverable", field="government_admin", why="required, unstarted",
  register="realisation")
U("Committee papers have to be published five clear days before and it is Thursday.",
  "act", goal="publish the committee papers within the five clear day rule",
  family="compliance", field="government_admin", why="statutory notice period",
  register="worry")

# ---- student -------------------------------------------------------
U("The library fine is stopping me getting my results.",
  "act", goal="pay the library fine blocking the results",
  family="finance_admin", field="student", why="his fine, blocking him",
  register="complaint")
U("Module registration closes Friday and I have not picked anything.",
  "act", goal="register for next year's modules before Friday",
  family="education", field="student", why="his registration, dated",
  register="realisation")
U("My railcard expired so every journey has cost me a fortune.",
  "act", goal="renew the expired railcard",
  family="travel", field="student", why="his card, costing him money",
  register="complaint")

# ---- parent --------------------------------------------------------
U("The school trip deposit was due last Wednesday.",
  "act", goal="pay the overdue school trip deposit",
  family="finance_admin", field="parent", why="his payment, already late",
  register="realisation")
U("We have not booked anything for half term and everything will be gone.",
  "act", goal="find and book something for the children over half term",
  family="childcare", field="parent", why="dated, nothing arranged",
  register="worry")
U("His inhaler is nearly empty and school need a spare one.",
  "act", goal="order a repeat inhaler and a spare for school",
  family="health_admin", field="parent", why="his child, medication low",
  register="worry")

# ---- retiree -------------------------------------------------------
U("The boiler service plan letter says they will cancel if I do not reply.",
  "act", goal="respond to the boiler service plan renewal letter",
  family="home_maintenance", field="retiree", why="his cover at risk",
  register="worry")
U("The single person council tax discount never got applied.",
  "act", goal="claim the single person council tax discount",
  family="finance_admin", field="retiree", why="his entitlement, unclaimed",
  register="complaint")

# ---- no professional context ---------------------------------------
U("The passport expires in four months and Spain want six.",
  "act", goal="renew the passport before travelling to Spain",
  family="travel", field="none", why="his document, blocks travel",
  register="realisation")
U("The gutter overflows every single time it rains.",
  "act", goal="get the overflowing gutter cleared or repaired",
  family="home_maintenance", field="none", why="recurring fault, his house",
  register="complaint")
U("The dentist has been sending me reminders since March.",
  "act", goal="book the overdue dental check up",
  family="health_admin", field="none", why="his appointment, long overdue",
  register="aside")
U("The gym has been taking money off me since I stopped going.",
  "act", goal="cancel the unused gym membership",
  family="finance_admin", field="none", why="his money, wasted monthly",
  register="complaint")
U("I want the cat booked in for the booster but I never remember when they are open.",
  "ask", goal="book the cat's booster vaccination",
  family="pets", field="none", why="intent real, practice hours unknown",
  register="thinking_aloud")
U("The smoke alarm has been chirping for a week now.",
  "act", goal="replace the smoke alarm battery or the unit",
  family="home_maintenance", field="none", why="safety device failing",
  register="complaint")
U("The broadband contract ended so we are on the out of contract rate.",
  "act", goal="switch or renegotiate the out of contract broadband deal",
  family="finance_admin", field="none", why="paying more, easily fixed",
  register="realisation")
U("I have not filed my self assessment and January is not that far off.",
  "act", goal="prepare and file the self assessment tax return",
  family="compliance", field="none", why="his return, dated deadline",
  register="worry")
U("Both the kids' passports run out before the summer.",
  "act", goal="renew both children's passports before summer",
  family="travel", field="parent", why="his children, dated expiry",
  register="realisation")
U("We never claimed on that flight delay back in June.",
  "act", goal="submit a flight delay compensation claim for the June flight",
  family="finance_admin", field="none", why="his claim, unclaimed",
  register="aside")
U("The freezer is making that clicking noise and it is full of food.",
  "act", goal="get the freezer looked at before it fails",
  family="home_maintenance", field="none", why="failing appliance, food at risk",
  register="worry")
U("The dog is due his booster and the tick treatment ran out.",
  "act", goal="book the dog's booster and reorder tick treatment",
  family="pets", field="none", why="his dog, both overdue",
  register="realisation")
U("We said we would send Nan photos and it has been months.",
  "act", goal="send photographs to Nan",
  family="communication", field="none", why="his promise, long unmet",
  register="realisation")
U("The recycling calendar changed and we keep missing the collection.",
  "act", goal="find the new recycling collection schedule",
  family="admin", field="none", why="recurring miss, easily answered",
  register="complaint")
U("I should probably sort life insurance now there is a mortgage, but I do not know where to start.",
  "ask", goal="look into life insurance options",
  family="finance_admin", field="none", why="real intent, no parameters",
  register="thinking_aloud")
U("We need to do something about the car, it is costing more than it is worth.",
  "ask", goal="decide whether to repair or replace the car",
  family="vehicle", field="none", why="real problem, decision not made",
  register="complaint")
U("I want to move my pension somewhere sensible.",
  "ask", goal="review pension transfer options",
  family="finance_admin", field="none", why="intent real, nothing specified",
  register="thinking_aloud")
U("The kids need something to do in the holidays and I have not looked at anything.",
  "ask", goal="find holiday activities for the children",
  family="childcare", field="parent", why="need real, no dates or budget",
  register="worry")
U("I ought to see someone about my back but I do not know if that is the GP or a physio.",
  "ask", goal="arrange care for a bad back",
  family="health_admin", field="none", why="intent real, route unknown",
  register="thinking_aloud")

# ---- veterinary ----------------------------------------------------
U("The RCVS fee is due and the reminder went to my old address.",
  "act", goal="pay the RCVS registration fee and update the address",
  family="compliance", field="veterinary", why="his registration, misrouted notice",
  register="realisation")
U("The radiation protection review on the x ray machine is overdue.",
  "act", goal="arrange the overdue radiation protection review",
  family="compliance", field="veterinary", why="statutory review, overdue",
  register="worry")

# ---- journalism ----------------------------------------------------
U("The FOI I put in back in June has had no response at all.",
  "act", goal="chase the unanswered FOI request from June",
  family="communication", field="journalism", why="his request, ignored",
  register="complaint")
U("The shorthand refresher is a condition of the contract and I have not booked it.",
  "act", goal="book the shorthand refresher course",
  family="education", field="journalism", why="contractual, unbooked",
  register="realisation")

# ---- fitness -------------------------------------------------------
U("My public liability renews on the first and I have not compared anything.",
  "act", goal="compare public liability insurance quotes before the first",
  family="finance_admin", field="fitness", why="his cover, dated renewal",
  register="worry")
U("The studio have double booked me on Saturday morning.",
  "act", goal="resolve the Saturday morning studio double booking",
  family="scheduling", field="fitness", why="his session, clash",
  register="complaint")

# ---- carpentry -----------------------------------------------------
U("My CSCS card runs out in November and they will not let me on site without it.",
  "act", goal="renew the CSCS card before November",
  family="compliance", field="carpentry", why="his card, blocks work",
  register="worry")
U("That last invoice is forty days overdue now.",
  "act", goal="chase the invoice that is forty days overdue",
  family="finance_admin", field="carpentry", why="his money, long overdue",
  register="complaint")

# ---- social work ---------------------------------------------------
U("The court report has to be filed before the hearing and I am two days behind.",
  "act", goal="finish and file the court report before the hearing",
  family="work_deliverable", field="social_work", why="his report, behind schedule",
  register="worry")
U("My supervision has not happened for three months.",
  "act", goal="arrange an overdue supervision session",
  family="scheduling", field="social_work", why="his entitlement, lapsed",
  register="realisation")

# ---- aviation ------------------------------------------------------
U("My proficiency check is due and the examiner is booked out for weeks.",
  "act", goal="book a licence proficiency check with an examiner",
  family="compliance", field="aviation", why="his licence, long lead time",
  register="worry")
U("The club want the annual fee before the end of the month.",
  "act", goal="pay the flying club annual fee before month end",
  family="finance_admin", field="aviation", why="his membership, dated",
  register="aside")

# ---- pharmacy ------------------------------------------------------
U("The NHS claim submission window closes on the fifth.",
  "act", goal="submit the NHS claim before the fifth",
  family="compliance", field="pharmacy", why="his claim, hard cutoff",
  register="worry")
U("We are out of the paediatric amoxicillin and the wholesaler is on quota.",
  "act", goal="source paediatric amoxicillin suspension from another supplier",
  family="procurement", field="pharmacy", why="stock out, supply constrained",
  register="worry")

# ---- hairdressing --------------------------------------------------
U("The salon insurance certificate has to be on the wall and I cannot find it.",
  "act", goal="obtain a copy of the salon insurance certificate",
  family="compliance", field="hairdressing", why="required on display, missing",
  register="complaint")
U("I keep turning colour correction work away because I never did the course.",
  "act", goal="find and book a colour correction course",
  family="education", field="hairdressing", why="lost work, fixable gap",
  register="complaint")

# ---- charity -------------------------------------------------------
U("The grant report is due to the funder at the end of the month.",
  "act", goal="prepare the grant report for the funder",
  family="work_deliverable", field="charity", why="his report, dated",
  register="worry")
U("The DBS checks for the new volunteers have not been started.",
  "act", goal="start DBS checks for the new volunteers",
  family="compliance", field="charity", why="required before they start",
  register="realisation")

# ---- architecture --------------------------------------------------
U("The planning submission needs the daylight study and nobody has commissioned it.",
  "act", goal="commission the daylight study for the planning submission",
  family="procurement", field="architecture", why="blocks his submission",
  register="realisation")
U("My ARB registration fee notice arrived and I put it straight in a drawer.",
  "act", goal="pay the ARB registration fee",
  family="compliance", field="architecture", why="his registration, avoided",
  register="aside")

# ---- dentistry -----------------------------------------------------
U("The compressor service is overdue and if it goes we close for the day.",
  "act", goal="book the overdue dental compressor service",
  family="home_maintenance", field="dentistry", why="single point of failure",
  register="worry")
U("My indemnity band changed and I never told them about the implant work.",
  "act", goal="notify the indemnity provider about the implant work",
  family="compliance", field="dentistry", why="cover may be invalid",
  register="realisation")

# ---- emergency services --------------------------------------------
U("My protective equipment is out of test and nobody has chased it.",
  "act", goal="get the out of test protective equipment retested",
  family="compliance", field="emergency_services", why="his kit, out of test",
  register="worry")
U("The court warning for Thursday lands on my rest day.",
  "act", goal="resolve the court warning clashing with the rest day",
  family="scheduling", field="emergency_services", why="his duty clash",
  register="complaint")

# ---- food production -----------------------------------------------
U("The allergen matrix has not been updated since we changed supplier.",
  "act", goal="update the allergen matrix for the new supplier",
  family="compliance", field="food_production", why="safety document stale",
  register="realisation")

# ---- security ------------------------------------------------------
U("My SIA licence expires in three months and the renewal takes eight weeks.",
  "act", goal="start the SIA licence renewal now",
  family="compliance", field="security", why="lead time nearly exceeds runway",
  register="worry")

# ---- childcare and nursery -----------------------------------------
U("Two of the room leaders need their paediatric first aid redone.",
  "act", goal="book paediatric first aid requalification for two staff",
  family="compliance", field="nursery", why="ratio requirement at risk",
  register="realisation")

# ---- translation and freelance -------------------------------------
U("The invoice to the Berlin client is ninety days out now.",
  "act", goal="chase the ninety day overdue Berlin client invoice",
  family="finance_admin", field="translation", why="his money, badly overdue",
  register="complaint")

# ---- music and performing ------------------------------------------
U("The PRS return has not been done for the last two quarters.",
  "act", goal="complete the outstanding PRS returns",
  family="compliance", field="music", why="his royalties, unclaimed",
  register="realisation")

# ---- cleaning ------------------------------------------------------
U("The COSHH sheets for the new degreaser never arrived.",
  "act", goal="obtain COSHH data sheets for the new degreaser",
  family="compliance", field="cleaning", why="safety documents missing",
  register="complaint")

# ---- photography ---------------------------------------------------
U("The wedding gallery was promised in six weeks and it has been nine.",
  "act", goal="deliver the overdue wedding gallery to the clients",
  family="work_deliverable", field="photography", why="his promise, badly late",
  register="worry")

# ---- recruitment ---------------------------------------------------
U("The candidate's right to work documents expire before the start date.",
  "act", goal="resolve the candidate's expiring right to work documents",
  family="compliance", field="recruitment", why="placement blocked",
  register="realisation")

# ---- marketing -----------------------------------------------------
U("The campaign microsite domain renews next week and it is on my personal card.",
  "act", goal="move the campaign domain renewal off the personal card",
  family="admin", field="marketing", why="dated renewal, wrong payment method",
  register="aside")

# ---- hotel management ----------------------------------------------
U("The fire alarm certificate is out of date and the inspection is annual.",
  "act", goal="book the annual fire alarm inspection",
  family="compliance", field="hotel_management", why="expired safety certificate",
  register="worry")


# =====================================================================
# 3. IGNORE — the 45%. A real day is mostly this. Every one of these
#    turning into a ping is a reason to take the pendant off.
# =====================================================================

# ---- small talk ----------------------------------------------------
for _t in [
    "Morning, you alright?",
    "Not too bad thanks, you?",
    "It has gone cold again, has it not.",
    "Did you see the traffic on the bridge earlier?",
    "I could murder a coffee.",
    "Long week already and it is only Tuesday.",
    "How was the weekend, did you get away at all?",
    "Nice one, see you later.",
    "That is a good shout, actually.",
    "Right, I am going to make a brew.",
    "Oh brilliant, that is one less thing.",
    "You would not believe the queue in there.",
]:
    U(_t, "ignore", whose="nobody", why="small talk", register="aside")

# ---- jokes ---------------------------------------------------------
for _t in [
    "If I get one more calendar invite I am moving to a forest.",
    "My back has filed a formal complaint.",
    "The printer has personally chosen violence today.",
    "I am not saying I am old, but I groaned getting out of the car.",
    "At this rate the dog is running the household.",
    "Statistically one of these meetings has to be useful.",
]:
    U(_t, "ignore", whose="nobody", why="joke, no obligation", register="aside")

# ---- venting with no commitment ------------------------------------
for _t in [
    "Everything takes three emails now, everything.",
    "I am so tired of chasing people for things they already agreed to.",
    "Honestly I do not know why I bother some days.",
    "They changed the system again without telling anyone.",
    "It is the same every single year and nothing changes.",
    "I have had about four hours sleep.",
    "Whoever designed this parking system needs a word with themselves.",
    "The phone has not stopped since half seven.",
    "I hate this time of year.",
    "Everyone wants everything yesterday.",
]:
    U(_t, "ignore", why="venting, no obligation created", register="complaint")

# ---- thinking aloud, no commitment ---------------------------------
for _t in [
    "I wonder how much those things even cost these days.",
    "Maybe one day I will learn to sail.",
    "I sometimes think about packing it all in and doing something with my hands.",
    "It would be nice to have a proper garden.",
    "I do not know, I might, I might not.",
    "There is probably a better way to do all this.",
    "Part of me wants to just start again from scratch.",
    "I keep seeing those adverts and wondering if they are any good.",
    "Something to think about, anyway.",
    "We will see how it goes I suppose.",
]:
    U(_t, "ignore", whose="nobody", why="musing, no commitment",
      register="thinking_aloud")

# ---- reading aloud and voice typing --------------------------------
for _t in [
    "Dear Mr Ellis, further to our conversation of the fourth, please find attached.",
    "New paragraph. The following items require sign off before Friday.",
    "Invoice number four four seven two, amount one thousand two hundred and forty.",
    "Send, reply all, include the attachment, remove item four nine one.",
    "Postcode is C V three, seven, R B.",
    "Bullet point, review the schedule. Bullet point, confirm the site access.",
    "Terms and conditions apply, see website for details.",
    "Section four subsection two, the contractor shall maintain adequate insurance.",
]:
    U(_t, "ignore", whose="machine", why="dictation to a machine", register="direct")

# ---- background television, radio and podcasts ---------------------
for _t, _w in [
    ("And that is why we always tell people to fix the rate before the renewal window closes.",
     "podcast presenter, not the owner"),
    ("Tonight on the programme, the chancellor faces questions over the autumn statement.",
     "television news, not the owner"),
    ("Buy one get one free this weekend only at your local store.",
     "advertisement audio"),
    ("Join us after the break for the weather.",
     "television continuity"),
    ("So my next guest has been doing this for over thirty years.",
     "podcast host, not the owner"),
    ("Book now and save twenty percent on your first order.",
     "advertisement audio"),
    ("It is two nil with about ten minutes left.",
     "match commentary"),
    ("Coming up, we will be taking your calls on the housing crisis.",
     "radio continuity"),
]:
    U(_t, "ignore", whose="nobody", why=_w, register="direct",
      hard=True, hard_kind="media")

# ---- someone else in the room, someone else's obligation -----------
for _t in [
    "Do not worry about the shopping, I will pick it up on the way home.",
    "I will photocopy the worksheets for you before first period.",
    "Leave the bins with me, I am up early anyway.",
    "I have already spoken to them, I will chase it tomorrow.",
    "I am booking the restaurant for Saturday, so do not double up.",
    "Give me the reference and I will call them myself.",
    "I will drop the forms in when I go past the surgery.",
    "Honestly it is fine, I will sort the tickets out tonight.",
    "My brother is picking Dad up from the hospital.",
    "Sam said he would chase the missing receipts from the Manchester office.",
]:
    U(_t, "ignore", whose="other", why="someone else's obligation",
      register="direct", hard=True, hard_kind="other_commitment")

# ---- hypotheticals -------------------------------------------------
for _t in [
    "If we ever go to Lisbon I would want to do it properly, a week at least.",
    "If I ever win anything decent I am buying a boat, that is the plan.",
    "Suppose we did move the whole thing to Friday, would that even help?",
    "In an ideal world we would have replaced that van two years ago.",
    "If money were no object I would have the loft done.",
    "Say we did go for the bigger unit, we would need the three phase supply.",
]:
    U(_t, "ignore", whose="nobody", why="hypothetical, nothing decided",
      register="thinking_aloud", hard=True, hard_kind="hypothetical")

# ---- already done, past tense --------------------------------------
for _t in [
    "Sorted the MOT this morning, all done.",
    "I raised the purchase order for the couplings last week.",
    "That is paid, it went out Friday.",
    "We got the tickets in the end, front section.",
    "I sent it over first thing so that one is off my list.",
    "The inspection passed, no actions.",
    "Renewed it online while I was waiting, took two minutes.",
]:
    U(_t, "ignore", why="already handled, past tense", register="aside",
      hard=True, hard_kind="past_done")

# ---- bare acknowledgements -----------------------------------------
for _t in [
    "Yeah ok sure.",
    "Mm hm.",
    "Right, yeah.",
    "Okay cool.",
    "Fine by me.",
    "Yep, that works.",
]:
    U(_t, "ignore", whose="nobody", why="bare acknowledgement, names nothing",
      register="fragment", hard=True, hard_kind="ack")

# ---- questions aimed at a person, not the assistant ----------------
for _t in [
    "Rachel, did you sign off the discharge summary or is that still with me?",
    "Did you move the car or is it still on the drive?",
    "Do you know if the bins went out last night?",
    "Have you seen my glasses anywhere?",
    "What time did they say they were coming?",
    "Are you eating with us or are you out?",
    "Dave, is the scaffold going up Monday or Tuesday?",
    "Did anyone actually reply to that thread?",
]:
    U(_t, "ignore", whose="other", why="question to a person in the room",
      register="direct", hard=True, hard_kind="question_to_person")

# ---- transcription mush --------------------------------------------
for _t in [
    "the the sorry no I mean the other one the",
    "and then we uh sorry go on",
    "yeah no yeah no yeah",
    "hang on there is something wrong with the",
    "cannot hear you at all now you are breaking",
    "okay so um right so basically the thing is",
]:
    U(_t, "ignore", whose="nobody", why="too garbled to act on",
      register="fragment", hard=True, hard_kind="asr_mush")

# ---- retractions inside one breath ---------------------------------
for _t in [
    "I need to book the car in for a service, oh no hang on, I did that last week.",
    "We should get flowers sent, actually no, she said not to.",
    "I will need a hire car for that trip, although it is cancelled now anyway.",
    "Order more of the blue ones, no wait, we found a box in the back.",
]:
    U(_t, "ignore", why="retracted in the same breath", register="thinking_aloud",
      hard=True, hard_kind="retraction")

# ---- plans that are already handled --------------------------------
for _t in [
    "The hotel is booked, the trains are booked, we are actually organised for once.",
    "It is all in the shared calendar already.",
    "The invoice went out with the others on the batch run.",
    "That is on next week's agenda so it will get picked up.",
]:
    U(_t, "ignore", why="plan already handled", register="aside")

# =====================================================================
# 4. CONVERSATIONS. The intent exists ACROSS lines, not in any one of
#    them. This is where a line-at-a-time triage is supposed to break.
# =====================================================================

# c01 — the split thought. Neither half is an errand; together they are.
U("I should call the clinic.", "ignore", convo="c01", turn=1,
  field="none", why="fragment, no subject yet", register="fragment")
U("About the results, I mean, they said a week and it has been three.", "act",
  convo="c01", turn=2, goal="contact the clinic about overdue test results",
  family="health_admin", field="none", why="completes the intent from turn one",
  register="worry")

# c02 — the referent arrives late.
U("There is that thing on Saturday.", "ignore", convo="c02", turn=1,
  whose="nobody", why="fragment, nothing named", register="fragment")
U("The christening, right.", "ignore", convo="c02", turn=2,
  whose="nobody", why="naming it is not an errand", register="fragment")
U("And we have not got them anything at all.", "act", convo="c02", turn=3,
  goal="buy a christening gift before Saturday",
  family="gifts", field="parent", why="need lands on the third line",
  register="realisation")

# c03 — a place remembered, then a want.
U("What was the name of that place.", "ignore", convo="c03", turn=1,
  whose="nobody", why="fragment, trying to recall", register="fragment")
U("The one with the courtyard, off the high street.", "ignore", convo="c03", turn=2,
  whose="nobody", why="still just recalling a place", register="fragment")
U("We should get a table there before it gets busy again.", "act", convo="c03", turn=3,
  goal="book a table at the courtyard restaurant off the high street",
  family="food", field="none", why="want plus urgency, his plan",
  register="thinking_aloud")

# c04 — the vehicle, assembled over three lines.
U("The van.", "ignore", convo="c04", turn=1, whose="nobody",
  why="single noun, no intent", register="fragment")
U("It is due its service, it has been flashing at me for a fortnight.", "act",
  convo="c04", turn=2, goal="book the van in for its service",
  family="vehicle", field="plumbing", why="overdue service, his van",
  register="complaint")
U("And the front tyres are borderline as well.", "act", convo="c04", turn=3,
  goal="have the front tyres checked and replaced with the van service",
  family="vehicle", field="plumbing", why="extends the same errand",
  register="aside")

# c05 — repeat mention of something already in flight.
U("I need to get the boiler serviced before it gets properly cold.", "act",
  convo="c05", turn=1, goal="arrange a boiler service",
  family="home_maintenance", field="none", why="his home, seasonal deadline",
  register="worry")
U("The radiators upstairs were never right last winter either.", "ignore",
  convo="c05", turn=2, why="context, no new errand", register="aside")
U("Still need to sort that boiler.", "ignore", convo="c05", turn=3,
  why="repeat of work already in flight", register="thinking_aloud",
  hard=True, hard_kind="in_flight")

# c06 — a plan retracted two lines later.
U("We should do dinner out Friday, somewhere decent for once.", "act",
  convo="c06", turn=1, goal="book dinner out for Friday",
  family="food", field="none", why="his plan, dated", register="thinking_aloud")
U("Oh, hang on, Priya is in Leeds Friday.", "ignore", convo="c06", turn=2,
  why="new fact undermines the plan", register="realisation")
U("Forget Friday then, we will do it another time.", "ignore", convo="c06", turn=3,
  why="explicit retraction of turn one", register="direct",
  hard=True, hard_kind="retraction")

# c07 — the errand is claimed by the other person in the room.
U("The car's MOT runs out next week.", "ignore", convo="c07", turn=1,
  why="statement of fact, nobody committed yet", register="aside")
U("Do not worry about it, I will book it in on my way home.", "ignore",
  convo="c07", turn=2, whose="other", why="the other person took it on",
  register="direct", hard=True, hard_kind="other_commitment")

# c08 — a question to a person, split over two lines.
U("Did you ever hear back.", "ignore", convo="c08", turn=1, whose="other",
  why="question to a person, incomplete", register="fragment",
  hard=True, hard_kind="question_to_person")
U("From the school, about the trip.", "ignore", convo="c08", turn=2, whose="other",
  why="completes a question to a person", register="fragment",
  hard=True, hard_kind="question_to_person")

# c09 — a hypothetical assembled over two lines.
U("If we ever go to Lisbon.", "ignore", convo="c09", turn=1, whose="nobody",
  why="hypothetical opener", register="fragment",
  hard=True, hard_kind="hypothetical")
U("We would want to do the tram thing, the yellow one.", "ignore",
  convo="c09", turn=2, whose="nobody", why="still hypothetical, nothing decided",
  register="thinking_aloud", hard=True, hard_kind="hypothetical")

# c10 — a worry that becomes a real health errand.
U("That mole on my back.", "ignore", convo="c10", turn=1, whose="nobody",
  why="fragment, no intent yet", register="fragment")
U("It has changed shape I think, it is darker than it was.", "ignore",
  convo="c10", turn=2, why="observation, no request yet", register="worry")
U("I ought to get somebody to look at it.", "act", convo="c10", turn=3,
  goal="book a GP appointment about a changing mole",
  family="health_admin", field="none", why="intent lands on the third line",
  register="realisation")

# c11 — the required past-tense done thing, in dialogue.
U("Did we ever sort the hotel for the wedding?", "ignore", convo="c11", turn=1,
  whose="other", why="question to a person", register="direct",
  hard=True, hard_kind="question_to_person")
U("I already booked it.", "ignore", convo="c11", turn=2,
  why="already done, nothing to do", register="direct",
  hard=True, hard_kind="past_done")

# c12 — the television, then a remark about the television.
U("And after the break, we will have the latest from the coast.", "ignore",
  convo="c12", turn=1, whose="nobody", why="television audio", register="direct",
  hard=True, hard_kind="media")
U("God, turn that down a bit.", "ignore", convo="c12", turn=2, whose="other",
  why="instruction to a person about the TV", register="direct")

# c13 — a work errand that only exists across two lines.
U("Marcus asked about the survey figures again.", "ignore", convo="c13", turn=1,
  field="civil_engineering", why="report of a request, not yet accepted",
  register="aside")
U("I will have to get those over to him before the site meeting.", "act",
  convo="c13", turn=2, goal="send Marcus the survey figures before the site meeting",
  family="communication", field="civil_engineering",
  why="he accepts the obligation here", register="thinking_aloud")

# c14 — a shopping need assembled from two complaints.
U("We are out of the good coffee again.", "ignore", convo="c14", turn=1,
  why="observation, may be routine", register="complaint")
U("And the dishwasher tablets, that is the last box.", "ignore",
  convo="c14", turn=2, why="second observation, still no intent", register="aside")
U("I am not doing another shop this week, can something just turn up.", "act",
  convo="c14", turn=3,
  goal="arrange a grocery delivery of coffee and dishwasher tablets",
  family="shopping", field="none", why="explicit want, concrete list above",
  register="complaint")

# c15 — a false start that never becomes anything.
U("I was going to ring them about the.", "ignore", convo="c15", turn=1,
  whose="nobody", why="abandoned sentence", register="fragment",
  hard=True, hard_kind="asr_mush")
U("No, it does not matter, it will keep.", "ignore", convo="c15", turn=2,
  why="explicitly dropped", register="direct",
  hard=True, hard_kind="retraction")

# =====================================================================
# 5. COMPOSITION GUARDS
# =====================================================================

REQUIRED_HARD_KINDS = {
    "other_commitment", "hypothetical", "past_done", "retraction", "ack",
    "in_flight", "question_to_person", "media",
}
AMBIENT_REGISTERS = ("realisation", "worry", "complaint", "aside",
                     "thinking_aloud")


def main() -> int:
    for i, r in enumerate(ROWS, 1):
        r["id"] = f"amb-{i:04d}"
    order = ["id", "text", "gold", "gold_lane", "goal", "family", "field",
             "whose", "why", "register", "hard", "hard_kind", "convo", "turn",
             "source"]
    rows = [{k: r[k] for k in order} for r in ROWS]

    n = len(rows)
    by_gold = Counter(r["gold"] for r in rows)
    ignore_share = by_gold["ignore"] / n
    act_ask = [r for r in rows if r["gold"] != "ignore"]
    fields = {r["field"] for r in act_ask if r["field"] != "none"}
    kinds = {r["hard_kind"] for r in rows if r["hard"]}
    convos = Counter(r["convo"] for r in rows if r["convo"])
    ambient = [r for r in act_ask if r["register"] in AMBIENT_REGISTERS]

    problems = []
    if n < 220:
        problems.append(f"only {n} utterances, need 220")
    if not 0.40 <= ignore_share <= 0.50:
        problems.append(f"ignore share {ignore_share:.1%} outside 40-50%")
    if len(fields) < 18:
        problems.append(f"only {len(fields)} walks of life in act/ask, need 18")
    missing = REQUIRED_HARD_KINDS - kinds
    if missing:
        problems.append(f"hard kinds missing: {sorted(missing)}")
    if len(ambient) < 16:
        problems.append(f"only {len(ambient)} ambient-register act/ask, need 16")
    if len(convos) < 8:
        problems.append(f"only {len(convos)} conversations, need 8")
    for cid, count in convos.items():
        turns = sorted(r["turn"] for r in rows if r["convo"] == cid)
        if turns != list(range(1, count + 1)):
            problems.append(f"conversation {cid} turns are {turns}")
    seen = set()
    for r in rows:
        if r["text"] in seen:
            problems.append(f"duplicate text: {r['text'][:50]}")
        seen.add(r["text"])
    anchor = "Oh my goodness, I forgot to cook for my kids this afternoon."
    if not any(r["text"] == anchor and r["gold"] == "act" for r in rows):
        problems.append("the owner's own example is missing or mislabelled")

    if problems:
        for p in problems:
            print("COMPOSITION FAILURE:", p)
        return 1

    out = os.path.join(HERE, "corpus.json")
    with open(out, "w") as fh:
        json.dump(rows, fh, indent=1)
        fh.write("\n")
    print(f"{n} utterances -> {out}")
    print(f"  ignore {by_gold['ignore']} ({ignore_share:.0%})  "
          f"act {by_gold['act']}  ask {by_gold['ask']}")
    print(f"  {len(fields)} walks of life, {len(convos)} conversations, "
          f"{sum(1 for r in rows if r['hard'])} hard cases")
    print(f"  ambient-register act/ask: {len(ambient)}")
    print(f"  hard kinds: {', '.join(sorted(kinds))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
