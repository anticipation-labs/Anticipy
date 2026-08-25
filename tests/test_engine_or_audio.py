"""The scorer has to be able to give a wrong answer, and be caught giving it.

These drive proof/engine_or_audio.py's pure half with synthetic reference /
transcript pairs where the right answer is known by construction — no audio, no
decoder, no network. The case that matters most is the 30% one: the entire
engine-versus-audio-path decision turns on whether a strong decoder loses about
a third of the words off the same file, so a scorer that cannot be shown
returning exactly 0.70 on a pair built to lose exactly 30% is not evidence of
anything.

The second thing they cover is refusal. proof/capture_day.py's own docstring
records what this repo keeps getting burned by — a measuring stick that quietly
reports a flattering number instead of failing. A transcript that cannot be
matched to its script must come back with no rate at all, not with a low one
that reads as "the audio was starved."
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from proof.engine_or_audio import (  # noqa: E402
    load_run,
    scaffold,
    AGC_WIN_MARGIN,
    ANCHOR_EXEMPT_CAPTURE,
    CONTEXTUAL_STRINGS_INERT_BAND,
    CONTROL_CREDIBILITY_FLOOR,
    ENGINE_FAULT_MIN_GAP,
    ENGINE_FAULT_REFERENCE_FLOOR,
    HEADLINE_LICENSES_MIGRATION,
    HEADLINE_MEANING,
    MAX_RECORDING_ATTEMPTS,
    MIN_CONTROL_SCRIPT_RATIO,
    MIN_NAME_HITS_EITHER_SIDE,
    MIN_NAME_MENTIONS,
    MIN_REFERENCE_SPAN,
    MIN_REFERENCE_WORDS,
    MIN_TRANSCRIPT_WORDS,
    MAX_INSERTION_RATE,
    SPAN_TRIM,
    MIN_SCRIPT_SHARE,
    STARVED_AUDIO_CEILING,
    align,
    explain,
    main,
    render,
    score,
    tokens,
    verdict,
)

VOCAB = ["Anticipy", "Tejas", "OpenTrade", "pendant"]


def numbered(n, start=1):
    """A reference of n unique tokens. Unique matters: with no repeats the
    alignment has exactly one optimal path, so an expected number in a test is
    an arithmetic fact rather than a tie-break the implementation happened to
    pick."""
    return " ".join(f"word{i}" for i in range(start, start + n))


# ---------------------------------------------------------------------------
# Tokenisation — what counts as a word, and what must never be normalised away
# ---------------------------------------------------------------------------

def test_case_and_edge_punctuation_do_not_decide():
    # The failure this product has is "anticipate" for "Anticipy" — a different
    # word. A capital letter is not that failure, and a decoder that lowercases
    # everything must not be scored as having lost every word.
    assert tokens("Anticipy, Tejas!") == tokens("anticipy tejas")


def test_a_time_is_not_normalised_into_words():
    # The recorded act goal that started all of this contained "5:15". A scorer
    # that split it, or folded it into "five fifteen", would hide exactly the
    # class of failure the eval exists to catch. Asserting the two are merely
    # unequal was too weak to pin that — a tokenizer that splits on the colon
    # also makes them unequal, and mutation testing caught the gap.
    assert tokens("at 5:15") == ["at", "5:15"]
    assert tokens("at 5:15") != tokens("at five fifteen")


def test_a_hyphen_is_a_word_break_in_both_directions():
    # Decoders disagree on hyphenation with no acoustic content behind the
    # disagreement, so scoring "far-field" against "far field" as a loss would
    # be measuring the writer's typing.
    assert tokens("far-field capture") == tokens("far field capture")


# ---------------------------------------------------------------------------
# Word capture — the number the decision turns on
# ---------------------------------------------------------------------------

def test_a_perfect_transcript_is_one_hundred_percent_and_zero_error():
    ref = numbered(40)
    s = score(ref, ref, VOCAB)
    assert s["capture_rate"] == 1.0
    assert s["wer"] == 0.0
    assert s["insertion_rate"] == 0.0
    assert s["unalignable"] is False


def test_a_pair_built_to_lose_exactly_thirty_percent_scores_exactly_seventy():
    """THE measurement. 100 reference words, 30 of them dropped in bursts of
    three — the shape production actually shows, where a span goes missing
    rather than every third word. If this cannot return 0.70 the whole
    experiment reports a number nobody should believe."""
    ref_words = [f"word{i}" for i in range(100)]
    # Drop the last three of every block of ten: 10 bursts x 3 = 30 words.
    kept = [w for i, w in enumerate(ref_words) if i % 10 < 7]
    assert len(kept) == 70

    s = score(" ".join(ref_words), " ".join(kept), VOCAB)
    assert s["capture_rate"] == 0.70
    assert s["deleted"] == 30
    assert s["substituted"] == 0
    assert s["inserted"] == 0
    assert s["wer"] == 0.30
    assert s["unalignable"] is False, (
        "losing 30% is the expected result of the experiment, not a reason to "
        "refuse to score it"
    )


def test_capture_rate_and_word_error_rate_are_different_numbers():
    """Capture rate is what the product cares about — what fraction of what was
    said survived. WER punishes a decoder for inventing words too. A decoder
    that repeats every word it hears loses nothing and is still unusable, so
    reporting only capture rate would call it perfect."""
    ref = numbered(20)
    doubled = " ".join(f"word{i} word{i}" for i in range(1, 21))

    s = score(ref, doubled, VOCAB)
    assert s["capture_rate"] == 1.0, "every spoken word survived"
    assert s["inserted"] == 20
    assert s["insertion_rate"] == 1.0
    assert s["wer"] == 1.0, "and the transcript is still twice as long as truth"


def test_the_same_words_in_the_wrong_order_is_not_a_perfect_capture():
    # A bag-of-words score would call this thirty out of thirty. Order is the
    # only thing separating a transcript from a word cloud.
    ref = numbered(30)
    shuffled = " ".join(reversed(ref.split()))
    s = score(ref, shuffled, VOCAB)
    assert s["matched"] <= 2
    assert s["unalignable"] is True, "and no rate is published off it"


def test_a_substituted_word_is_a_loss_not_a_survival():
    ref = numbered(30)
    hyp = ref.replace("word4", "banana")
    s = score(ref, hyp, VOCAB)
    assert s["substituted"] == 1
    assert s["deleted"] == 0
    assert s["capture_rate"] == 29 / 30


# ---------------------------------------------------------------------------
# Product names — the load-bearing vocabulary
# ---------------------------------------------------------------------------

def test_the_product_name_heard_as_anticipate_is_a_miss_and_the_miss_is_named():
    """The recorded incident: "anticipy growth dot com" arrived as "anticipate
    growth there's something.com" and the assistant offered to buy the
    misspelling. Counting the miss is half the job — saying WHAT it became is
    what tells you whether contextualStrings moved anything."""
    ref = ("we should register Anticipy growth dot com before someone else "
           "does and then point it at the marketing page we already wrote "
           "last week")
    hyp = ("we should register anticipate growth dot com before someone else "
           "does and then point it at the marketing page we already wrote "
           "last week")

    s = score(ref, hyp, VOCAB)
    assert s["names"]["Anticipy"]["mentions"] == 1
    assert s["names"]["Anticipy"]["hits"] == 0
    assert s["names"]["Anticipy"]["heard_as"] == {"anticipate": 1}
    assert s["name_hit_rate"] == 0.0


def test_a_name_that_was_dropped_entirely_is_recorded_as_dropped():
    # A dropped name and a mangled name have different fixes: one is capture,
    # the other is biasing. Folding them into one "miss" count would hide which.
    ref = ("tell Tejas the pendant is charging on the desk next to the window "
           "and it should be full again by the time the meeting starts")
    hyp = ("tell the pendant is charging on the desk next to the window "
           "and it should be full again by the time the meeting starts")
    s = score(ref, hyp, VOCAB)
    assert s["names"]["Tejas"]["hits"] == 0
    assert s["names"]["Tejas"]["dropped"] == 1
    assert s["names"]["Tejas"]["heard_as"] == {}


def test_every_mention_is_counted_not_just_the_first():
    ref = ("Anticipy heard me say Anticipy and then wrote down Anticipy in the "
           "notes it keeps for the morning so nothing gets lost overnight")
    hyp = ("anticipate heard me say Anticipy and then wrote down anticipate in "
           "the notes it keeps for the morning so nothing gets lost overnight")
    s = score(ref, hyp, VOCAB)
    assert s["names"]["Anticipy"]["mentions"] == 3
    assert s["names"]["Anticipy"]["hits"] == 1
    assert s["name_hit_rate"] == 1 / 3


def test_a_two_word_name_is_only_a_hit_when_both_words_survive():
    # The vocabulary carries the owner's first AND last name. Half a name
    # resolves in Contacts as confidently as a whole one, and to the wrong
    # human — so half a name is a miss.
    ref = ("ask Jose Cruz whether Jose Cruz signed the renewal already or "
           "whether it is still sitting in the folder waiting on somebody")
    hyp = ("ask Jose Cruz whether Jose Cruise signed the renewal already or "
           "whether it is still sitting in the folder waiting on somebody")
    s = score(ref, hyp, ["Jose Cruz"])
    assert s["names"]["Jose Cruz"]["mentions"] == 2
    assert s["names"]["Jose Cruz"]["hits"] == 1


def test_one_name_split_into_two_words_is_reported_as_the_two_words():
    """Caught by running the real decoder over the real script: whisper heard
    "OpenTrade" as "open trade" and the report said heard as 'trade', because
    only one of the two words aligned and the other was an insertion. A miss
    reported as half of what it became sends whoever reads it looking for the
    wrong bug. It is still a miss — "open trade" does not match a company name
    downstream, and producing the spelling is what the vocabulary is for."""
    ref = ("the OpenTrade account is the one that matters here and nobody has "
           "looked at it properly since the spring so it is overdue")
    hyp = ("the open trade account is the one that matters here and nobody has "
           "looked at it properly since the spring so it is overdue")
    s = score(ref, hyp, VOCAB)
    assert s["names"]["OpenTrade"]["hits"] == 0
    assert s["names"]["OpenTrade"]["heard_as"] == {"open trade": 1}


def test_a_hallucinated_paragraph_beside_a_name_is_not_reported_as_the_name():
    # The other half of the same fix: sweeping up adjacent insertions must be
    # bounded, or a looping decoder attributes its whole loop to the nearest
    # product name.
    ref = ("we should ask Tejas about the renewal before the end of the week "
           "because nobody else has the history on it")
    hyp = ("we should ask a b c d e f g about the renewal before the end of "
           "the week because nobody else has the history on it")
    s = score(ref, hyp, VOCAB)
    assert s["names"]["Tejas"]["hits"] == 0
    heard = " ".join(s["names"]["Tejas"]["heard_as"])
    assert len(heard.split()) <= 5


def test_a_vocabulary_term_nobody_said_does_not_dilute_the_rate():
    # OpenTrade never occurs here. Counting it as a mention with zero hits
    # would report a name failure that never had the chance to happen.
    ref = ("the pendant is on the table by the door and it has been sitting "
           "there since yesterday afternoon without anybody picking it up")
    s = score(ref, ref, VOCAB)
    assert s["names"]["OpenTrade"]["mentions"] == 0
    assert s["name_hit_rate"] == 1.0


def test_no_mentions_at_all_gives_no_rate_rather_than_a_flattering_one():
    ref = numbered(30)
    s = score(ref, ref, VOCAB)
    assert s["name_mentions"] == 0
    assert s["name_hit_rate"] is None, (
        "zero of zero is not 100%, and printing 100% would advertise a "
        "vocabulary that was never tested"
    )


# ---------------------------------------------------------------------------
# Refusal — the part that exists because flattering numbers keep shipping
# ---------------------------------------------------------------------------

def test_an_empty_transcript_gets_no_rate_and_says_why_it_got_none():
    """0% capture and "you handed me the wrong file" produce identical bytes.
    The harness cannot tell them apart, so it must not pick one — least of all
    the one that reads as a dramatic finding."""
    s = score(numbered(50), "", VOCAB)
    assert s["unalignable"] is True
    assert s["capture_rate"] is None
    assert s["wer"] is None
    assert "empty" in s["unalignable_reason"].lower()


def test_a_transcript_of_a_different_script_is_refused_not_scored_low():
    """The failure that would ruin this experiment quietly: arm B's transcript
    filed against arm A's script. Common words still match, so it scores
    somewhere near 20% — and 20% reads exactly like "the audio was starved.\""""
    ref = ("the quarterly review moved to the morning and the finance team "
           "will bring the revised deck with them so we can go through the "
           "pricing before lunch")
    hyp = ("a completely different sentence about the weather and the traffic "
           "on the bridge this evening and nothing whatsoever to do with any "
           "of that other material")
    s = score(ref, hyp, VOCAB)
    assert s["unalignable"] is True
    assert s["capture_rate"] is None
    assert "script" in s["unalignable_reason"].lower()


def test_a_catastrophically_starved_recording_is_still_scored_not_refused():
    """A 7% capture rate is a real, terrible result and the most damning
    finding this experiment could produce. It is NOT a wrong file: every word
    in the transcript is a script word, and they are spread the whole way down
    the page, which is what a microphone losing words looks like.

    THIS FIXTURE CHANGED, DELIBERATELY, and the reasoning matters more than the
    numbers. It used to be four words out of sixty — the reference's first four
    — and that shape is not starvation, it is truncation: a recording that
    stopped, a partial from SFSpeechURLRecognitionRequest, a truncated write.
    Reading it as "the microphone captured 7%" is precisely the confusion that
    let a transcript holding the script's first quarter print ENGINE AT FAULT.
    The property this test protects — a catastrophic capture is a finding, not
    a reason to refuse — is protected here at a scale where the evidence
    exists. Its companion below pins the truncated shape as refused."""
    ref_words = [f"word{i}" for i in range(300)]
    # Every fourteenth word survives, all the way down the page.
    heard = [w for i, w in enumerate(ref_words) if i % 14 == 0]
    assert len(heard) == 22

    s = score(" ".join(ref_words), " ".join(heard), VOCAB)
    assert s["script_share"] == 1.0
    assert s["unalignable"] is False
    assert s["capture_rate"] == 22 / 300
    assert s["capture_rate"] < 0.08, "as bad as anything the experiment can report"


def test_a_transcript_holding_only_the_top_of_the_page_is_refused():
    """C1, the headline this instrument could be made to print. A transcript
    holding the script's first 92 of 370 words is 100% script material, sails
    through every share and insertion check, and scores capture 0.25 — which
    against a reference decoder at 0.82 fired R2 and printed "ENGINE AT FAULT
    ... the §8 migration is justified on evidence." The evidence was a quarter
    of a page.

    The harness already computed the discriminating numbers and refused to read
    them: longest_run 90 and matched_in_runs 1.00, both marked DIAGNOSTIC ONLY.
    A truncated recording, a partial result, a truncated write and a microphone
    that died halfway are four bugs of one shape from here, so the cell is
    refused and names them."""
    ref_words = [f"word{i}" for i in range(370)]
    s = score(" ".join(ref_words), " ".join(ref_words[:92]), VOCAB)
    assert s["script_share"] == 1.0, "every word of it IS script material"
    assert s["longest_run"] >= 90, "and it reads as a clean run of the script"
    assert s["unalignable"] is True
    assert s["capture_rate"] is None, "0.25 reads exactly like the headline finding"
    assert "part of the page" in s["unalignable_reason"]


def test_a_transcript_of_only_the_middle_of_the_page_is_refused_too():
    """The generalisation, not the instance. C1 was a prefix because that is
    what a truncated write produces; the rule is about reach, so a window
    anywhere in the script fails it the same way. Four independent patches
    against four reported symptoms would have left this one open."""
    ref_words = [f"word{i}" for i in range(370)]
    s = score(" ".join(ref_words), " ".join(ref_words[120:230]), VOCAB)
    assert s["unalignable"] is True
    assert "part of the page" in s["unalignable_reason"]


def test_the_span_floor_is_a_boundary_not_a_direction():
    """MIN_REFERENCE_SPAN is one of the comparisons the reviewer showed could
    be inverted with every test still green. A pair either side of it, so
    flipping `<` to `>` cannot pass."""
    ref_words = [f"word{i}" for i in range(1000)]
    # Survivors spread evenly across a prefix of the script, so the covered
    # span is that prefix's length. `_span` trims a tenth off each end and
    # rescales, so an evenly-spread window reads back as its own width.
    def spread(width):
        return " ".join(ref_words[i] for i in range(0, width, 5))

    below = score(" ".join(ref_words), spread(650), VOCAB)
    above = score(" ".join(ref_words), spread(800), VOCAB)
    assert below["covered_span"] < MIN_REFERENCE_SPAN <= above["covered_span"]
    assert below["unalignable"] is True
    assert above["unalignable"] is False, (
        "a transcript that reaches the whole page is scored however bad it is")


def test_a_thirty_percent_capture_made_of_three_word_bursts_is_scored():
    """The shape production actually shows — "All of these", "Help me
    understand" — never reaches four consecutive words. An earlier draft gated
    on run length and refused exactly this, which is the case the whole
    experiment exists to measure."""
    ref_words = [f"word{i}" for i in range(100)]
    bursty = [w for i, w in enumerate(ref_words) if i % 10 < 3]
    s = score(" ".join(ref_words), " ".join(bursty), VOCAB)
    assert s["longest_run"] == 3, "no four-word anchor anywhere"
    assert s["unalignable"] is False
    assert s["capture_rate"] == 0.30


def test_free_conversation_recorded_into_the_script_file_is_refused():
    """Found by building the refusal, not by running the experiment: §11 asks
    for a scripted half and a free-talking half in one ten-minute recording. If
    both land in one transcript, the free half is thousands of insertions
    against a script that never contained them — the WER goes to nonsense and
    the transcript stops looking like the script at all. The protocol therefore
    has to ask for two files, and this is the check that catches it when
    somebody forgets."""
    ref = numbered(40)
    both = ref + " " + " ".join(
        f"chatter{i}" for i in range(120))
    s = score(ref, both, VOCAB)
    assert s["unalignable"] is True
    assert "same file as the script" in s["unalignable_reason"]
    assert s["capture_rate"] is None, (
        "the capture number here would even be RIGHT — the script survived. "
        "Publishing it beside a word error rate of three would be the worst "
        "of both, so the cell publishes nothing")


def test_a_reference_too_short_to_support_a_rate_is_refused():
    s = score("only a handful of words here", "only a handful of words here", VOCAB)
    assert s["unalignable"] is True
    assert str(MIN_REFERENCE_WORDS) in s["unalignable_reason"]


# ---------------------------------------------------------------------------
# Alignment internals
# ---------------------------------------------------------------------------

def test_the_alignment_that_survives_a_tie_is_the_one_that_finds_the_match():
    """Two alignments of "a b" against "b a" cost two edits each: two
    substitutions, which find nothing, or delete-match-insert, which finds
    "b". A plain Levenshtein backtrace picks whichever the loop happened to
    check first — so the capture rate, the number this entire experiment turns
    on, would depend on a tie-break rather than on the audio.

    Found by mutation testing: reversing the tie-break preference changed no
    test, which meant nothing was pinning it."""
    ops = align(["a", "b"], ["b", "a"])
    assert sum(1 for kind, _, _ in ops if kind == "equal") == 1


def test_the_tie_break_never_buys_a_match_with_extra_edits():
    """The other direction, and the harder one: maximising matches has to stay
    strictly subordinate to the edit distance. Weight them equally and the
    scorer starts preferring elaborate alignments that pick up one more word at
    the price of one more edit — a bad transcript scoring better than it is.

    This pair was found by searching for it, not invented: with the two
    objectives weighted equally the alignment costs five edits, and the true
    edit distance is four."""
    ops = align(list("ebdce"), list("bbebed"))
    assert sum(1 for kind, _, _ in ops if kind != "equal") == 4


def test_an_absurdly_large_pair_is_refused_before_it_swaps_the_machine():
    # The table is len(ref) x len(hyp). A transcript file that turns out to be
    # a book should say so, not allocate for a minute and die.
    import pytest
    with pytest.raises(ValueError, match="wrong pair of files"):
        align(["w"] * 6000, ["w"] * 6000)


def test_alignment_reports_one_operation_per_reference_word_plus_insertions():
    ops = align(["a", "b", "c"], ["a", "x", "b", "c"])
    kinds = [o[0] for o in ops]
    assert kinds.count("insert") == 1
    assert len([k for k in kinds if k != "insert"]) == 3


# ---------------------------------------------------------------------------
# The pre-registered decision rule
# ---------------------------------------------------------------------------

def test_the_thresholds_are_pinned_so_moving_one_is_a_visible_act():
    """These numbers were written down before any recording existed, from
    research/2026-08-24-engine-options.md §11. Pinning them means a later
    session cannot slide a threshold to meet a result it has already seen —
    it has to edit this test and explain itself in the diff."""
    assert STARVED_AUDIO_CEILING == 0.45
    assert ENGINE_FAULT_REFERENCE_FLOOR == 0.75
    assert ENGINE_FAULT_MIN_GAP == 0.30
    assert AGC_WIN_MARGIN == 0.15
    assert CONTEXTUAL_STRINGS_INERT_BAND == 0.10
    assert MIN_NAME_MENTIONS == 8
    assert CONTROL_CREDIBILITY_FLOOR == 0.85
    assert MIN_SCRIPT_SHARE == 0.50
    assert MAX_INSERTION_RATE == 1.00
    assert MIN_REFERENCE_SPAN == 0.70
    assert MIN_TRANSCRIPT_WORDS == 20
    assert MIN_NAME_HITS_EITHER_SIDE == 1
    assert MIN_CONTROL_SCRIPT_RATIO == 0.80
    assert MAX_RECORDING_ATTEMPTS == 2
    # SPAN_TRIM is pinned here rather than by a behaviour test on purpose. The
    # span metric rescales by the trim, so widening it barely moves a uniformly
    # spread transcript — which is exactly why it needs pinning by declaration:
    # a constant with no behavioural signature is a constant a later session
    # can move without anything going red.
    assert SPAN_TRIM == 0.10


def cell(capture=None, name_rate=None, mentions=0, unalignable=False, reason="",
         ref_words=370, attempts=1, hits=None, digest=None, provenance=None):
    """One scored cell as verdict() sees it.

    `ref_words` and `attempts` are not decoration. The validity gate reads both:
    a control scored against a twenty-word passage does not calibrate a decoder
    for a 370-word arm A, and a control re-recorded until it cleared its floor
    is a maximum over attempts rather than a measurement. Defaulting them to
    the honest case here keeps the rule tests about the rule."""
    if hits is None:
        # Enough hits to clear R4's positive control unless a test says
        # otherwise. Zero against zero is a starved arm, not an inert setting.
        hits = 0 if not name_rate else max(1, round((name_rate or 0) * mentions))
        if name_rate == 0.0 and mentions:
            hits = 0
    return {
        "capture_rate": capture,
        "name_hit_rate": name_rate,
        "name_mentions": mentions,
        "name_hits": hits,
        "unalignable": unalignable,
        "unalignable_reason": reason,
        "ref_words": ref_words,
        "attempts": attempts,
        "transcript_sha256": digest,
        "provenance": provenance,
    }


def full_run(**over):
    cells = {
        "C/reference": cell(capture=0.95),
        "A/reference": cell(capture=0.40),
        "A/sf_ctx": cell(capture=0.32, name_rate=0.10, mentions=12),
        "A/sf_noctx": cell(capture=0.31, name_rate=0.08, mentions=12),
        "B/sf_ctx": cell(capture=0.36, name_rate=0.12, mentions=12),
    }
    cells.update(over)
    return cells


def fired(v, rule):
    return next(f for f in v["findings"] if f["rule"] == rule)["fired"]


def test_a_reference_decoder_that_also_loses_the_words_exonerates_the_engine():
    v = verdict(full_run(**{"A/reference": cell(capture=0.40)}))
    assert fired(v, "R1") is True
    assert fired(v, "R2") is False
    assert v["headline"] == "AUDIO PATH AT FAULT"


def test_a_reference_decoder_that_hears_fine_convicts_the_engine():
    v = verdict(full_run(**{
        "A/reference": cell(capture=0.88),
        "A/sf_ctx": cell(capture=0.32, name_rate=0.10, mentions=12),
    }))
    assert fired(v, "R2") is True
    assert fired(v, "R1") is False
    assert v["headline"] == "ENGINE AT FAULT"


def test_a_reference_decoder_in_the_middle_decides_nothing_and_says_so():
    """0.60 is the number that gets argued about. Pre-registering the band
    means it gets reported as undecided instead of read as whichever answer the
    reader arrived with."""
    v = verdict(full_run(**{"A/reference": cell(capture=0.60)}))
    assert fired(v, "R1") is False
    assert fired(v, "R2") is False
    assert v["headline"] == "INDETERMINATE"


def test_a_strong_reference_that_the_app_matches_does_not_convict_the_engine():
    # Both decoders at 0.80: the audio is fine and so is the recognizer. The
    # gap clause is what stops R2 firing on a healthy run.
    v = verdict(full_run(**{
        "A/reference": cell(capture=0.85),
        "A/sf_ctx": cell(capture=0.80, name_rate=0.9, mentions=12),
    }))
    assert fired(v, "R2") is False
    assert v["headline"] == "INDETERMINATE"


def test_voice_processing_winning_by_fifteen_points_convicts_measurement_mode():
    v = verdict(full_run(**{
        "A/sf_ctx": cell(capture=0.32, name_rate=0.1, mentions=12),
        "B/sf_ctx": cell(capture=0.50, name_rate=0.3, mentions=12),
    }))
    assert fired(v, "R3") is True


def test_voice_processing_winning_by_a_little_does_not_convict_anything():
    v = verdict(full_run(**{
        "A/sf_ctx": cell(capture=0.32, name_rate=0.1, mentions=12),
        "B/sf_ctx": cell(capture=0.40, name_rate=0.2, mentions=12),
    }))
    assert fired(v, "R3") is False


def test_the_same_name_rate_with_and_without_the_vocabulary_calls_it_inert():
    """tejas_gate leg 7 is green because the string contextualStrings appears
    in PhoneListener.swift. Whether it does anything under
    requiresOnDeviceRecognition has no primary source either way. This is the
    leg that finds out."""
    v = verdict(full_run(**{
        "A/sf_ctx": cell(capture=0.32, name_rate=0.10, mentions=14),
        "A/sf_noctx": cell(capture=0.31, name_rate=0.08, mentions=14),
    }))
    assert fired(v, "R4") is True


def test_a_vocabulary_that_clearly_helps_is_not_called_inert():
    v = verdict(full_run(**{
        "A/sf_ctx": cell(capture=0.32, name_rate=0.70, mentions=14),
        "A/sf_noctx": cell(capture=0.31, name_rate=0.10, mentions=14),
    }))
    assert fired(v, "R4") is False


def test_too_few_name_mentions_cannot_answer_the_vocabulary_question():
    # Three mentions cannot express a ten-point difference. Reporting "inert"
    # off three mentions would be a coin flip wearing a verdict's clothes.
    v = verdict(full_run(**{
        "A/sf_ctx": cell(capture=0.32, name_rate=0.0, mentions=3),
        "A/sf_noctx": cell(capture=0.31, name_rate=0.0, mentions=3),
    }))
    assert fired(v, "R4") is None
    assert "mentions" in next(
        f for f in v["findings"] if f["rule"] == "R4")["because"]


def test_a_reference_decoder_that_fails_the_clean_control_voids_the_verdict():
    """The whole experiment reads a low reference score as "the audio is
    starved". That inference is only available if the reference decoder is
    known to score well on audio that is NOT starved. Without the control it
    is equally consistent with "the reference decoder is weak"."""
    v = verdict(full_run(**{"C/reference": cell(capture=0.55)}))
    assert fired(v, "R1") is None
    assert fired(v, "R2") is None
    assert v["headline"] == "CANNOT DECIDE"
    assert any("control" in b.lower() for b in v["blocked"])


def test_a_missing_control_blocks_the_engine_verdict_and_names_the_missing_cell():
    cells = full_run()
    del cells["C/reference"]
    v = verdict(cells)
    assert fired(v, "R1") is None
    assert v["headline"] == "CANNOT DECIDE"
    assert any("C/reference" in b for b in v["blocked"])


def test_an_unalignable_cell_blocks_the_rule_that_needs_it():
    v = verdict(full_run(**{
        "A/reference": cell(unalignable=True, reason="the transcript is empty"),
    }))
    assert fired(v, "R1") is None
    assert fired(v, "R2") is None
    assert any("A/reference" in b for b in v["blocked"])


def test_the_agc_question_survives_a_missing_reference_decoder():
    """Arm A against arm B on the same decoder needs no reference decoder at
    all. If the environment cannot run one, that arm of the experiment is still
    worth flying — and the harness must not withhold it."""
    cells = full_run()
    del cells["A/reference"]
    del cells["C/reference"]
    cells["B/sf_ctx"] = cell(capture=0.55, name_rate=0.4, mentions=12)
    v = verdict(cells)
    assert fired(v, "R3") is True
    assert fired(v, "R1") is None


# ---------------------------------------------------------------------------
# Reading a run off disk
# ---------------------------------------------------------------------------

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "proof", "fixtures", "read_aloud_script.txt")


def _thin(script_words, keep_per_ten):
    """A transcript that keeps `keep_per_ten` words out of every ten, spread the
    whole way down the page — the shape a starved microphone produces, as
    against a truncation, which is a different bug the harness must refuse."""
    return " ".join(w for i, w in enumerate(script_words) if i % 10 < keep_per_ten)


def _prov(arm, decoder, wav_sha):
    """The provenance line the scratch recorder's output contract requires. It
    is the only thing that can tell a toggle nobody wired from a setting that
    genuinely does nothing, and an arm swap from two honest recordings."""
    return f"#anticipy: arm={arm} decoder={decoder} wav=arm_{arm.lower()}.wav sha256={wav_sha}\n"


def _write_run(run, files):
    for rel, text in files.items():
        with open(os.path.join(run, rel), "w", encoding="utf-8") as fh:
            fh.write(text)


def test_the_shipped_script_says_every_vocabulary_word_enough_times_to_score():
    """A recording protocol that produces four mentions of the product name
    cannot answer the vocabulary question, and nobody finds that out until the
    afternoon is spent. The script is checked here instead."""
    with open(SCRIPT, encoding="utf-8") as fh:
        text = fh.read()
    s = score(text, text, VOCAB)
    assert s["ref_words"] >= 300, "enough words for a stable rate"
    assert s["names"]["Anticipy"]["mentions"] >= MIN_NAME_MENTIONS
    for term in VOCAB:
        assert s["names"][term]["mentions"] >= 4, term


def test_a_scaffolded_run_scores_as_entirely_refused_rather_than_crashing(tmp_path):
    # The state a run is in the moment it is created: every cell named, nothing
    # recorded. It must read as "nothing here yet", not as a traceback and not
    # as a verdict.
    run = str(tmp_path / "run")
    scaffold(run, SCRIPT)
    loaded = load_run(run)
    assert loaded["cells"], "the cells are named before they are filled"
    assert all(c["unalignable"] for c in loaded["cells"].values())
    v = verdict(loaded["cells"])
    assert v["headline"] == "CANNOT DECIDE"


def test_a_missing_transcript_names_the_path_it_wanted(tmp_path):
    run = str(tmp_path / "run")
    scaffold(run, SCRIPT)
    loaded = load_run(run)
    assert "sf_ctx.txt" in loaded["cells"]["A/sf_ctx"]["unalignable_reason"]


def test_a_half_finished_run_still_answers_the_question_it_can(tmp_path):
    """Arms A and B on the phone's own recognizer need no reference decoder.
    Someone who flies that half on a Tuesday should get R3 on the Tuesday, not
    a refusal to say anything until a Mac is free."""
    run = str(tmp_path / "run")
    scaffold(run, SCRIPT)
    with open(SCRIPT, encoding="utf-8") as fh:
        script = fh.read().split()
    starved = " ".join(w for i, w in enumerate(script) if i % 10 < 3)
    better = " ".join(w for i, w in enumerate(script) if i % 10 < 8)
    for rel, text in (("arm_a/sf_ctx.txt", starved), ("arm_b/sf_ctx.txt", better)):
        with open(os.path.join(run, rel), "w", encoding="utf-8") as fh:
            fh.write(text)

    v = verdict(load_run(run)["cells"])
    assert fired(v, "R3") is True
    assert fired(v, "R1") is None
    assert v["headline"] == "CANNOT DECIDE"


def test_an_unknown_decoder_in_a_manifest_is_rejected_not_ignored(tmp_path):
    """The sibling of the arm check, and it had no cover at all: turning it
    into `pass` left every test green. A typo'd decoder name silently scores a
    cell no rule reads, so R4 comes back None and the reader is told the
    vocabulary question is unanswered rather than misspelled."""
    import json
    run = str(tmp_path / "run")
    scaffold(run, SCRIPT)
    path = os.path.join(run, "manifest.json")
    with open(path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    manifest["cells"] = [{"arm": "A", "decoder": "sf_context", "transcript": "x.txt"}]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh)

    try:
        load_run(run)
    except ValueError as exc:
        assert "sf_context" in str(exc)
    else:  # pragma: no cover - the point of the test
        raise AssertionError("a typo'd decoder would silently score nothing")


def test_an_unknown_arm_in_a_manifest_is_rejected_not_ignored(tmp_path):
    import json
    run = str(tmp_path / "run")
    scaffold(run, SCRIPT)
    path = os.path.join(run, "manifest.json")
    with open(path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    manifest["cells"] = [{"arm": "Z", "decoder": "sf_ctx", "transcript": "x.txt"}]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh)

    try:
        load_run(run)
    except ValueError as exc:
        assert "Z" in str(exc)
    else:  # pragma: no cover - the point of the test
        raise AssertionError("a typo'd arm would silently score nothing")


# ---------------------------------------------------------------------------
# C2 — the transcript floor. One word defeated the empty-transcript refusal
# ---------------------------------------------------------------------------

def test_one_word_is_refused_for_the_reason_zero_words_is():
    """`if not hyp:` refused zero tokens and scored one. "you" and "Thank you."
    are whisper's canonical output on silence or a failed decode; "you" scored
    capture 0.0027 with a script share of 1.00 and fired R1 — AUDIO PATH AT
    FAULT off a dead file. The empty refusal's own rationale, that a dead
    recognizer and a wrong file look identical from here, is exactly as true at
    one word as at zero. The line was drawn at the single point where the
    confusion cannot occur, not where it stops."""
    ref = numbered(400)
    for canned in ("you", "Thank you.", "Thanks for watching!", "word1"):
        s = score(ref, canned, VOCAB)
        assert s["unalignable"] is True, canned
        assert s["capture_rate"] is None, canned
        assert s["wer"] is None, canned


def test_a_canned_phrase_repeated_still_has_no_sample_to_measure():
    """The version nobody tried. A decoder looping on silence emits the same
    short phrase over and over; each repeat lifts the transcript's word count
    without adding a single new observation. The share test underneath is a
    proportion over len(hyp), so eight repeats of one script word can read as
    62% script material."""
    ref = numbered(400)
    s = score(ref, " ".join(["word7"] * 8), VOCAB)
    assert s["unalignable"] is True
    assert s["capture_rate"] is None


def _spread(words, n):
    """`n` of these words, spread evenly across all of them — a starved
    microphone, not a truncation, so the span check is not what decides."""
    last = len(words) - 1
    return " ".join(words[round(i * last / (n - 1))] for i in range(n))


def test_the_transcript_floor_is_a_boundary_not_a_direction():
    # Either side of MIN_TRANSCRIPT_WORDS, so inverting the comparison fails.
    words = numbered(400).split()
    ref = " ".join(words)
    just_under = _spread(words, MIN_TRANSCRIPT_WORDS - 1)
    at_the_floor = _spread(words, MIN_TRANSCRIPT_WORDS)
    assert len(just_under.split()) == MIN_TRANSCRIPT_WORDS - 1
    assert len(at_the_floor.split()) == MIN_TRANSCRIPT_WORDS

    assert score(ref, just_under, VOCAB)["unalignable"] is True
    assert score(ref, at_the_floor, VOCAB)["unalignable"] is False, (
        "exactly at the floor is scored — the floor is a minimum, not a target")


def test_the_floor_still_leaves_the_whole_decision_range_measurable():
    """What the floor costs, checked rather than asserted. Against the shipped
    370-word script the harness gives up capture rates under about 0.054 — and
    every threshold the decision rule reads sits above 0.30, so nothing the
    experiment is for has been given away."""
    with open(SCRIPT, encoding="utf-8") as fh:
        script = fh.read().split()
    lost = MIN_TRANSCRIPT_WORDS / len(script)
    assert lost < STARVED_AUDIO_CEILING
    assert lost < ENGINE_FAULT_MIN_GAP
    assert lost < 0.10, "the region given up is far below anything the rule reads"


# ---------------------------------------------------------------------------
# C3 — a missing measurement is not a verdict
# ---------------------------------------------------------------------------

def test_a_missing_app_cell_that_decides_the_verdict_cannot_decide_it():
    """The reviewer's C3, and it is verbatim the sin verdict()'s own docstring
    names. Control credible, A/reference at 0.82 — above the 0.75 floor — and
    A/sf_ctx absent. R2 is None, and the headline chain used to fall through
    to:

        VERDICT: INDETERMINATE — the reference decoder landed between the two
        pre-registered thresholds

    which is factually false about a 0.82, with decidable True and exit 0. A
    missing measurement printed as a decided verdict, with an invented
    reason."""
    cells = full_run(**{"A/reference": cell(capture=0.82)})
    del cells["A/sf_ctx"]
    v = verdict(cells)
    assert fired(v, "R2") is None
    assert v["headline"] == "CANNOT DECIDE"
    assert v["decidable"] is False
    assert "between the two pre-registered thresholds" not in HEADLINE_MEANING[v["headline"]]


def test_a_missing_app_cell_that_cannot_change_the_verdict_does_not_block_it():
    """The other direction, and the reason the fix is not just `or`. With the
    reference decoder at 0.40 the first clause of R2 has already failed on a
    cell that IS present, so no value the missing one could take would fire R2.
    Reporting None there would withhold a sound conclusion — and this harness's
    whole design is that it must answer what it can."""
    cells = full_run(**{"A/reference": cell(capture=0.40)})
    del cells["A/sf_ctx"]
    v = verdict(cells)
    assert fired(v, "R1") is True
    assert fired(v, "R2") is False, "determinately false, not unknown"
    assert v["headline"] == "AUDIO PATH AT FAULT"
    assert v["decidable"] is True


def test_the_exit_code_contract_is_what_the_docstring_says_it_is(tmp_path, capsys):
    """`decidable` and `return 0` were both hardcodeable with every test green,
    so the documented exit-code contract was untested — and C3's symptom was
    exit 0 on a run that could not be read."""
    run = str(tmp_path / "run")
    scaffold(run, SCRIPT)
    assert main(["--run", run]) == 1, "a run with nothing in it is not decidable"
    capsys.readouterr()

    with open(SCRIPT, encoding="utf-8") as fh:
        script = fh.read().split()
    _write_run(run, {
        "arm_c/reference.txt": " ".join(script),
        "arm_a/reference.txt": _thin(script, 9),
        "arm_a/sf_ctx.txt": _thin(script, 3),
        "arm_a/sf_noctx.txt": _thin(script, 4),
        "arm_b/sf_ctx.txt": _thin(script, 8),
    })
    assert main(["--run", run]) == 0, (
        "ENGINE AT FAULT exits 0: a measurement is not a gate, and a harness "
        "that exits red on a finding teaches people to stop running it")
    out = capsys.readouterr().out
    assert "ENGINE AT FAULT" in out


# ---------------------------------------------------------------------------
# C4 — R4 had no positive control, and no proof of two recordings
# ---------------------------------------------------------------------------

def test_an_arm_that_heard_no_names_at_all_cannot_call_the_vocabulary_inert():
    """C4(a). The mention counts come from the REFERENCE, so both arms always
    carry the same number — they measure the script, not the data. Nothing
    required either decoder to have heard a single name, so a starved arm at
    0/26 on both sides is a delta of exactly 0.00: the strongest possible
    "inert" verdict, manufactured by the very outcome the experiment expects,
    firing alongside R1 saying the audio was starved."""
    v = verdict(full_run(**{
        "A/reference": cell(capture=0.40),
        "A/sf_ctx": cell(capture=0.08, name_rate=0.0, mentions=26, hits=0),
        "A/sf_noctx": cell(capture=0.07, name_rate=0.0, mentions=26, hits=0),
    }))
    assert fired(v, "R1") is True, "the arm really is starved"
    assert fired(v, "R4") is None, "and that is not evidence about the vocabulary"
    because = next(f for f in v["findings"] if f["rule"] == "R4")["because"]
    assert "heard" in because


def test_one_name_heard_on_either_side_is_enough_to_ask_the_question():
    # The boundary. MIN_NAME_HITS_EITHER_SIDE on one side only, and R4 speaks.
    v = verdict(full_run(**{
        "A/sf_ctx": cell(capture=0.32, name_rate=1 / 26, mentions=26,
                         hits=MIN_NAME_HITS_EITHER_SIDE),
        "A/sf_noctx": cell(capture=0.31, name_rate=0.0, mentions=26, hits=0),
    }))
    assert fired(v, "R4") is True


def test_two_cells_that_are_one_file_cannot_be_subtracted(tmp_path):
    """C4(b). The scratch recorder's contextualStrings toggle is never wired,
    so arm_a/sf_ctx.txt and arm_a/sf_noctx.txt are the same bytes. Delta
    exactly +0.00 and R4 fires: "contextualStrings does nothing under
    requiresOnDeviceRecognition." The strongest possible signal for that rule
    is also the signature of the harness never having run the experiment."""
    run = str(tmp_path / "run")
    scaffold(run, SCRIPT)
    with open(SCRIPT, encoding="utf-8") as fh:
        script = fh.read().split()
    same = _thin(script, 3)
    _write_run(run, {
        "arm_c/reference.txt": " ".join(script),
        "arm_a/reference.txt": _thin(script, 9),
        "arm_a/sf_ctx.txt": same,
        "arm_a/sf_noctx.txt": same,
        "arm_b/sf_ctx.txt": _thin(script, 8),
    })
    v = verdict(load_run(run)["cells"])
    assert fired(v, "R4") is None
    because = next(f for f in v["findings"] if f["rule"] == "R4")["because"]
    assert "byte-identical" in because


def test_a_provenance_line_lets_a_genuinely_inert_setting_still_be_reported(tmp_path):
    """The other half, and the reason the check is provenance and not a byte
    comparison. A biasing setting that truly does nothing, on a deterministic
    decoder over one WAV, produces exactly the same bytes as a toggle nobody
    wired. Only the recorder saying what it did separates them — and the
    recorder does not exist yet, so its contract can still require it."""
    run = str(tmp_path / "run")
    scaffold(run, SCRIPT)
    with open(SCRIPT, encoding="utf-8") as fh:
        script = fh.read().split()
    same = _thin(script, 3)
    wav_a = "a" * 64
    _write_run(run, {
        "arm_c/reference.txt": _prov("C", "reference", "c" * 64) + " ".join(script),
        "arm_a/reference.txt": _prov("A", "reference", wav_a) + _thin(script, 9),
        "arm_a/sf_ctx.txt": _prov("A", "sf_ctx", wav_a) + same,
        "arm_a/sf_noctx.txt": _prov("A", "sf_noctx", wav_a) + same,
        "arm_b/sf_ctx.txt": _prov("B", "sf_ctx", "b" * 64) + _thin(script, 8),
    })
    v = verdict(load_run(run)["cells"])
    assert fired(v, "R4") is True, (
        "with two decodes of one WAV on record, identical output IS the finding")


def test_the_provenance_line_is_not_scored_as_words_the_decoder_invented(tmp_path):
    # `sha256=<64 hex>` tokenises into a word. A header left in the text would
    # be charged to the decoder as a hallucination — the harness billing the
    # recorder for its own bookkeeping.
    run = str(tmp_path / "run")
    scaffold(run, SCRIPT)
    with open(SCRIPT, encoding="utf-8") as fh:
        script = fh.read().split()
    _write_run(run, {"arm_c/reference.txt": _prov("C", "reference", "c" * 64) + " ".join(script)})
    c = load_run(run)["cells"]["C/reference"]
    assert c["capture_rate"] == 1.0
    assert c["inserted"] == 0
    assert c["hyp_words"] == len(script)


def test_an_arm_swap_is_caught_by_the_line_the_recorder_writes(tmp_path):
    """The report conceded this one as undetectable, and it was: arm A and arm
    B are two recordings of the same page, and no arithmetic separates them.
    What separates them is the recorder saying which one it wrote. Swapping
    them reverses R3, the rule with a one-line fix behind it."""
    run = str(tmp_path / "run")
    scaffold(run, SCRIPT)
    with open(SCRIPT, encoding="utf-8") as fh:
        script = fh.read().split()
    _write_run(run, {
        "arm_c/reference.txt": " ".join(script),
        "arm_a/sf_ctx.txt": _prov("A", "sf_ctx", "a" * 64) + _thin(script, 3),
        # arm A's transcript, filed under arm B.
        "arm_b/sf_ctx.txt": _prov("A", "sf_ctx", "a" * 64) + _thin(script, 8),
    })
    cells = load_run(run)["cells"]
    assert cells["B/sf_ctx"]["unalignable"] is True
    assert cells["B/sf_ctx"]["capture_rate"] is None
    assert "arm A" in cells["B/sf_ctx"]["unalignable_reason"]
    assert fired(verdict(cells), "R3") is None


def test_one_recording_filed_as_two_arms_is_caught_by_its_hash(tmp_path):
    """The version the byte comparison misses. Two decodes of the SAME WAV,
    filed as arm A and arm B, produce different text if the decoders differ —
    but the arms are supposed to differ by an audio-session setting, so one
    recording filed twice is a delta manufactured by the filing."""
    run = str(tmp_path / "run")
    scaffold(run, SCRIPT)
    with open(SCRIPT, encoding="utf-8") as fh:
        script = fh.read().split()
    one_wav = "a" * 64
    _write_run(run, {
        "arm_c/reference.txt": " ".join(script),
        "arm_a/sf_ctx.txt": _prov("A", "sf_ctx", one_wav) + _thin(script, 3),
        "arm_b/sf_ctx.txt": _prov("B", "sf_ctx", one_wav) + _thin(script, 8),
    })
    v = verdict(load_run(run)["cells"])
    assert fired(v, "R3") is None
    because = next(f for f in v["findings"] if f["rule"] == "R3")["because"]
    assert "SAME source recording" in because


# ---------------------------------------------------------------------------
# I7 — the validity gate: what the control proved, and how many tries it took
# ---------------------------------------------------------------------------

def test_a_short_control_does_not_calibrate_a_decoder_for_a_long_script():
    """I7(a). A cell may name its own reference_script, and nothing required
    the control's to resemble arm A's. A twenty-word passage read perfectly
    cleared the 0.85 floor and opened R1 and R2 for a 370-word arm A —
    headline AUDIO PATH AT FAULT off a control that proved the decoder can
    manage one sentence."""
    v = verdict(full_run(**{
        "C/reference": cell(capture=1.0, ref_words=20),
        "A/reference": cell(capture=0.40, ref_words=370),
    }))
    assert fired(v, "R1") is None
    assert fired(v, "R2") is None
    assert v["headline"] == "CANNOT DECIDE"
    assert any("control was scored against" in b for b in v["blocked"])


def test_the_control_script_ratio_is_a_boundary_not_a_direction():
    at_the_floor = int(MIN_CONTROL_SCRIPT_RATIO * 370)
    ok = verdict(full_run(**{
        "C/reference": cell(capture=0.95, ref_words=at_the_floor),
        "A/reference": cell(capture=0.40, ref_words=370),
    }))
    short = verdict(full_run(**{
        "C/reference": cell(capture=0.95, ref_words=at_the_floor - 1),
        "A/reference": cell(capture=0.40, ref_words=370),
    }))
    assert fired(ok, "R1") is True
    assert fired(short, "R1") is None


def test_a_control_re_recorded_until_it_cleared_is_a_maximum_not_a_measurement():
    """I7(b). RECORDING-PROTOCOL.md told the operator in writing to re-record
    arm C until it cleared, and nothing recorded how many attempts it took. A
    pass/fail on decoder credibility that may be retried without limit or
    record is a maximum over attempts."""
    v = verdict(full_run(**{
        "C/reference": cell(capture=0.86, attempts=MAX_RECORDING_ATTEMPTS + 1),
    }))
    assert fired(v, "R1") is None
    assert v["headline"] == "CANNOT DECIDE"
    assert any("recorded" in b and "attempts" in b for b in v["blocked"])


def test_the_same_hazard_pointed_at_the_conclusion_is_caught_too():
    # Re-recording arm A until the numbers look like the expected finding is
    # the same act aimed the other way. The rule is about selection, not about
    # the control.
    v = verdict(full_run(**{
        "A/sf_ctx": cell(capture=0.05, name_rate=0.1, mentions=12,
                         attempts=MAX_RECORDING_ATTEMPTS + 1),
    }))
    assert fired(v, "R3") is None
    assert fired(v, "R4") is None


def test_an_unrecorded_attempt_count_is_not_assumed_to_be_one():
    # "Nobody wrote it down" and "the ninth try" are the same evidence here.
    v = verdict(full_run(**{"C/reference": cell(capture=0.95, attempts=None)}))
    assert fired(v, "R1") is None
    assert any("how many times" in b for b in v["blocked"])


def test_the_attempt_ceiling_is_a_boundary_not_a_direction():
    at_ceiling = verdict(full_run(**{
        "C/reference": cell(capture=0.95, attempts=MAX_RECORDING_ATTEMPTS)}))
    over = verdict(full_run(**{
        "C/reference": cell(capture=0.95, attempts=MAX_RECORDING_ATTEMPTS + 1)}))
    assert fired(at_ceiling, "R1") is True, "one honest retake is allowed"
    assert fired(over, "R1") is None


def test_the_scaffold_writes_the_attempt_count_it_requires(tmp_path):
    # A required field the tool does not lay out is a field nobody fills in.
    import json
    run = str(tmp_path / "run")
    scaffold(run, SCRIPT)
    with open(os.path.join(run, "manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    assert manifest["attempts"] == {"A": 1, "B": 1, "C": 1}


# ---------------------------------------------------------------------------
# I5 — the printed rule and the printed conclusion, pinned to the code
# ---------------------------------------------------------------------------

def test_the_printed_rule_quotes_the_numbers_the_code_enforces():
    """explain() was made to advertise a control floor of 0.60 while the code
    enforced 0.85, and 57 of 57 tests stayed green. Pre-registration is a
    promise about a document the operator reads, and the document was free to
    disagree with the code.

    Not a list of expected strings, which would drift with them: the set of
    numbers PRINTED must be exactly the set of numbers the rule BRANCHES on.
    Hardcoding any value adds a number that is no constant; dropping a
    threshold from the document removes one that is."""
    import re
    # Section references ("§8", "§11") and the dated filename of the research
    # doc are citations, not thresholds. Stripped so a genuine integer
    # threshold cannot be quietly dropped from the document and still "appear"
    # because some unrelated prose happens to contain the same digit — which is
    # exactly how the first version of this test let MIN_NAME_MENTIONS through.
    document = re.sub(r"§[\d.]+|\d{4}-\d\d-\d\d|\bR\d\b|\biOS \d+", " ", explain())
    enforced = [
        STARVED_AUDIO_CEILING, ENGINE_FAULT_REFERENCE_FLOOR, ENGINE_FAULT_MIN_GAP,
        AGC_WIN_MARGIN, CONTEXTUAL_STRINGS_INERT_BAND, MIN_NAME_MENTIONS,
        MIN_NAME_HITS_EITHER_SIDE, CONTROL_CREDIBILITY_FLOOR,
        MIN_CONTROL_SCRIPT_RATIO, MAX_RECORDING_ATTEMPTS,
        MIN_REFERENCE_WORDS, MIN_TRANSCRIPT_WORDS,
        MIN_SCRIPT_SHARE, ANCHOR_EXEMPT_CAPTURE, MAX_INSERTION_RATE,
        MIN_REFERENCE_SPAN,
    ]
    # Every number the code branches on is in the document the operator reads.
    # Hardcoding one — the reviewer replaced an interpolated 0.85 with a
    # literal 0.60 — takes the real value out of the text, and this leg goes
    # red on it.
    # Counted, not merely present. MIN_REFERENCE_WORDS and MIN_TRANSCRIPT_WORDS
    # are both 20 by design and for the same reason, so "does 20 appear?" is
    # satisfied by either of them alone — dropping one from the document
    # survived until this was a count. Mutation testing again.
    from collections import Counter
    wanted = Counter(str(v) for v in enforced)
    printed_counts = Counter(re.findall(r"(?<![\d.])\d+(?:\.\d+)?(?!\d)", document))
    for value, needed in wanted.items():
        assert printed_counts[value] >= needed, (
            f"{value} is enforced by {needed} rule(s) and printed "
            f"{printed_counts[value]} time(s)")

    # And nothing else. Every decimal in the document has to BE one of them, so
    # a hardcoded 0.60 beside a 0.85 the code enforces is caught from the other
    # direction too. Integers are exempt from this leg only because the
    # document cites research/2026-08-24-engine-options.md and iOS 26 by name.
    printed = {float(m) for m in re.findall(r"(?<![\d.])\d+\.\d+", document)}  # noqa: E501
    assert printed <= {float(v) for v in enforced}, (
        f"printed but enforced nowhere: "
        f"{sorted(printed - {float(v) for v in enforced})}")


def test_what_each_verdict_licenses_is_pinned_like_the_thresholds_are():
    """HEADLINE_MEANING is prose, and prose was pinned by nothing: reversing
    AUDIO PATH AT FAULT to read "the engine could not decode it. Migrate."
    left 57 of 57 green. This is the one bit that costs weeks, held as a
    boolean where a test can reach it — and render() prints the operator's
    instruction from the boolean, not from the sentence."""
    assert HEADLINE_LICENSES_MIGRATION["AUDIO PATH AT FAULT"] is False
    assert HEADLINE_LICENSES_MIGRATION["ENGINE AT FAULT"] is True
    assert HEADLINE_LICENSES_MIGRATION["INDETERMINATE"] is None
    assert HEADLINE_LICENSES_MIGRATION["CANNOT DECIDE"] is None


def test_the_verdict_sentences_are_pinned_because_reversing_one_costs_weeks():
    """Pinned literally, for the same reason the nine thresholds are: moving
    one has to be an edit to a test with a name that asks why. Migrating an
    engine that was never at fault and exonerating one that is are both weeks,
    and a reversed sentence is how either happens quietly."""
    assert HEADLINE_MEANING["AUDIO PATH AT FAULT"] == (
        "a strong decoder loses the same words off the same file. Fix the front "
        "end; do not migrate the engine.")
    assert HEADLINE_MEANING["ENGINE AT FAULT"] == (
        "the audio was decodable and the app's recognizer did not decode it. "
        "The §8 migration is justified on evidence.")


def test_the_printed_instruction_follows_the_rule_that_actually_fired(tmp_path):
    """The structural half: whatever the prose says, the line the operator acts
    on is generated from the rule that fired. Driven off two real runs on disk
    rather than off the maps, so the test cannot agree with a reversal by
    reading the same dict the code reversed."""
    with open(SCRIPT, encoding="utf-8") as fh:
        script = fh.read().split()

    starved = str(tmp_path / "starved")
    scaffold(starved, SCRIPT)
    _write_run(starved, {
        "arm_c/reference.txt": " ".join(script),
        "arm_a/reference.txt": _thin(script, 4),      # 0.40 — R1 territory
        "arm_a/sf_ctx.txt": _thin(script, 3),
    })
    printed = render(load_run(starved))
    assert "AUDIO PATH AT FAULT" in printed
    assert "is NOT licensed" in printed

    convicted = str(tmp_path / "convicted")
    scaffold(convicted, SCRIPT)
    _write_run(convicted, {
        "arm_c/reference.txt": " ".join(script),
        "arm_a/reference.txt": _thin(script, 9),      # 0.90 against 0.30
        "arm_a/sf_ctx.txt": _thin(script, 3),
    })
    printed = render(load_run(convicted))
    assert "ENGINE AT FAULT" in printed
    assert "IS licensed" in printed


def test_every_threshold_comparison_is_pinned_at_its_own_boundary():
    """Eight comparisons survived inversion with every test green. Each pair
    here sits either side of one of them, so `>=` cannot become `>` and `<`
    cannot become `<=` without a red test."""
    # The control credibility floor, :501
    assert fired(verdict(full_run(**{
        "C/reference": cell(capture=CONTROL_CREDIBILITY_FLOOR)})), "R1") is not None
    assert fired(verdict(full_run(**{
        "C/reference": cell(capture=CONTROL_CREDIBILITY_FLOOR - 0.01)})), "R1") is None

    # R1's starved ceiling, :524
    assert fired(verdict(full_run(**{
        "A/reference": cell(capture=STARVED_AUDIO_CEILING)})), "R1") is True
    assert fired(verdict(full_run(**{
        "A/reference": cell(capture=STARVED_AUDIO_CEILING + 0.01)})), "R1") is False

    # R2's reference floor and its gap clause, :540 x2
    at_floor = full_run(**{
        "A/reference": cell(capture=ENGINE_FAULT_REFERENCE_FLOOR),
        "A/sf_ctx": cell(capture=ENGINE_FAULT_REFERENCE_FLOOR - ENGINE_FAULT_MIN_GAP,
                         name_rate=0.1, mentions=12)})
    assert fired(verdict(at_floor), "R2") is True
    assert fired(verdict(full_run(**{
        "A/reference": cell(capture=ENGINE_FAULT_REFERENCE_FLOOR - 0.01),
        "A/sf_ctx": cell(capture=0.10, name_rate=0.1, mentions=12)})), "R2") is False
    assert fired(verdict(full_run(**{
        "A/reference": cell(capture=0.80),
        "A/sf_ctx": cell(capture=0.80 - ENGINE_FAULT_MIN_GAP + 0.01,
                         name_rate=0.1, mentions=12)})), "R2") is False

    # R3's margin, :565. The delta has to land EXACTLY on the constant or
    # `>=` and `>` are indistinguishable — 0.45 - 0.30 is 0.15000000000000002
    # in binary floating point, which clears both and pins neither. Mutation
    # testing is what surfaced that: inverting this comparison stayed green.
    assert AGC_WIN_MARGIN - 0.0 == AGC_WIN_MARGIN
    assert fired(verdict(full_run(**{
        "A/sf_ctx": cell(capture=0.0, name_rate=0.1, mentions=12),
        "B/sf_ctx": cell(capture=AGC_WIN_MARGIN, name_rate=0.2, mentions=12),
    })), "R3") is True, "exactly the margin wins — the rule says >=, not >"
    assert fired(verdict(full_run(**{
        "A/sf_ctx": cell(capture=0.30, name_rate=0.1, mentions=12),
        "B/sf_ctx": cell(capture=0.44, name_rate=0.2, mentions=12),
    })), "R3") is False

    # R4's band, :593 — exactly at the band is NOT inert. Landing exactly on
    # the constant for the same reason: `<` and `<=` are the same test
    # anywhere else, and inverting this one stayed green until it was pinned
    # here.
    assert fired(verdict(full_run(**{
        "A/sf_ctx": cell(capture=0.32, name_rate=CONTEXTUAL_STRINGS_INERT_BAND,
                         mentions=12, hits=1),
        "A/sf_noctx": cell(capture=0.31, name_rate=0.0, mentions=12, hits=0),
    })), "R4") is False, "exactly the band is not inert — the rule says <, not <="
    assert fired(verdict(full_run(**{
        "A/sf_ctx": cell(capture=0.32, name_rate=0.40, mentions=12),
        "A/sf_noctx": cell(capture=0.31, name_rate=0.31, mentions=12),
    })), "R4") is True

    # R4's mention floor, and the exact count is enough
    assert fired(verdict(full_run(**{
        "A/sf_ctx": cell(capture=0.32, name_rate=0.5, mentions=MIN_NAME_MENTIONS),
        "A/sf_noctx": cell(capture=0.31, name_rate=0.5, mentions=MIN_NAME_MENTIONS),
    })), "R4") is True
    assert fired(verdict(full_run(**{
        "A/sf_ctx": cell(capture=0.32, name_rate=0.5, mentions=MIN_NAME_MENTIONS - 1),
        "A/sf_noctx": cell(capture=0.31, name_rate=0.5, mentions=MIN_NAME_MENTIONS - 1),
    })), "R4") is None


def test_the_script_share_floor_and_its_exemption_are_boundaries():
    """:452 x2 — both comparisons in the one refusal, either side."""
    # Exactly at MIN_SCRIPT_SHARE is scored; a hair under is refused.
    ref_words = [f"word{i}" for i in range(200)]
    survivors = [ref_words[i] for i in range(0, 200, 2)]  # 100 words, spread
    at_floor = survivors + [f"junk{i}" for i in range(100)]  # share exactly 0.50
    under = survivors + [f"junk{i}" for i in range(101)]

    s_at = score(" ".join(ref_words), " ".join(at_floor), VOCAB)
    s_under = score(" ".join(ref_words), " ".join(under), VOCAB)
    assert s_at["script_share"] == MIN_SCRIPT_SHARE
    assert s_at["unalignable"] is False
    assert s_under["unalignable"] is True
    assert "script material" in s_under["unalignable_reason"]

    # And the anchor exemption: capture at ANCHOR_EXEMPT_CAPTURE survives a
    # share under the floor; a hair below it does not.
    def noisy(n_kept):
        kept = _spread(ref_words, n_kept).split()
        # More junk than survivors, so the share is under MIN_SCRIPT_SHARE and
        # only the exemption can let this through.
        return " ".join(kept + [f"junk{i}" for i in range(n_kept + 20)])

    at_exemption = int(ANCHOR_EXEMPT_CAPTURE * 200)
    exempt = score(" ".join(ref_words), noisy(at_exemption), VOCAB)
    below = score(" ".join(ref_words), noisy(at_exemption - 1), VOCAB)
    assert exempt["script_share"] < MIN_SCRIPT_SHARE, "the exemption is what is on trial"
    assert exempt["capture_rate"] == ANCHOR_EXEMPT_CAPTURE
    assert exempt["unalignable"] is False, (
        "a high capture rate is its own evidence that this is the right pair")
    assert below["unalignable"] is True


def test_the_insertion_ceiling_is_pinned_at_exactly_the_ceiling():
    # :443. Doubling every word is insertion rate exactly 1.00 and is SCORED —
    # capture 1.00, WER 1.00 and insertion 1.00 printed side by side is the
    # designed mitigation for a stuttering decoder. Tripling is refused.
    ref = numbered(30)
    doubled = " ".join(f"word{i} word{i}" for i in range(1, 31))
    tripled = " ".join(f"word{i} word{i} word{i}" for i in range(1, 31))
    assert score(ref, doubled, VOCAB)["insertion_rate"] == MAX_INSERTION_RATE
    assert score(ref, doubled, VOCAB)["unalignable"] is False
    assert score(ref, tripled, VOCAB)["unalignable"] is True


# ---------------------------------------------------------------------------
# M12 — refusals that used to escape as tracebacks
# ---------------------------------------------------------------------------

def test_an_absurdly_large_transcript_is_refused_not_raised(tmp_path):
    """align() refuses a mis-supplied book rather than swapping the machine,
    and that refusal escaped load_run as a traceback because only
    FileNotFoundError was caught. A refusal that crashes the harness is a
    refusal nobody reads."""
    run = str(tmp_path / "run")
    scaffold(run, SCRIPT)
    _write_run(run, {"arm_c/reference.txt": " ".join(["word"] * 200_000)})
    c = load_run(run)["cells"]["C/reference"]
    assert c["unalignable"] is True
    assert "wrong pair of files" in c["unalignable_reason"]



def test_the_reference_and_the_app_cell_must_also_be_two_decodes(tmp_path):
    """R2 subtracts the app's capture from the reference's, and the same
    question applies: a reference decode copied into the app's path — or the
    app's transcript pointed at by both cells — is a gap of exactly zero, or a
    perfect agreement, manufactured by the filing rather than measured."""
    run = str(tmp_path / "run")
    scaffold(run, SCRIPT)
    with open(SCRIPT, encoding="utf-8") as fh:
        script = fh.read().split()
    same = _thin(script, 9)
    _write_run(run, {
        "arm_c/reference.txt": " ".join(script),
        "arm_a/reference.txt": same,
        "arm_a/sf_ctx.txt": same,
    })
    v = verdict(load_run(run)["cells"])
    assert fired(v, "R2") is None
    assert "byte-identical" in next(
        f for f in v["findings"] if f["rule"] == "R2")["because"]


def test_a_transcript_filed_under_the_wrong_decoder_is_caught_too(tmp_path):
    """The sibling of the arm swap. sf_ctx and sf_noctx are the two cells R4
    subtracts, so filing one as the other reverses the vocabulary finding — and
    the two are decodes of one WAV, so nothing in the text separates them."""
    run = str(tmp_path / "run")
    scaffold(run, SCRIPT)
    with open(SCRIPT, encoding="utf-8") as fh:
        script = fh.read().split()
    wav = "a" * 64
    _write_run(run, {
        "arm_c/reference.txt": " ".join(script),
        "arm_a/sf_ctx.txt": _prov("A", "sf_ctx", wav) + _thin(script, 3),
        # the WITHOUT-vocabulary decode, filed as the WITH-vocabulary one
        "arm_a/sf_noctx.txt": _prov("A", "sf_ctx", wav) + _thin(script, 4),
    })
    cells = load_run(run)["cells"]
    assert cells["A/sf_noctx"]["unalignable"] is True
    assert "sf_ctx" in cells["A/sf_noctx"]["unalignable_reason"]
    assert fired(verdict(cells), "R4") is None


def test_two_cells_of_one_arm_scored_from_different_recordings_are_refused(tmp_path):
    """The other direction of the same question, and the one nobody tried.
    A/sf_ctx and A/sf_noctx are supposed to be two DECODES OF ONE WAV — the
    only thing differing is the vocabulary flag. If they name different source
    recordings, the delta measures the recordings and R4 reports it as the
    vocabulary."""
    run = str(tmp_path / "run")
    scaffold(run, SCRIPT)
    with open(SCRIPT, encoding="utf-8") as fh:
        script = fh.read().split()
    _write_run(run, {
        "arm_c/reference.txt": " ".join(script),
        "arm_a/sf_ctx.txt": _prov("A", "sf_ctx", "a" * 64) + _thin(script, 3),
        "arm_a/sf_noctx.txt": _prov("A", "sf_noctx", "d" * 64) + _thin(script, 4),
    })
    v = verdict(load_run(run)["cells"])
    assert fired(v, "R4") is None
    assert "different source recordings" in next(
        f for f in v["findings"] if f["rule"] == "R4")["because"]


def test_the_manifests_attempt_count_reaches_the_rule_that_reads_it(tmp_path):
    """End to end rather than by unit: the number the operator writes in the
    manifest has to arrive at the validity gate. Stamping a constant 1 in
    load_run left every rule test green, because they all build their cells by
    hand."""
    import json
    run = str(tmp_path / "run")
    scaffold(run, SCRIPT)
    with open(SCRIPT, encoding="utf-8") as fh:
        script = fh.read().split()
    _write_run(run, {
        "arm_c/reference.txt": " ".join(script),
        "arm_a/reference.txt": _thin(script, 4),
        "arm_a/sf_ctx.txt": _thin(script, 3),
    })
    assert verdict(load_run(run)["cells"])["headline"] == "AUDIO PATH AT FAULT"

    path = os.path.join(run, "manifest.json")
    with open(path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    manifest["attempts"]["C"] = MAX_RECORDING_ATTEMPTS + 1
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh)

    v = verdict(load_run(run)["cells"])
    assert v["headline"] == "CANNOT DECIDE"
    assert any("recorded" in b and "attempts" in b for b in v["blocked"])


def test_the_scaffold_lays_out_only_cells_a_rule_actually_reads(tmp_path):
    """I9. --scaffold used to write nine cells — every arm crossed with every
    decoder — while the protocol listed five files, two of the nine being
    `speech_transcriber` cells the protocol never mentioned. Following the
    protocol exactly produced a report with four REFUSED lines that were
    NORMAL. Every refusal this harness prints is one it needs a human to
    notice; four false ones a run is how the true one gets skimmed past."""
    run = str(tmp_path / "run")
    scaffold(run, SCRIPT)
    cells = load_run(run)["cells"]
    assert set(cells) == {
        "C/reference", "A/reference", "A/sf_ctx", "A/sf_noctx", "B/sf_ctx"}

    # And every one of them is read by a rule: filling all five leaves no
    # REFUSED line behind, so a REFUSED line always means something.
    with open(SCRIPT, encoding="utf-8") as fh:
        script = fh.read().split()
    _write_run(run, {
        "arm_c/reference.txt": " ".join(script),
        "arm_a/reference.txt": _thin(script, 9),
        "arm_a/sf_ctx.txt": _thin(script, 3),
        "arm_a/sf_noctx.txt": _thin(script, 4),
        "arm_b/sf_ctx.txt": _thin(script, 8),
    })
    printed = render(load_run(run))
    assert "REFUSED" not in printed, (
        "a complete run must print no refusals at all, or REFUSED stops "
        "carrying information")
    assert all(f["fired"] is not None for f in verdict(load_run(run)["cells"])["findings"])


# ---------------------------------------------------------------------------
# The half of the provenance contract that exists today
# ---------------------------------------------------------------------------

def test_the_reference_decoder_writes_the_provenance_line_the_scorer_reads():
    """The scratch recorder that has to stamp the on-device cells does not
    exist yet — that is why its output contract could still be made to require
    this. proof/reference_decode.py DOES exist, so it honours the contract
    today, and the two files share one PROVENANCE_PREFIX rather than two
    definitions that can drift apart."""
    from proof import reference_decode
    from proof.engine_or_audio import (PROVENANCE_PREFIX, parse_provenance,
                                       strip_provenance)
    assert reference_decode.PROVENANCE_PREFIX is PROVENANCE_PREFIX

    wav = os.path.join(os.path.dirname(SCRIPT), "..", "e2e_audio.wav")
    line = reference_decode.provenance_line(os.path.abspath(wav), "A")
    parsed = parse_provenance(line + "some words")
    assert parsed["arm"] == "A"
    assert parsed["decoder"] == "reference"
    assert len(parsed["sha256"]) == 64
    assert parsed["sha256"] == reference_decode.wav_digest(os.path.abspath(wav))
    assert strip_provenance(line + "some words") == "some words"


def test_the_arm_is_read_off_the_path_and_never_guessed():
    """A provenance line that itself lies is worse than none: the scorer trusts
    it to catch a swap. An unrecognised output path therefore gets no line
    rather than a guessed one."""
    from proof.reference_decode import arm_of
    assert arm_of("/runs/2026-08-24/arm_a/reference.txt") == "A"
    assert arm_of("/runs/2026-08-24/arm_c/reference.txt") == "C"
    assert arm_of("/somewhere/else/out.txt") == ""
    assert arm_of("/runs/arm_alpha/reference.txt") == ""


def test_decode_stamps_the_line_onto_the_file_it_writes(tmp_path, monkeypatch):
    """The plumbing, not just the helper. whisper is not run here — the
    decoder subprocess is stubbed and the file it would have produced is
    written by hand, because what is on trial is whether decode() puts the
    provenance line on the transcript, not whether whisper works. A helper that
    formats a line nothing calls is the shape of a check that does not run."""
    from proof import reference_decode
    from proof.engine_or_audio import parse_provenance

    wav = tmp_path / "arm_a.wav"
    wav.write_bytes(b"RIFF....WAVEfmt not really audio")
    out_dir = tmp_path / "arm_a"
    out_dir.mkdir()
    out_path = str(out_dir / "reference.txt")

    monkeypatch.setattr(reference_decode, "availability",
                        lambda *a, **k: {"available": True, "interpreter": "python3",
                                         "model": "base", "cached": ["base"],
                                         "caveat": "", "why_not": ""})

    class _Probe:
        returncode = 0

    def fake_run(cmd, **kwargs):
        if "-m" not in cmd:          # the `import whisper` probe
            return _Probe()
        # whisper names its output after the WAV, which is why decode() renames.
        with open(out_dir / "arm_a.txt", "w", encoding="utf-8") as fh:
            fh.write("the words the decoder heard")
        return _Probe()

    monkeypatch.setattr(reference_decode.subprocess, "run", fake_run)

    text = reference_decode.decode(str(wav), out_path)
    assert text == "the words the decoder heard", (
        "decode returns the transcript, not the bookkeeping")
    with open(out_path, encoding="utf-8") as fh:
        on_disk = fh.read()
    parsed = parse_provenance(on_disk)
    assert parsed is not None, "the file the scorer reads carries the line"
    assert parsed["arm"] == "A"
    assert parsed["sha256"] == reference_decode.wav_digest(str(wav))
