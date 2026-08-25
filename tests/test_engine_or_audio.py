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
    CONTEXTUAL_STRINGS_INERT_BAND,
    CONTROL_CREDIBILITY_FLOOR,
    ENGINE_FAULT_MIN_GAP,
    ENGINE_FAULT_REFERENCE_FLOOR,
    MIN_NAME_MENTIONS,
    MIN_REFERENCE_WORDS,
    MAX_INSERTION_RATE,
    MIN_SCRIPT_SHARE,
    STARVED_AUDIO_CEILING,
    align,
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
    """Four words out of sixty is a 7% capture rate and a real, terrible
    result. It is NOT a wrong file: every word in the transcript is a script
    word. Refusing it would suppress the most damning finding the experiment
    could produce."""
    ref = numbered(60)
    partial = " ".join(f"word{i}" for i in range(1, 5))
    s = score(ref, partial, VOCAB)
    assert s["script_share"] == 1.0
    assert s["unalignable"] is False
    assert s["capture_rate"] == 4 / 60


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


def cell(capture=None, name_rate=None, mentions=0, unalignable=False, reason=""):
    return {
        "capture_rate": capture,
        "name_hit_rate": name_rate,
        "name_mentions": mentions,
        "unalignable": unalignable,
        "unalignable_reason": reason,
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
