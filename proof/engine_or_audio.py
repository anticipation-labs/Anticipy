#!/usr/bin/env python3
"""Is it the engine, or is it the audio path? Scored, against a known script.

research/2026-08-24-engine-options.md concluded the engine is probably not the
fault. That conclusion rests on inference: 42 words per minute captured against
130-160 natural, 49% of phone lines four words or fewer, and 72% of THOSE
sitting in 2.6s of silence on both sides — isolated utterances, not cut
sentences. Words are being missed, not sentences cut. The prime suspect is
`PhoneListener.swift:311`, which runs the session in `mode: .measurement` — a
mode whose documented purpose is to MINIMISE automatic gain control. It has
been that way since build 6 and has never once been compared against the
alternative.

This file turns that inference into a measurement. It scores transcripts made
through the app's own audio path against the script that was read aloud, and
applies a decision rule that was written down before any recording existed.

    python3 proof/engine_or_audio.py --run proof/runs/<id>
    python3 proof/engine_or_audio.py --explain      # print the rule, run nothing

WHAT IT DOES NOT DO, STATED PLAINLY (LAW 3). It proves nothing today. Every
number below is arithmetic over text files, and no recording exists yet. Until
somebody reads proof/RECORDING-PROTOCOL.md into a phone and drops the
transcripts in a run directory, this is a scoring stick with nothing on it. A
green test suite here is evidence that the stick is straight — not that
anything has been measured.

WHY THERE ARE TWO WORD NUMBERS AND NOT ONE. Word error rate is the number the
literature quotes; it charges a decoder for words it invented as well as words
it lost. Capture rate is the number this product is capped by: of the words
that were actually spoken, what fraction survived to the brain. They are
different, they can move in opposite directions, and the §11 rule is written in
terms of capture. Both are printed, always, along with the insertion rate —
because capture rate alone would score a decoder that stutters every word as
perfect, and that is precisely the kind of flattery this repo keeps shipping.

WHY IT REFUSES. proof/capture_day.py's docstring says it about itself: the
recurring failure here is an instrument that quietly reports a nice number
instead of failing. A transcript that cannot be shown to be a recording of this
script gets no rate at all — not a low one, because a low one reads exactly
like the headline finding this experiment is hunting for.

Pattern matching in this file is tokenisation and arithmetic over a known
script. It decides no meaning and drives no behavior — HARNESS-LAWS LAW 1's
third carve-out, "gates and evals", is the whole of what this is.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter

# ---------------------------------------------------------------------------
# THE DECISION RULE, PRE-REGISTERED
#
# Copied from research/2026-08-24-engine-options.md §11, which took it from the
# voice-capture spec's §12.4: "Deciding the bar after seeing the result is how a
# bake-off gets talked into the wrong conclusion." These numbers exist before
# the first recording does. tests/test_engine_or_audio.py pins every one of
# them, so moving one is an edit to a test with a name that asks why — not a
# quiet slide toward the answer somebody already wanted.
# ---------------------------------------------------------------------------

#: R1. A strong reference decoder at or below this on the app's own audio means
#: the signal is starved: no decoder on the shortlist rescues it, and the
#: engine is exonerated.
STARVED_AUDIO_CEILING = 0.45

#: R2. A strong reference decoder at or above this means the audio was fine all
#: along and something downstream of the microphone lost the words.
ENGINE_FAULT_REFERENCE_FLOOR = 0.75

#: R2, second clause. The app's recognizer must trail the reference by at least
#: this much. Without it, a run where both decoders score 0.80 would "convict"
#: an engine that is keeping up perfectly well.
ENGINE_FAULT_MIN_GAP = 0.30

#: R3. Voice processing beating `.measurement` by this many points, on the same
#: decoder and the same script, makes the audio session line the bug. One line,
#: every iOS version, no migration.
AGC_WIN_MARGIN = 0.15

#: R4. Product-name hit rate with and without `contextualStrings` closer than
#: this means the vocabulary API is doing nothing under
#: `requiresOnDeviceRecognition` — which no primary source settles either way,
#: and which tejas_gate leg 7 currently reports green by grepping for a string.
CONTEXTUAL_STRINGS_INERT_BAND = 0.10

#: R4 needs enough mentions to express a ten-point difference at all. Three
#: mentions cannot; calling the vocabulary inert off three would be a coin flip
#: wearing a verdict's clothes.
MIN_NAME_MENTIONS = 8

#: THE VALIDITY GATE. Reading a low reference score as "the audio is starved"
#: is only available if the reference decoder is known to do well on audio that
#: is NOT starved. The control arm — the same script, close mic, clean — is how
#: the decoder proves it. Below this it has not, and R1/R2 are unavailable no
#: matter how the other cells came out. This is the difference between an
#: experiment and a number.
CONTROL_CREDIBILITY_FLOOR = 0.85

#: Below this many reference words a capture rate is noise with a decimal point.
MIN_REFERENCE_WORDS = 20

#: THE REFUSAL. Not "how much of the script survived" — that is the measurement
#: itself and it is allowed to be terrible. This is the other direction: of the
#: words in this TRANSCRIPT, what fraction are script words, in order?
#:
#: A starved microphone produces less text, but what it produces is script text.
#: A wrong file produces a full transcript that is mostly not script text at
#: all. Those separate cleanly where "capture is low" does not separate at all,
#: because a wrong file and a starved microphone both score low on capture —
#: which is exactly the confusion that would let a filing mistake be published
#: as this experiment's headline finding.
#:
#: An earlier draft gated on run structure instead: no four consecutive script
#: words means the wrong file. Its own test suite killed it. Production loses
#: words in BURSTS — "All of these", "Help me understand" — so a real 30%
#: capture can be a hundred three-word fragments that never once reach four in
#: a row, and the harness refused to score the exact case it exists to score.
MIN_SCRIPT_SHARE = 0.50

#: ...except when nearly everything survived. A decoder that stutters every word
#: matches all of the script and still fills half its transcript with repeats.
#: A high capture rate is its own evidence that this is the right pair of files.
ANCHOR_EXEMPT_CAPTURE = 0.60

#: The other end of the same problem. A transcript more than twice as long as
#: the script is not a decoder being verbose: it is free conversation recorded
#: into the scripted file, or a decoder looping on silence. Capture rate stays
#: honest in both cases and word error rate goes to nonsense, so the cell reads
#: as a fine result with an alarming number nobody looks at. Refuse instead.
MAX_INSERTION_RATE = 1.00

#: The alignment is O(len(ref) x len(hyp)). Ten minutes of speech is ~1400
#: words a side, which is instant; a mis-supplied book would swap the machine.
MAX_ALIGNMENT_CELLS = 25_000_000

ARMS = {
    "A": "today's config — .record, mode: .measurement",
    "B": "identical, plus inputNode.setVoiceProcessingEnabled(true)",
    "C": "control — same script, close mic, clean. Calibrates the reference decoder.",
}

DECODERS = {
    "sf_ctx": "SFSpeechRecognizer, on-device, WITH contextualStrings (today's baseline)",
    "sf_noctx": "SFSpeechRecognizer, on-device, WITHOUT contextualStrings",
    "reference": "a strong reference decoder run offline over the same WAV",
    "speech_transcriber": "SpeechTranscriber (iOS 26), if a device is to hand",
}

# ---------------------------------------------------------------------------
# Tokenisation
# ---------------------------------------------------------------------------

# Characters that end a word wherever they appear. Hyphens are here because
# decoders disagree about "far-field" versus "far field" with no acoustic
# difference behind the disagreement, and scoring that as a lost word would be
# measuring the typist.
_BREAKERS = str.maketrans({c: " " for c in "-–—/\\\n\t\r"})

# Stripped from the ends of a word only. The colon stays INSIDE a word on
# purpose: "5:15" is a token this product has been burned by, and folding it
# into "five fifteen" would erase exactly the failure the eval hunts.
_EDGE = ".,!?;:()[]{}<>\"`*_…“” "

_QUOTES = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"'})


def tokens(text: str) -> list[str]:
    """Words, lowercased, punctuation off the ends.

    Case is folded because the failure this measures is "anticipate" for
    "Anticipy" — a different word, not a different capital. A decoder that
    lowercases its output has not lost anything.
    """
    out: list[str] = []
    for raw in (text or "").translate(_QUOTES).translate(_BREAKERS).split():
        word = raw.strip(_EDGE).lower()
        if word:
            out.append(word)
    return out


# ---------------------------------------------------------------------------
# Alignment
# ---------------------------------------------------------------------------

def align(ref: list[str], hyp: list[str]) -> list[tuple]:
    """Levenshtein alignment, one operation per reference word plus insertions.

    Returns (kind, ref_index, hyp_index) in reference order, kind being
    "equal", "sub", "delete" or "insert". ref_index is None for an insertion;
    hyp_index is None for a deletion.

    IT MINIMISES TWO THINGS, IN ORDER: the edit distance first, and then — among
    every alignment that ties on edit distance — the number of words NOT counted
    as survivors. Both halves are load-bearing.

    Without the second half, capture rate depends on which equal-cost path the
    backtrace happened to walk. "a b" against "b a" costs two edits either as
    two substitutions, which finds nothing, or as delete-match-insert, which
    finds "b" — and capture rate is the number this whole experiment turns on.
    Mutation testing is what surfaced it: flipping the old tie-break broke no
    test, because nothing was pinning a choice that moved the headline number.

    Without the first half it would start buying matches with extra edits,
    preferring elaborate alignments that find a word here and there, and a bad
    transcript would score well.

    The two are packed into one integer rather than a tuple because at ten
    minutes a side this table is two million cells, and two million tuples is
    real memory for no gain.
    """
    n, m = len(ref), len(hyp)
    if n * m > MAX_ALIGNMENT_CELLS:
        raise ValueError(
            f"alignment of {n} reference words against {m} transcript words is "
            f"{n * m} cells, over the {MAX_ALIGNMENT_CELLS} ceiling — this is "
            "almost certainly the wrong pair of files")

    # value = cost * K + (K - 1 - equals). Ordering by this integer is exactly
    # ordering by (cost, -equals): the second term can never reach K, because
    # there cannot be more matches than there are words on the shorter side.
    K = min(n, m) + 1
    MISS = K - 1

    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        d[i][0] = i * K + MISS
    for j in range(1, m + 1):
        d[0][j] = j * K + MISS
    d[0][0] = MISS
    for i in range(1, n + 1):
        ri = ref[i - 1]
        di, dprev = d[i], d[i - 1]
        for j in range(1, m + 1):
            diag = dprev[j - 1] + (-1 if ri == hyp[j - 1] else K)
            di[j] = min(diag, dprev[j] + K, di[j - 1] + K)

    ops: list[tuple] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0:
            same = ref[i - 1] == hyp[j - 1]
            if d[i][j] == d[i - 1][j - 1] + (-1 if same else K):
                ops.append(("equal" if same else "sub", i - 1, j - 1))
                i, j = i - 1, j - 1
                continue
        if i > 0 and d[i][j] == d[i - 1][j] + K:
            ops.append(("delete", i - 1, None))
            i -= 1
            continue
        ops.append(("insert", None, j - 1))
        j -= 1
    ops.reverse()
    return ops


def _runs(ops: list[tuple]) -> tuple[int, float]:
    """Longest stretch of consecutive reference words that survived, and the
    share of survivors sitting in a stretch of two or more.

    DIAGNOSTIC ONLY — no rule reads either number. They are printed because
    "0.30 capture in three-word fragments" and "0.30 capture in two intact
    paragraphs and then nothing" are different bugs with the same rate, and the
    reader should not have to open the transcript to tell them apart.

    Insertions do not break a run: a decoder that hallucinated a word between
    two correct ones still heard the phrase.
    """
    longest = run = matched = in_runs = 0
    for kind, _, _ in ops:
        if kind == "insert":
            continue
        if kind == "equal":
            run += 1
            matched += 1
            longest = max(longest, run)
        else:
            if run >= 2:
                in_runs += run
            run = 0
    if run >= 2:
        in_runs += run
    return longest, (in_runs / matched if matched else 0.0)


# ---------------------------------------------------------------------------
# Product names
# ---------------------------------------------------------------------------

def _occurrences(ref: list[str], term_tokens: list[str]) -> list[tuple[int, int]]:
    """Every non-overlapping span of the reference that IS this term."""
    spans = []
    k = len(term_tokens)
    i = 0
    while i + k <= len(ref):
        if ref[i:i + k] == term_tokens:
            spans.append((i, i + k))
            i += k
        else:
            i += 1
    return spans


def _name_report(ref: list[str], hyp: list[str], ops: list[tuple],
                 vocabulary) -> dict:
    """Per-term mentions, hits, and — the part that earns its keep — what each
    miss turned into.

    Counting the miss is half the job. "Anticipy" heard as "anticipate" and
    "Anticipy" dropped entirely have different fixes: one is biasing, the other
    is capture. Folding them into a single miss count hides which one you have,
    and "heard as 'anticipate' x13" is the line that tells you which.
    """
    # Reference index -> (what happened to it, which hypothesis word it became),
    # and where in the operation stream that reference word sits.
    by_ref: dict[int, tuple] = {}
    op_at: dict[int, int] = {}
    for pos, (kind, ri, hi) in enumerate(ops):
        if ri is not None:
            by_ref[ri] = (kind, hi)
            op_at[ri] = pos

    report = {}
    for term in vocabulary:
        term_tokens = tokens(term)
        mentions = hits = dropped = 0
        heard_as: Counter = Counter()
        for start, end in _occurrences(ref, term_tokens) if term_tokens else []:
            mentions += 1
            outcomes = [by_ref.get(i, ("delete", None)) for i in range(start, end)]
            if all(kind == "equal" for kind, _ in outcomes):
                hits += 1
                continue
            # A two-word name half-heard is a miss, not half a hit: half a name
            # resolves in Contacts as confidently as a whole one, and to the
            # wrong human.
            became = _became(ops, op_at, hyp, start, end)
            if became:
                heard_as[" ".join(became)] += 1
            else:
                dropped += 1
        report[term] = {"mentions": mentions, "hits": hits, "dropped": dropped,
                        "heard_as": dict(heard_as)}
    return report


#: How far either side of a missed name to sweep up insertions. One word
#: becoming several is the headline failure — whisper writes "OpenTrade" as
#: "open trade" and "Anticipy" as "anti sippy" — and reporting only the single
#: word that happened to align sends the reader hunting the wrong bug. The cap
#: exists because the sweep is unbounded otherwise: a decoder looping on silence
#: beside a name would have its whole loop attributed to the name.
INSERTION_SWEEP = 2


def _became(ops, op_at, hyp, start, end) -> list[str]:
    """What a missed name span actually turned into, in transcript order."""
    positions = [op_at[i] for i in range(start, end) if i in op_at]
    if not positions:
        return []
    lo, hi_pos = min(positions), max(positions)
    swept = 0
    while lo > 0 and ops[lo - 1][0] == "insert" and swept < INSERTION_SWEEP:
        lo -= 1
        swept += 1
    swept = 0
    while hi_pos + 1 < len(ops) and ops[hi_pos + 1][0] == "insert" and swept < INSERTION_SWEEP:
        hi_pos += 1
        swept += 1
    return [hyp[h] for _, _, h in ops[lo:hi_pos + 1] if h is not None]


# ---------------------------------------------------------------------------
# Scoring one cell
# ---------------------------------------------------------------------------

def score(reference_text: str, transcript_text: str, vocabulary) -> dict:
    """One arm, one decoder, one script. Rates, or a refusal with a reason.

    On refusal every RATE is None rather than a number. That is deliberate and
    it is the whole point: a None propagates into a TypeError the next time
    somebody does arithmetic on it, where a 0.19 propagates into a slide.
    """
    ref = tokens(reference_text)
    hyp = tokens(transcript_text)

    out = {
        "ref_words": len(ref),
        "hyp_words": len(hyp),
        "matched": 0, "substituted": 0, "deleted": 0, "inserted": 0,
        "capture_rate": None, "wer": None, "insertion_rate": None,
        "longest_run": 0, "matched_in_runs": 0.0, "script_share": None,
        "names": {}, "name_mentions": 0, "name_hits": 0, "name_hit_rate": None,
        "unalignable": False, "unalignable_reason": "",
    }

    if len(ref) < MIN_REFERENCE_WORDS:
        out["unalignable"] = True
        out["unalignable_reason"] = (
            f"the reference is {len(ref)} words; a capture rate needs at least "
            f"{MIN_REFERENCE_WORDS} words behind it to mean anything")
        return out

    if not hyp:
        # A recognizer that went deaf and a wrong file supplied by a tired
        # human produce byte-identical evidence. The harness cannot tell them
        # apart, so it must not pick — least of all the one that reads as a
        # dramatic finding. If the recognizer genuinely produced nothing, that
        # is a capture rate of zero and a finding in its own right; record it
        # by hand, with the operator saying so.
        out["unalignable"] = True
        out["unalignable_reason"] = (
            "the transcript is empty — a dead recognizer and a wrong file look "
            "identical from here, and this harness will not pick one for you")
        return out

    ops = align(ref, hyp)
    counts = Counter(kind for kind, _, _ in ops)
    matched = counts["equal"]
    out["matched"] = matched
    out["substituted"] = counts["sub"]
    out["deleted"] = counts["delete"]
    out["inserted"] = counts["insert"]

    longest, in_runs = _runs(ops)
    out["longest_run"] = longest
    out["matched_in_runs"] = in_runs

    names = _name_report(ref, hyp, ops, vocabulary)
    out["names"] = names
    out["name_mentions"] = sum(n["mentions"] for n in names.values())
    out["name_hits"] = sum(n["hits"] for n in names.values())

    capture = matched / len(ref)
    share = matched / len(hyp)
    out["script_share"] = share

    if counts["insert"] / len(ref) > MAX_INSERTION_RATE:
        out["unalignable"] = True
        out["unalignable_reason"] = (
            f"this transcript is {len(hyp)} words against a {len(ref)}-word "
            "script. Either free conversation was recorded into the same file "
            "as the script, or the decoder looped. The capture rate would be "
            "right and the error rate meaningless, which is the worst of both")
        return out

    if share < MIN_SCRIPT_SHARE and capture < ANCHOR_EXEMPT_CAPTURE:
        out["unalignable"] = True
        out["unalignable_reason"] = (
            f"only {share:.0%} of this transcript is script material, under the "
            f"{MIN_SCRIPT_SHARE:.0%} floor. A starved microphone sends less "
            "text; it does not send text about something else. Check the file "
            "pairing — and check that free conversation was not recorded into "
            "the same file as the script — before reading a starved microphone "
            "into this")
        return out

    out["capture_rate"] = capture
    out["wer"] = (counts["sub"] + counts["delete"] + counts["insert"]) / len(ref)
    out["insertion_rate"] = counts["insert"] / len(ref)
    # Zero of zero is not a hundred percent. Printing one would advertise a
    # vocabulary that never got the chance to fail.
    out["name_hit_rate"] = (out["name_hits"] / out["name_mentions"]
                            if out["name_mentions"] else None)
    return out


# ---------------------------------------------------------------------------
# The verdict
# ---------------------------------------------------------------------------

def _usable(cells, key, blocked):
    cell = cells.get(key)
    if cell is None:
        blocked.append(f"{key} is missing from the run")
        return None
    if cell.get("unalignable"):
        blocked.append(f"{key} could not be aligned: {cell.get('unalignable_reason')}")
        return None
    return cell


def verdict(cells: dict) -> dict:
    """Apply the pre-registered rule to a scored run.

    Every rule reports fired True, fired False, or fired None — and None is a
    first-class answer meaning "this run cannot speak to that question".
    Collapsing None into False is how a missing measurement becomes a claim.
    """
    findings = []
    blocked: list[str] = []

    # --- the validity gate -------------------------------------------------
    control_blocked: list[str] = []
    control = _usable(cells, "C/reference", control_blocked)
    credible = control is not None and control["capture_rate"] >= CONTROL_CREDIBILITY_FLOOR
    if control is not None and not credible:
        control_blocked.append(
            f"the reference decoder scored {control['capture_rate']:.2f} on the "
            f"clean control, under the {CONTROL_CREDIBILITY_FLOOR} floor — it is "
            "not strong enough here for a low score on arm A to mean the audio "
            "was starved rather than the decoder was weak")
    if not credible:
        blocked.extend(control_blocked)

    # --- R1 / R2: engine or audio path ------------------------------------
    r1_blocked: list[str] = []
    a_ref = _usable(cells, "A/reference", r1_blocked) if credible else None
    blocked.extend(b for b in r1_blocked if b not in blocked)

    if not credible or a_ref is None:
        why = "; ".join(blocked) or "the reference decoder cell is unavailable"
        findings.append({"rule": "R1", "id": "AUDIO_PATH_AT_FAULT",
                         "fired": None, "because": why})
        findings.append({"rule": "R2", "id": "ENGINE_AT_FAULT",
                         "fired": None, "because": why})
    else:
        cap = a_ref["capture_rate"]
        r1 = cap <= STARVED_AUDIO_CEILING
        findings.append({
            "rule": "R1", "id": "AUDIO_PATH_AT_FAULT", "fired": r1,
            "because": (
                f"the reference decoder captured {cap:.2f} of the script off the "
                f"app's own audio, {'at or under' if r1 else 'above'} the "
                f"{STARVED_AUDIO_CEILING} ceiling")})

        app_blocked: list[str] = []
        a_app = _usable(cells, "A/sf_ctx", app_blocked)
        if a_app is None:
            blocked.extend(b for b in app_blocked if b not in blocked)
            findings.append({"rule": "R2", "id": "ENGINE_AT_FAULT", "fired": None,
                             "because": "; ".join(app_blocked)})
        else:
            gap = cap - a_app["capture_rate"]
            r2 = cap >= ENGINE_FAULT_REFERENCE_FLOOR and gap >= ENGINE_FAULT_MIN_GAP
            findings.append({
                "rule": "R2", "id": "ENGINE_AT_FAULT", "fired": r2,
                "because": (
                    f"reference {cap:.2f} against the app's {a_app['capture_rate']:.2f} "
                    f"— a gap of {gap:.2f} against a floor of "
                    f"{ENGINE_FAULT_REFERENCE_FLOOR} and a required gap of "
                    f"{ENGINE_FAULT_MIN_GAP}")})

    # --- R3: the audio session line ---------------------------------------
    # Deliberately independent of the reference decoder. Arm A against arm B on
    # the SAME decoder needs nothing calibrated, so an environment with no
    # reference decoder can still fly this arm — and it is the one with a
    # one-line fix behind it.
    agc_blocked: list[str] = []
    a_app = _usable(cells, "A/sf_ctx", agc_blocked)
    b_app = _usable(cells, "B/sf_ctx", agc_blocked)
    if a_app is None or b_app is None:
        blocked.extend(b for b in agc_blocked if b not in blocked)
        findings.append({"rule": "R3", "id": "MEASUREMENT_MODE_IS_THE_BUG",
                         "fired": None, "because": "; ".join(agc_blocked)})
    else:
        delta = b_app["capture_rate"] - a_app["capture_rate"]
        findings.append({
            "rule": "R3", "id": "MEASUREMENT_MODE_IS_THE_BUG",
            "fired": delta >= AGC_WIN_MARGIN,
            "because": (
                f"voice processing captured {b_app['capture_rate']:.2f} against "
                f"{a_app['capture_rate']:.2f} for .measurement — {delta:+.2f}, "
                f"against a required {AGC_WIN_MARGIN}")})

    # --- R4: is contextualStrings inert? ----------------------------------
    voc_blocked: list[str] = []
    with_ctx = _usable(cells, "A/sf_ctx", voc_blocked)
    without = _usable(cells, "A/sf_noctx", voc_blocked)
    if with_ctx is None or without is None:
        blocked.extend(b for b in voc_blocked if b not in blocked)
        findings.append({"rule": "R4", "id": "CONTEXTUAL_STRINGS_INERT",
                         "fired": None, "because": "; ".join(voc_blocked)})
    elif (with_ctx["name_mentions"] < MIN_NAME_MENTIONS
          or without["name_mentions"] < MIN_NAME_MENTIONS):
        findings.append({
            "rule": "R4", "id": "CONTEXTUAL_STRINGS_INERT", "fired": None,
            "because": (
                f"{with_ctx['name_mentions']} and {without['name_mentions']} "
                f"vocabulary mentions, under the {MIN_NAME_MENTIONS} needed to "
                f"express a {CONTEXTUAL_STRINGS_INERT_BAND} difference at all")})
    elif with_ctx["name_hit_rate"] is None or without["name_hit_rate"] is None:
        findings.append({"rule": "R4", "id": "CONTEXTUAL_STRINGS_INERT",
                         "fired": None,
                         "because": "no vocabulary term was spoken in this arm"})
    else:
        delta = with_ctx["name_hit_rate"] - without["name_hit_rate"]
        findings.append({
            "rule": "R4", "id": "CONTEXTUAL_STRINGS_INERT",
            "fired": abs(delta) < CONTEXTUAL_STRINGS_INERT_BAND,
            "because": (
                f"names came through {with_ctx['name_hit_rate']:.2f} with the "
                f"vocabulary and {without['name_hit_rate']:.2f} without "
                f"({delta:+.2f}, band {CONTEXTUAL_STRINGS_INERT_BAND})")})

    fired = {f["rule"]: f["fired"] for f in findings}
    if fired["R1"] is None and fired["R2"] is None:
        headline = "CANNOT DECIDE"
    elif fired["R1"]:
        headline = "AUDIO PATH AT FAULT"
    elif fired["R2"]:
        headline = "ENGINE AT FAULT"
    else:
        headline = "INDETERMINATE"

    return {
        "headline": headline,
        # INDETERMINATE is decidable: the run answered, and the answer was
        # "neither". Only CANNOT DECIDE means the run could not be read.
        "decidable": headline != "CANNOT DECIDE",
        "findings": findings,
        "blocked": blocked,
    }


HEADLINE_MEANING = {
    "AUDIO PATH AT FAULT": (
        "a strong decoder loses the same words off the same file. Fix the front "
        "end; do not migrate the engine."),
    "ENGINE AT FAULT": (
        "the audio was decodable and the app's recognizer did not decode it. "
        "The §8 migration is justified on evidence."),
    "INDETERMINATE": (
        "the reference decoder landed between the two pre-registered thresholds. "
        "Neither conclusion is available; this is the answer, not a rounding "
        "opportunity."),
    "CANNOT DECIDE": (
        "the run does not contain what the rule needs. See the blocked list."),
}


# ---------------------------------------------------------------------------
# Reading a run off disk
# ---------------------------------------------------------------------------

def load_run(run_dir: str) -> dict:
    """A run directory is a manifest plus the text files it names.

    manifest.json:
        {"run_id": "...", "recorded_at": "...",
         "reference_script": "script.txt",
         "vocabulary": ["Anticipy", "Tejas", ...],
         "cells": [{"arm": "A", "decoder": "sf_ctx",
                    "transcript": "arm_a/sf_ctx.txt"}, ...]}

    Paths are relative to the run directory. Everything is plain text: the
    scratch recorder writes a transcript per cell, and nothing here needs a
    parser that could disagree with the thing that wrote it.
    """
    manifest_path = os.path.join(run_dir, "manifest.json")
    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)

    def read(rel):
        with open(os.path.join(run_dir, rel), encoding="utf-8") as fh:
            return fh.read()

    reference = read(manifest["reference_script"])
    vocabulary = manifest.get("vocabulary") or []
    scored = {}
    for cell in manifest.get("cells", []):
        arm, decoder = cell["arm"], cell["decoder"]
        if arm not in ARMS:
            raise ValueError(f"unknown arm {arm!r}; known: {sorted(ARMS)}")
        if decoder not in DECODERS:
            raise ValueError(f"unknown decoder {decoder!r}; known: {sorted(DECODERS)}")
        # A cell may name its own script: if the control arm reads a shorter
        # passage, scoring it against the full script would report the unread
        # remainder as lost words.
        ref = read(cell["reference_script"]) if cell.get("reference_script") else reference
        key = f"{arm}/{decoder}"
        try:
            scored[key] = score(ref, read(cell["transcript"]), vocabulary)
        except FileNotFoundError:
            # A half-finished run is the normal case, not an error: arms A and B
            # can be flown on a phone alone, days before anybody gets a
            # reference decoder pointed at the WAVs. Crashing on the empty cell
            # would withhold R3 — the one rule with a one-line fix behind it.
            scored[key] = {
                "ref_words": 0, "hyp_words": 0,
                "matched": 0, "substituted": 0, "deleted": 0, "inserted": 0,
                "capture_rate": None, "wer": None, "insertion_rate": None,
                "longest_run": 0, "matched_in_runs": 0.0, "script_share": None,
                "names": {}, "name_mentions": 0, "name_hits": 0,
                "name_hit_rate": None, "unalignable": True,
                "unalignable_reason": f"no transcript at {cell['transcript']!r}",
            }
    return {"manifest": manifest, "cells": scored}


def scaffold(run_dir: str, script_path: str, vocabulary=None) -> str:
    """Lay out an empty run so nobody has to hand-write JSON while holding a
    phone. Every cell is listed; the ones nobody fills in come back REFUSED
    with the missing path named, which is the honest state of a partial run."""
    cells = [{"arm": arm, "decoder": dec,
              "transcript": f"arm_{arm.lower()}/{dec}.txt"}
             for arm in ("A", "B", "C") for dec in DECODERS
             # The control arm exists to calibrate the reference decoder. Asking
             # for the app's recognizer on it too would be three more recordings
             # for a question nothing asks.
             if not (arm == "C" and dec != "reference")]
    os.makedirs(run_dir, exist_ok=True)
    for arm in ("a", "b", "c"):
        os.makedirs(os.path.join(run_dir, f"arm_{arm}"), exist_ok=True)
    with open(script_path, encoding="utf-8") as fh:
        script = fh.read()
    with open(os.path.join(run_dir, "script.txt"), "w", encoding="utf-8") as fh:
        fh.write(script)
    manifest = {
        "run_id": os.path.basename(os.path.normpath(run_dir)),
        "recorded_at": "",
        "reference_script": "script.txt",
        "vocabulary": list(vocabulary or ["Anticipy", "Tejas", "OpenTrade", "pendant"]),
        "cells": cells,
    }
    path = os.path.join(run_dir, "manifest.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")
    return path


def render(run: dict) -> str:
    lines = []
    m = run["manifest"]
    lines.append(f"run {m.get('run_id', '?')}   recorded {m.get('recorded_at', '?')}")
    lines.append("")
    lines.append(f"{'cell':<26}{'capture':>9}{'WER':>7}{'ins':>7}"
                 f"{'script%':>9}{'names':>9}{'run':>6}")
    for key in sorted(run["cells"]):
        c = run["cells"][key]
        if c["unalignable"]:
            lines.append(f"{key:<26}{'REFUSED':>9}   {c['unalignable_reason']}")
            continue
        names = ("n/a" if c["name_hit_rate"] is None
                 else f"{c['name_hits']}/{c['name_mentions']}")
        lines.append(f"{key:<26}{c['capture_rate']:>9.2f}{c['wer']:>7.2f}"
                     f"{c['insertion_rate']:>7.2f}{c['script_share']:>9.2f}"
                     f"{names:>9}{c['longest_run']:>6}")
    # The reference decoder has no vocabulary biasing of any kind, so its names
    # column is not comparable with the app's and is not used by any rule. R4
    # compares the app against itself, with and without contextualStrings.
    lines.append("  (names on the reference row measure an unbiased decoder — "
                 "no rule reads them)")

    lines.append("")
    for key in sorted(run["cells"]):
        c = run["cells"][key]
        misses = {t: n for t, n in c["names"].items()
                  if n["mentions"] and n["hits"] < n["mentions"]}
        for term, n in misses.items():
            heard = ", ".join(f"{k!r} x{v}" for k, v in n["heard_as"].items())
            lines.append(f"  {key}  {term}: {n['hits']}/{n['mentions']} "
                         f"heard as {heard or '-'}, dropped {n['dropped']}")

    v = verdict(run["cells"])
    lines.append("")
    for f in v["findings"]:
        mark = {True: "FIRED ", False: "no    ", None: "??????"}[f["fired"]]
        lines.append(f"  {f['rule']} {mark} {f['id']}")
        lines.append(f"        {f['because']}")
    lines.append("")
    lines.append(f"VERDICT: {v['headline']} — {HEADLINE_MEANING[v['headline']]}")
    for b in v["blocked"]:
        lines.append(f"  blocked: {b}")
    lines.append("")
    lines.append("Law 3: this is a measurement of files, not of production. It "
                 "says nothing about the live system until a build carrying the "
                 "winning change is verified on the device.")
    return "\n".join(lines)


def explain() -> str:
    out = ["THE DECISION RULE, PRE-REGISTERED "
           "(research/2026-08-24-engine-options.md §11)", ""]
    out.append("Validity gate, before any verdict about the engine:")
    out.append(f"  the reference decoder must capture >= {CONTROL_CREDIBILITY_FLOOR} "
               "on arm C, the clean close-mic control.")
    out.append(f"  Below that it is a weak decoder, not a starved microphone, and "
               "R1 and R2 are unavailable.")
    out.append("")
    out.append(f"R1 AUDIO PATH AT FAULT   reference on arm A <= {STARVED_AUDIO_CEILING}")
    out.append(f"R2 ENGINE AT FAULT       reference on arm A >= {ENGINE_FAULT_REFERENCE_FLOOR}")
    out.append(f"                         AND ahead of the app by >= {ENGINE_FAULT_MIN_GAP}")
    out.append(f"   between {STARVED_AUDIO_CEILING} and {ENGINE_FAULT_REFERENCE_FLOOR}: "
               "INDETERMINATE, and that is the answer")
    out.append(f"R3 MEASUREMENT MODE      arm B beats arm A on sf_ctx by >= {AGC_WIN_MARGIN}")
    out.append(f"R4 VOCABULARY INERT      |sf_ctx - sf_noctx| name hit rate < "
               f"{CONTEXTUAL_STRINGS_INERT_BAND}")
    out.append(f"                         needs >= {MIN_NAME_MENTIONS} mentions a side")
    out.append("")
    out.append("Arms:")
    for k, v in ARMS.items():
        out.append(f"  {k}  {v}")
    out.append("Decoders:")
    for k, v in DECODERS.items():
        out.append(f"  {k:<20} {v}")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", help="a run directory holding manifest.json")
    ap.add_argument("--scaffold", metavar="DIR",
                    help="create an empty run directory ready for transcripts")
    ap.add_argument("--script", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "fixtures",
        "read_aloud_script.txt"))
    ap.add_argument("--explain", action="store_true",
                    help="print the pre-registered rule and exit")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    if args.scaffold:
        path = scaffold(args.scaffold, args.script)
        print(f"wrote {path}")
        print("drop one transcript per cell at the paths it names, then re-run "
              "with --run")
        return 0

    if args.explain or not args.run:
        print(explain())
        return 0

    run = load_run(args.run)
    v = verdict(run["cells"])
    if args.json:
        print(json.dumps({"cells": run["cells"], "verdict": v}, indent=2))
    else:
        print(render(run))

    # Exit 1 means the run could not be READ as a measurement — a refused cell,
    # a missing one, a reference decoder that failed its control. It does NOT
    # mean the answer was unwelcome: "ENGINE AT FAULT" exits 0, because a
    # measurement is not a gate and a harness that exits red on a finding
    # teaches people to stop running it.
    return 0 if v["decidable"] else 1


if __name__ == "__main__":
    sys.exit(main())
