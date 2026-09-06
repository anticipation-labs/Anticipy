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
import hashlib
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

#: R4'S POSITIVE CONTROL, and it had none. The "power floor" above counts
#: mentions in the REFERENCE, so both arms always have the same count — it
#: measures the script, not the data, and nothing anywhere required either
#: decoder to have heard a single name. A starved arm scoring 0/26 on BOTH
#: sides is a delta of exactly 0.00, which is the strongest possible "inert"
#: signal: the outcome the experiment expects mechanically manufactures the
#: vocabulary finding, firing R4 alongside R1. Zero against zero is not "the
#: biasing changed nothing", it is "nothing was heard for the biasing to
#: change".
MIN_NAME_HITS_EITHER_SIDE = 1

#: THE VALIDITY GATE. Reading a low reference score as "the audio is starved"
#: is only available if the reference decoder is known to do well on audio that
#: is NOT starved. The control arm — the same script, close mic, clean — is how
#: the decoder proves it. Below this it has not, and R1/R2 are unavailable no
#: matter how the other cells came out. This is the difference between an
#: experiment and a number.
CONTROL_CREDIBILITY_FLOOR = 0.85

#: THE VALIDITY GATE, SECOND CLAUSE. The control proves the reference decoder
#: can hear THIS script clean. A cell may name its own `reference_script`, and
#: nothing used to require the control's script to resemble the one arm A was
#: scored against: a twenty-word passage read perfectly cleared the 0.85 floor
#: and opened R1 and R2 for a 370-word arm A. "This decoder can transcribe one
#: sentence" is not the premise the inference needs.
MIN_CONTROL_SCRIPT_RATIO = 0.80

#: THE VALIDITY GATE, THIRD CLAUSE. RECORDING-PROTOCOL.md used to tell the
#: operator in writing to re-record the control until it cleared, and nothing
#: anywhere recorded how many attempts that took. A pass/fail on decoder
#: credibility that may be retried without limit or record is a MAXIMUM OVER
#: ATTEMPTS, not a measurement — and the same hazard runs the other way on arms
#: A and B, where re-recording until the numbers look like the expected finding
#: is the same act pointed at the conclusion. One recording, plus one honest
#: retake for a fumbled read. Above that the number was selected. The manifest
#: has to say; an unrecorded attempt count and a ninth attempt are the same
#: evidence from here.
MAX_RECORDING_ATTEMPTS = 2

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

# ---------------------------------------------------------------------------
# EXTENT. Every refusal above asks the same question — "is this transcript
# about the RIGHT script?" — and not one of them asks "is it about ALL of it?"
# That gap is one shape, not two bugs, and it is the shape that produced both
# of the wrong headlines below:
#
#   * a partial from SFSpeechURLRecognitionRequest, or a truncated write from
#     the scratch recorder, holding the script's first 92 of 370 words. 100%
#     script material, share 1.00, capture 0.25 — and against a reference at
#     0.82 the harness printed ENGINE AT FAULT and called the migration
#     justified. Nothing looked at WHERE in the reference the survivors fell.
#
#   * one word. `if not hyp:` refuses zero tokens and scores one; "you" and
#     "Thank you." are whisper's canonical output on silence or a failed
#     decode, and "you" alone scored capture 0.0027 with share 1.00 and fired
#     R1 off a dead file. The empty-transcript refusal's own rationale — a dead
#     recognizer and a wrong file look identical from here — is exactly as true
#     at one word as at zero. The line was drawn at the single point where the
#     confusion cannot occur rather than at the point where it stops.
#
# Both are the same failure: a proportion computed over a sample nobody sized,
# and a conclusion about a page drawn from a paragraph.
# ---------------------------------------------------------------------------

#: EXTENT, first half: how far across the reference the surviving words reach,
#: first survivor to last, as a fraction of the script.
#:
#: The operator read the WHOLE page — that is what the protocol asks for and
#: what makes the script a reference at all. So a transcript whose evidence
#: stops a quarter of the way in is not a measurement of a starved microphone;
#: it is a recording that stopped, a file that was truncated, a decoder that
#: returned a partial, or the wrong file. Those are four different bugs and
#: they are one shape from here, so the harness refuses and names them rather
#: than publishing a capture rate that reads as this experiment's headline.
#:
#: This is NOT the four-consecutive-words rule an earlier draft died on. That
#: one asked whether survivors clustered; this asks only whether they reach the
#: end. A hundred scattered three-word fragments — the shape production
#: actually shows — span the whole script and pass, which is why the 30%-in-
#: bursts case still scores.
MIN_REFERENCE_SPAN = 0.70

#: EXTENT, second half: how many words a transcript must contain before the
#: script-share refusal above means anything.
#:
#: `share` is a proportion estimated from a sample of size len(hyp), and at
#: len(hyp) = 1 it carries no information whatever: "you" is 100% script
#: material. MIN_REFERENCE_WORDS already says this about the other side of the
#: pair — "below this many reference words a capture rate is noise with a
#: decimal point" — and this is the same sentence about the transcript, at the
#: same number, for the same reason.
#:
#: What it costs: against the shipped 370-word script the harness can no longer
#: report a capture below about 0.054. Every threshold the decision rule reads
#: sits above 0.30, production's observed 42 wpm against 130-160 natural is
#: ~0.27, and R1's ceiling is 0.45 — so the instrument keeps its full
#: resolution across the entire decision-relevant range and gives up only the
#: region where it could not tell a starved microphone from a dead one.
MIN_TRANSCRIPT_WORDS = 20

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
# PROVENANCE. The second half of the same shape. Every rule in this file works
# by SUBTRACTING one cell from another — R2 reference minus app, R3 arm B minus
# arm A, R4 with-vocabulary minus without — and not one of them asked whether
# the two cells came from different recordings.
#
# The cost of not asking, twice over:
#
#   * the scratch recorder's `contextualStrings` toggle is never wired, so
#     arm_a/sf_ctx.txt and arm_a/sf_noctx.txt are the SAME BYTES. Delta exactly
#     +0.00, and R4 fires: "contextualStrings does nothing under
#     requiresOnDeviceRecognition." The strongest possible R4 signal is also
#     the signature of the harness never having run the experiment.
#
#   * arm A's transcript filed under arm B reverses R3, and the protocol's own
#     mitigation is a sentence asking the operator to be careful.
#
# The scratch recorder EXISTS as of 2026-09-06, iOS build 153
# (`app/ios/Anticipy/Audio/ScratchRecorder.swift`), and it writes this line.
# It was specified here first, while the file was still unwritten and its
# output contract was free to require anything — which is why the cheapest
# check in the repo is also the one the recorder was built around. First line
# of each transcript, stripped before scoring:
#
#   #anticipy: arm=A decoder=sf_ctx wav=arm_a.wav sha256=<64 hex of the WAV>
#
# From it three things become checkable that no arithmetic over the text ever
# could: the cell is filed under the arm it was recorded in; two cells from the
# same arm decoded the same WAV; and two cells from different arms did not.
PROVENANCE_PREFIX = "#anticipy:"

#: Which provenance keys are load-bearing. `wav` is carried for the operator to
#: read; `sha256` is what the checks compare, because a filename is exactly the
#: thing a tired human gets wrong.
PROVENANCE_KEYS = ("arm", "decoder", "wav", "sha256")


def parse_provenance(text: str) -> dict | None:
    """Read the provenance line off the front of a transcript, or None.

    Absent is legal — a run recorded before the recorder existed, or a
    reference decode produced by proof/reference_decode.py, has none. Absent is
    not the same as WRONG: a missing line leaves the distinctness checks with
    nothing to stand on, and they say so rather than assuming the good case.
    """
    first = (text or "").lstrip().split("\n", 1)[0].strip()
    if not first.startswith(PROVENANCE_PREFIX):
        return None
    out: dict = {}
    for field in first[len(PROVENANCE_PREFIX):].split():
        key, sep, value = field.partition("=")
        if sep and key in PROVENANCE_KEYS:
            out[key] = value
    return out or None


def strip_provenance(text: str) -> str:
    """The transcript without its provenance line.

    Load-bearing: `sha256=<64 hex>` tokenises into a word, and a header left in
    the text would be scored as a hallucinated word the decoder never said —
    the harness charging the recorder for its own bookkeeping.
    """
    if parse_provenance(text) is None:
        return text
    stripped = (text or "").lstrip()
    _, _, rest = stripped.partition("\n")
    return rest

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


#: How much of each end of the surviving-word positions `_span` ignores.
#:
#: NOT a fudge factor — it is the price of the alignment's tie-break. When the
#: transcript is much shorter than the script, whole families of alignments tie
#: on BOTH objectives: matching 92 words at reference positions 0-91 and
#: matching 91 of them there plus one against a common word at position 300
#: cost the same 278 deletions and find the same 92 survivors. The backtrace is
#: free to pick either, so raw first-and-last positions are decided by a
#: tie-break rather than by the audio — the exact disease the align() docstring
#: records having been caught by mutation testing. Measured on the real
#: 370-word script against its own first 92 words, the scatter is a couple of
#: words; a tenth of the survivors at each end absorbs it with room to spare.
SPAN_TRIM = 0.10


def _span(ops: list[tuple], ref_len: int) -> float:
    """How far across the reference the surviving words reach, ignoring the
    outermost SPAN_TRIM of them at each end, scaled so that survivors spread
    evenly down the page read 1.00.

    NOT a diagnostic — MIN_REFERENCE_SPAN reads this, and it is the number that
    separates "the microphone lost words all the way down the page" from "this
    file only ever contained the top of the page". `_runs` above computes the
    same family of evidence and is marked DIAGNOSTIC ONLY, no rule reads either
    number; that was true, and a truncated transcript with longest_run 90 and
    matched_in_runs 1.00 walked past every refusal into an ENGINE AT FAULT
    headline while both numbers sat in the report saying so.

    Reach rather than density, on purpose. Density is the four-consecutive-
    words rule an earlier draft died on: production loses words in bursts, so a
    real 30% capture is a hundred scattered fragments that never reach four in
    a row. Those fragments still start near the first word of the page and end
    near the last, because the reader read the whole page — which is what makes
    reach the one thing a truncation cannot fake.
    """
    matched = sorted(ri for kind, ri, _ in ops if kind == "equal")
    n = len(matched)
    if n < 2 or ref_len <= 0:
        return 0.0
    lo = int(SPAN_TRIM * (n - 1))
    hi = n - 1 - lo
    reach = matched[hi] - matched[lo]
    return min(1.0, reach / ((1 - 2 * SPAN_TRIM) * ref_len))


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
        "covered_span": 0.0,
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

    if len(hyp) < MIN_TRANSCRIPT_WORDS:
        # The sentence above is exactly as true at one word as at zero, and the
        # line used to sit at the single point where the confusion cannot
        # occur. "you" and "Thank you." are whisper's canonical output on
        # silence or a failed decode; "you" scored capture 0.0027 with a script
        # share of 1.00 and fired R1 — AUDIO PATH AT FAULT off a dead file.
        # The share test underneath is a proportion over a sample of size
        # len(hyp), and below this it has no power at all: one script word out
        # of one word is 100%.
        out["unalignable"] = True
        out["unalignable_reason"] = (
            f"the transcript is {len(hyp)} words against a {len(ref)}-word "
            f"script, under the {MIN_TRANSCRIPT_WORDS}-word floor. A dead "
            "recognizer emits a canned phrase — 'you', 'Thank you.' — and it "
            "is 100% script material by accident. Below this floor the "
            "script-share check that separates a wrong file from a starved "
            "microphone has nothing to measure")
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
    out["covered_span"] = _span(ops, len(ref))

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

    # EXTENT. The refusal above asks whether this transcript is about the right
    # script. This one asks whether it is about ALL of it. A transcript holding
    # the script's first 92 of 370 words is 100% script material and sailed
    # through — capture 0.25, and against a reference at 0.82 the harness
    # printed ENGINE AT FAULT and called the §8 migration justified on
    # evidence. The evidence was a quarter of a page.
    if out["covered_span"] < MIN_REFERENCE_SPAN:
        out["unalignable"] = True
        out["unalignable_reason"] = (
            f"the surviving words reach across {out['covered_span']:.0%} of the "
            f"script, under the {MIN_REFERENCE_SPAN:.0%} floor — this transcript "
            "is about part of the page, not the page. A recording that stopped "
            "early, a truncated write, a decoder that returned a partial and a "
            "microphone that went deaf halfway are one shape from here. Split "
            "the file, or say in the manifest what was actually read")
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
    attempts = cell.get("attempts")
    if attempts is None:
        blocked.append(
            f"{key} does not record how many times its recording was made. A "
            "credibility check that may be retried without record is a maximum "
            "over attempts, not a measurement — put \"attempts\" in the manifest")
        return None
    if attempts > MAX_RECORDING_ATTEMPTS:
        blocked.append(
            f"{key} was recorded {attempts} times, over the "
            f"{MAX_RECORDING_ATTEMPTS} the rule allows. Re-recording until a "
            "cell clears its floor — or until it reads like the expected "
            "finding — reports a maximum over attempts as if it were a "
            "measurement")
        return None
    return cell


def _distinct(cells, a_key, b_key):
    """Why these two cells cannot be subtracted from each other, or None.

    Every rule here is a subtraction, and the shape underneath all four of the
    reviewer's wrong headlines is that none of them asked whether the two cells
    came from different recordings. Two concrete ways they do not:

    * the scratch recorder's `contextualStrings` toggle is never wired, so
      arm_a/sf_ctx.txt and arm_a/sf_noctx.txt are the same bytes. Delta exactly
      +0.00 and R4 fires "the vocabulary API is inert" — the strongest possible
      signal for that rule is also the signature of the experiment never having
      been run.

    * one WAV decoded twice and filed as two arms, or one arm's transcript
      copied into the other's path.

    Identical text is not by itself proof of a copy — a genuinely inert biasing
    setting on a deterministic decoder over one WAV produces exactly that. That
    is why it takes provenance to tell them apart, and why identical text with
    NO provenance is refused rather than read as the finding it most resembles.
    """
    a, b = cells.get(a_key), cells.get(b_key)
    if a is None or b is None:
        return None

    a_prov, b_prov = a.get("provenance"), b.get("provenance")
    a_wav = (a_prov or {}).get("sha256")
    b_wav = (b_prov or {}).get("sha256")
    a_arm, b_arm = a_key.split("/")[0], b_key.split("/")[0]

    if a_wav and b_wav:
        if a_arm == b_arm and a_wav != b_wav:
            return (f"{a_key} and {b_key} are the same arm but name different "
                    f"source recordings ({a_wav[:12]} and {b_wav[:12]}) — two "
                    "decoders compared over two different files measure the "
                    "files, not the decoders")
        if a_arm != b_arm and a_wav == b_wav:
            return (f"{a_key} and {b_key} name the SAME source recording "
                    f"({a_wav[:12]}) — the arms differ by one audio-session "
                    "setting, so one recording filed as two is a delta of zero "
                    "manufactured by the filing")

    a_text, b_text = a.get("transcript_sha256"), b.get("transcript_sha256")
    if a_text and b_text and a_text == b_text:
        if a_arm != b_arm:
            return (f"{a_key} and {b_key} are byte-identical. Two separate "
                    "recordings of a several-hundred-word page do not decode "
                    "to the same bytes; this is one file in two places")
        if not (a_wav and b_wav):
            return (f"{a_key} and {b_key} are byte-identical and neither says "
                    "which recording it came from. A toggle that was never "
                    "wired and a setting that genuinely does nothing produce "
                    "the same bytes, and only the provenance line separates "
                    "them — see PROVENANCE_PREFIX")
    return None


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

    # The control calibrates the decoder ON THE SCRIPT ARM A WAS SCORED
    # AGAINST. A cell may name its own reference_script, and a twenty-word
    # passage read perfectly cleared the 0.85 floor and opened R1/R2 for a
    # 370-word arm A — a control that proved the decoder can manage one
    # sentence, standing in for a premise about a page.
    if credible and a_ref is not None and control is not None:
        c_words, a_words = control.get("ref_words"), a_ref.get("ref_words")
        if c_words is not None and a_words:
            if c_words < MIN_CONTROL_SCRIPT_RATIO * a_words:
                credible = False
                why = (
                    f"the control was scored against {c_words} words and arm A "
                    f"against {a_words} — under the "
                    f"{MIN_CONTROL_SCRIPT_RATIO:.0%} the rule requires. A short "
                    "passage read perfectly does not show the reference decoder "
                    "can hear THIS script, which is the only thing the control "
                    "is for")
                blocked.append(why)
                a_ref = None

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
        if a_app is not None:
            same = _distinct(cells, "A/reference", "A/sf_ctx")
            if same:
                app_blocked.append(same)
                a_app = None
        if a_app is None and cap < ENGINE_FAULT_REFERENCE_FLOOR:
            # Not None. R2's first clause has already failed on a cell that IS
            # present, so the missing one cannot change the answer — and saying
            # None here would let the headline chain below fall through to
            # INDETERMINATE with a printed reason that is factually false.
            # A measurement that does not matter and a measurement that decides
            # the verdict are different states, and only the second is None.
            blocked.extend(b for b in app_blocked if b not in blocked)
            findings.append({
                "rule": "R2", "id": "ENGINE_AT_FAULT", "fired": False,
                "because": (
                    f"the reference decoder captured {cap:.2f}, under the "
                    f"{ENGINE_FAULT_REFERENCE_FLOOR} floor R2 needs — the app's "
                    "own cell is unavailable, and no value it could take would "
                    f"fire R2 ({'; '.join(app_blocked)})")})
        elif a_app is None:
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
    # Arm A's transcript filed under arm B reverses this rule, and the
    # protocol's only mitigation was a sentence asking the operator to be
    # careful. Two recordings that are one recording are caught here.
    if a_app is not None and b_app is not None:
        same = _distinct(cells, "A/sf_ctx", "B/sf_ctx")
        if same:
            agc_blocked.append(same)
            a_app = None
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
    # The toggle that was never wired: two paths, one file, delta exactly
    # +0.00, and R4 fires hardest at the moment it is least entitled to.
    if with_ctx is not None and without is not None:
        same = _distinct(cells, "A/sf_ctx", "A/sf_noctx")
        if same:
            voc_blocked.append(same)
            with_ctx = None
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
    elif max(with_ctx["name_hits"] or 0, without["name_hits"] or 0) < MIN_NAME_HITS_EITHER_SIDE:
        # THE POSITIVE CONTROL R4 NEVER HAD. The mention counts above come from
        # the REFERENCE, so both arms always carry the same number: they
        # measure the script, not the data. Nothing required either decoder to
        # have heard a single name. A starved arm at 0/26 on both sides is a
        # delta of exactly 0.00 — the strongest possible "inert" verdict,
        # manufactured by the very outcome the experiment expects, and it fired
        # alongside R1 saying the audio was starved.
        findings.append({
            "rule": "R4", "id": "CONTEXTUAL_STRINGS_INERT", "fired": None,
            "because": (
                f"neither decoder heard a single one of the "
                f"{with_ctx['name_mentions']} vocabulary mentions. Zero against "
                "zero is not 'the biasing changed nothing', it is 'nothing was "
                "heard for the biasing to change' — and if R1 fired, that is "
                "what this arm is telling you")})
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
    # `or`, not `and`. With `and`, R1 False beside R2 None fell through to the
    # else and printed "INDETERMINATE — the reference decoder landed between the
    # two pre-registered thresholds" for a run whose reference decoder scored
    # 0.82, above the 0.75 floor: a missing measurement printed as a decided
    # verdict, with a false reason, decidable True, exit 0. That is verbatim the
    # sin this function's own docstring names. Either headline rule needing a
    # None is CANNOT DECIDE; R2 is made determinately False above wherever the
    # missing cell genuinely cannot change it, so nothing answerable is
    # withheld by this.
    if fired["R1"] is None or fired["R2"] is None:
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

#: THE ONE BIT THAT COSTS WEEKS, kept where a test can reach it.
#:
#: HEADLINE_MEANING above is prose, and prose was pinned by nothing: reversing
#: "AUDIO PATH AT FAULT" to read "the engine could not decode it. Migrate."
#: left 57 of 57 tests green. Pre-registration is a promise about a document
#: the operator reads, and that document was free to disagree with the code
#: that produced it.
#:
#: Two things now stop that. This map holds the single decision each headline
#: licenses as a BOOLEAN, pinned literally in
#: tests/test_engine_or_audio.py alongside the nine thresholds; render() prints
#: the instruction from it rather than from the sentence, so the sentence
#: cannot be the only thing carrying the direction. And the sentences
#: themselves are pinned literally too, for the same reason the numbers are:
#: moving one has to be an edit to a test with a name that asks why.
HEADLINE_LICENSES_MIGRATION = {
    "AUDIO PATH AT FAULT": False,
    "ENGINE AT FAULT": True,
    "INDETERMINATE": None,
    "CANNOT DECIDE": None,
}

#: What render() prints under the verdict, generated from the boolean above.
MIGRATION_VERDICT = {
    True: "the §8 engine migration IS licensed by this run.",
    False: "the §8 engine migration is NOT licensed by this run.",
    None: "this run licenses no decision about the §8 engine migration.",
}


# ---------------------------------------------------------------------------
# Reading a run off disk
# ---------------------------------------------------------------------------

def _empty_cell(reason: str) -> dict:
    """A cell with no rates and a reason. Every rate is None rather than 0.0 so
    arithmetic on a missing measurement raises instead of publishing."""
    return {
        "ref_words": 0, "hyp_words": 0,
        "matched": 0, "substituted": 0, "deleted": 0, "inserted": 0,
        "capture_rate": None, "wer": None, "insertion_rate": None,
        "longest_run": 0, "matched_in_runs": 0.0, "script_share": None,
        "covered_span": 0.0,
        "names": {}, "name_mentions": 0, "name_hits": 0,
        "name_hit_rate": None, "unalignable": True,
        "unalignable_reason": reason,
        "provenance": None, "transcript_sha256": None,
    }


def _provenance_mismatch(provenance, arm: str, decoder: str):
    """Why this transcript does not belong in the cell it was filed under.

    The arm swap: arm A's transcript filed under arm B reverses R3, and two
    recordings of the same page are identical from any arithmetic. The only
    thing that separates them is the recorder saying which one it wrote.
    """
    if not provenance:
        return None
    said_arm = provenance.get("arm")
    if said_arm and said_arm != arm:
        return (f"this transcript says it was recorded on arm {said_arm}, and "
                f"it is filed as arm {arm}. Two recordings of the same page are "
                "identical to any arithmetic here; the provenance line is the "
                "only thing that can catch a swap, and it just did")
    said_decoder = provenance.get("decoder")
    if said_decoder and said_decoder != decoder:
        return (f"this transcript says it came from {said_decoder}, and it is "
                f"filed as {decoder}. The vocabulary question is decided by "
                "subtracting one of these from the other")
    return None


def load_run(run_dir: str) -> dict:
    """A run directory is a manifest plus the text files it names.

    manifest.json:
        {"run_id": "...", "recorded_at": "...",
         "reference_script": "script.txt",
         "vocabulary": ["Anticipy", "Tejas", ...],
         "attempts": {"A": 1, "B": 1, "C": 1},
         "cells": [{"arm": "A", "decoder": "sf_ctx",
                    "transcript": "arm_a/sf_ctx.txt"}, ...]}

    Paths are relative to the run directory. Everything is plain text: the
    scratch recorder writes a transcript per cell, and nothing here needs a
    parser that could disagree with the thing that wrote it.

    `attempts` is how many times each arm was RECORDED, and it is required —
    see MAX_RECORDING_ATTEMPTS. Each transcript may open with a provenance line
    (PROVENANCE_PREFIX); it is stripped before scoring, checked against the
    cell it was filed under, and it is the only thing that can tell an inert
    setting from a toggle that was never wired.
    """
    manifest_path = os.path.join(run_dir, "manifest.json")
    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)

    def read(rel):
        with open(os.path.join(run_dir, rel), encoding="utf-8") as fh:
            return fh.read()

    reference = read(manifest["reference_script"])
    vocabulary = manifest.get("vocabulary") or []
    attempts = manifest.get("attempts") or {}
    scored = {}
    for cell in manifest.get("cells", []):
        arm, decoder = cell["arm"], cell["decoder"]
        if arm not in ARMS:
            raise ValueError(f"unknown arm {arm!r}; known: {sorted(ARMS)}")
        if decoder not in DECODERS:
            raise ValueError(f"unknown decoder {decoder!r}; known: {sorted(DECODERS)}")
        # A cell may name its own script: if the control arm reads a shorter
        # passage, scoring it against the full script would report the unread
        # remainder as lost words. MIN_CONTROL_SCRIPT_RATIO bounds how much
        # shorter, because "the decoder managed one sentence" is not the
        # premise R1 and R2 are drawn from.
        ref = read(cell["reference_script"]) if cell.get("reference_script") else reference
        key = f"{arm}/{decoder}"
        try:
            raw = read(cell["transcript"])
            provenance = parse_provenance(raw)
            body = strip_provenance(raw)
            scored[key] = score(ref, body, vocabulary)
            scored[key]["provenance"] = provenance
            scored[key]["transcript_sha256"] = hashlib.sha256(
                " ".join(tokens(body)).encode("utf-8")).hexdigest()
            mismatch = _provenance_mismatch(provenance, arm, decoder)
            if mismatch and not scored[key]["unalignable"]:
                # The arm swap the report conceded was undetectable. It was —
                # two recordings of the same page, and no arithmetic separates
                # them. What separates them is the recorder saying which one it
                # wrote, and the recorder does not exist yet, so the contract
                # can still require it.
                scored[key]["unalignable"] = True
                scored[key]["unalignable_reason"] = mismatch
                for rate in ("capture_rate", "wer", "insertion_rate",
                             "name_hit_rate"):
                    scored[key][rate] = None
        except ValueError as exc:
            # align() refuses a mis-supplied book rather than swapping the
            # machine, and that refusal used to escape as a traceback because
            # only FileNotFoundError was caught. A refusal that crashes the
            # harness is a refusal nobody reads.
            scored[key] = _empty_cell(str(exc))
        except FileNotFoundError:
            # A half-finished run is the normal case, not an error: arms A and B
            # can be flown on a phone alone, days before anybody gets a
            # reference decoder pointed at the WAVs. Crashing on the empty cell
            # would withhold R3 — the one rule with a one-line fix behind it.
            scored[key] = _empty_cell(f"no transcript at {cell['transcript']!r}")
        # How many times this arm was recorded. Absent is not assumed innocent:
        # _usable() blocks on None, because an unrecorded attempt count and a
        # ninth attempt are the same evidence from here.
        scored[key]["attempts"] = attempts.get(arm)
    return {"manifest": manifest, "cells": scored}


def scaffold(run_dir: str, script_path: str, vocabulary=None) -> str:
    """Lay out an empty run so nobody has to hand-write JSON while holding a
    phone. Every cell is listed; the ones nobody fills in come back REFUSED
    with the missing path named, which is the honest state of a partial run."""
    # EXACTLY THE CELLS A RULE READS, and no others. This used to lay out nine
    # paths — every arm crossed with every decoder — including two
    # `speech_transcriber` cells the protocol never mentions and three the
    # rules never look at. A correctly-run experiment therefore printed four
    # REFUSED lines that were NORMAL, which teaches the reader to skim past
    # REFUSED. Every refusal in this harness is a line it needs a human to
    # notice, and four false ones a run is how the true one gets missed.
    # An iOS 26 device with SpeechTranscriber to hand: add the cell to the
    # manifest by hand. It is three lines of JSON, and then its REFUSED means
    # something too.
    cells = [
        {"arm": "C", "decoder": "reference", "transcript": "arm_c/reference.txt"},
        {"arm": "A", "decoder": "reference", "transcript": "arm_a/reference.txt"},
        {"arm": "A", "decoder": "sf_ctx", "transcript": "arm_a/sf_ctx.txt"},
        {"arm": "A", "decoder": "sf_noctx", "transcript": "arm_a/sf_noctx.txt"},
        {"arm": "B", "decoder": "sf_ctx", "transcript": "arm_b/sf_ctx.txt"},
    ]
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
        # How many times each arm was RECORDED, not decoded. Written as 1 and
        # meant to be corrected upward by the operator: a re-take is legitimate
        # and unlimited re-takes are a maximum over attempts wearing a
        # measurement's clothes. See MAX_RECORDING_ATTEMPTS.
        "attempts": {"A": 1, "B": 1, "C": 1},
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
                 f"{'script%':>9}{'span':>7}{'names':>9}{'run':>6}")
    for key in sorted(run["cells"]):
        c = run["cells"][key]
        if c["unalignable"]:
            lines.append(f"{key:<26}{'REFUSED':>9}   {c['unalignable_reason']}")
            continue
        names = ("n/a" if c["name_hit_rate"] is None
                 else f"{c['name_hits']}/{c['name_mentions']}")
        # `span` is not a diagnostic. MIN_REFERENCE_SPAN reads it, and it is
        # the column that says whether this cell is evidence about the page or
        # about the top of the page.
        lines.append(f"{key:<26}{c['capture_rate']:>9.2f}{c['wer']:>7.2f}"
                     f"{c['insertion_rate']:>7.2f}{c['script_share']:>9.2f}"
                     f"{c['covered_span']:>7.2f}{names:>9}{c['longest_run']:>6}")
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
    # Printed from HEADLINE_LICENSES_MIGRATION, not from the sentence above, so
    # the one bit that costs weeks is carried by something a test can pin.
    lines.append(f"         {MIGRATION_VERDICT[HEADLINE_LICENSES_MIGRATION[v['headline']]]}")
    for b in v["blocked"]:
        lines.append(f"  blocked: {b}")
    lines.append("")
    lines.append("Law 3: this is a measurement of files, not of production. It "
                 "says nothing about the live system until a build carrying the "
                 "winning change is verified on the device.")
    return "\n".join(lines)


def explain() -> str:
    """The document the operator reads before recording anything.

    EVERY NUMBER HERE IS INTERPOLATED FROM THE CONSTANT THE CODE BRANCHES ON,
    and tests/test_engine_or_audio.py checks that the set of numbers printed
    here is exactly the set of pre-registered thresholds — no more and no
    fewer. That test exists because this function was made to advertise a
    control floor of 0.60 while the code enforced 0.85, and 57 of 57 tests
    stayed green. A pre-registered rule the operator can read and the code can
    contradict is not pre-registration, it is a leaflet.
    """
    out = ["THE DECISION RULE, PRE-REGISTERED "
           "(research/2026-08-24-engine-options.md §11)", ""]
    out.append("Validity gate, before any verdict about the engine:")
    out.append(f"  the reference decoder must capture >= {CONTROL_CREDIBILITY_FLOOR} "
               "on arm C, the clean close-mic control.")
    out.append(f"  Below that it is a weak decoder, not a starved microphone, and "
               "R1 and R2 are unavailable.")
    out.append(f"  arm C must be scored against at least {MIN_CONTROL_SCRIPT_RATIO} "
               "of arm A's script — a short passage read")
    out.append("  perfectly does not show the decoder can hear THIS page.")
    out.append(f"  no arm may have been recorded more than {MAX_RECORDING_ATTEMPTS} "
               "times, and the manifest must say how")
    out.append("  many. A floor that may be retried without record is a maximum "
               "over attempts.")
    out.append("")
    out.append("Before any cell is scored at all:")
    out.append(f"  the transcript must be >= {MIN_TRANSCRIPT_WORDS} words "
               f"(and the script >= {MIN_REFERENCE_WORDS}), or the")
    out.append("  script-share check below has no sample to work on — 'you' is "
               "100% script material.")
    out.append(f"  >= {MIN_SCRIPT_SHARE} of the transcript must be script words in "
               f"order, unless capture >= {ANCHOR_EXEMPT_CAPTURE}.")
    out.append(f"  insertions must be <= {MAX_INSERTION_RATE} x the script length.")
    out.append(f"  the surviving words must reach across >= {MIN_REFERENCE_SPAN} of "
               "the script, first to last. A")
    out.append("  transcript about the top of the page is not a measurement of "
               "the page.")
    out.append("  two cells that are subtracted from each other must be shown to "
               "come from different")
    out.append("  recordings — see the provenance line in "
               "proof/RECORDING-PROTOCOL.md.")
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
    out.append(f"                         and >= {MIN_NAME_HITS_EITHER_SIDE} name "
               "actually HEARD on one side or the other:")
    out.append("                         zero against zero is a starved arm, not "
               "an inert setting")
    out.append("")
    out.append("What each verdict licenses:")
    for headline, licensed in HEADLINE_LICENSES_MIGRATION.items():
        out.append(f"  {headline:<22} {MIGRATION_VERDICT[licensed]}")
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
