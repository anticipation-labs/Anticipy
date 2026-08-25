# The pendant is mute, and what it would take to make it speak

2026-08-25 · branch `jose_anticipy_system` · build 83 → 84 · commit `ca317582`

    python3 overnight/no_vendor_ears.py                        1 -> 0
    python3 -m pytest tests/ -q --ignore=tests/test_day_zero_oracle.py
                                            1 failed/2168 -> 2169 passed, 0

The iOS half of design/LOCAL-FIRST.md rule 1. The server half was `49b04481`;
the four remaining references were all in `app/ios`.

## What was removed

- `app/ios/Anticipy/Audio/TranscriberClient.swift` — **deleted**. It opened a
  websocket to a speech vendor and forwarded the pendant's raw Opus frames
  undecoded.
- `AnticipyBackend.transcriptionToken()` — deleted. It exchanged the owner's
  session for a 60-second vendor JWT.
- `schedulePendantRetry` and the retry bookkeeping — deleted.
- Five user-facing sentences — **rewritten, not deleted**.

`startPendantTranscription` now leaves `onOpusFrame` nil, so frames are dropped
where they arrive rather than queued for something downstream to decide about.

## What it cost

Nothing that worked. Production events with `source="pendant"`: **ZERO, ever**,
against 229 from the phone microphone. The lane never delivered a single row.

## Why deleted rather than left inert

An inert class named `TranscriberClient` with a live `connect(accessToken:)`
signature is a socket-shaped hole waiting to be refilled. The law says find a
better local model; leaving a vendor-shaped slot invites somebody to fill it in
instead of building the replacement. It was also the only consumer of the
websocket/keep-alive/receive-loop machinery, none of which an on-device
transcriber needs, and two transcriber types — one of them a decoy — is worse
than one honest gap.

`BoundedOpusQueue` **stays**. No consumer today, and that is honest rather than
dead: an on-device Opus path needs exactly that bounded queue, and it is
separately stressed.

## The retry loop, and the rule if a remote lane ever returns

`/transcription/token` answers **410 GONE**. The old catch called
`schedulePendantRetry` on ANY error, so a permanent refusal spun a three-second
reconnect forever against a connected pendant — battery and radio spent on a
decision that is never going to change.

The fix was not a status check in front of the retry. A 410 is not an outage to
be handled gracefully; it is the product refusing. So the *request* is gone
rather than guarded, and nothing is left to interpret an answer.

**Written down so it is not re-derived:** a `410` is a DECISION and must stop
trying. A `5xx` or a dropped connection is an OUTAGE and may be retried. One
catch must never be widened over both.

## The copy — the part that mattered most

Three sentences told the owner their pendant audio went to a named vendor. Two
more promised a stream that was never coming:

    "Pendant · starting transcription"
    "I'm opening its secure transcription stream."

**`no_vendor_ears.py` cannot see those two.** It greps for the vendor's
hostname, and a lie told without naming anybody passes it clean. They were also
the branches that ACTUALLY RENDERED, because `pendantCapturing` can no longer
become true — so the sentences a person would really have read were the two the
gate was blind to. A gate that greps for a name cannot catch a false promise
made without one.

All five are now false, and a false privacy promise is worse than the violation
it described: it tells someone their audio goes somewhere it does not, and
nothing about where it went instead. They were rewritten rather than deleted —
silence where a promise was is its own failure, and somebody who read the old
sentence needs to find the new answer in the same place.

## THE REAL WORK, NOT DONE HERE

**The pendant cannot hear until an on-device transcriber exists.** The size of
that gap, so nobody scopes it as an afternoon:

- `app/ios/Anticipy/Audio/LocalTranscriber.swift` is **43 lines with zero call
  sites**. It is a sketch, not a component.
- It wants `AVAudioPCMBuffer`. **The pendant emits Opus `Data`.**
- **There is no Opus decoder in the target.** That decoder — sourcing it,
  linking it, and surviving whatever App Store Connect does to a build carrying
  a new binary dependency, which is the same hazard that has now unlinked
  sherpa-onnx twice — is the actual work.
- `SpeakerTagger` is a live warning about that last point: a binary xcframework
  in this target correlates with builds 46, 47 and 76-80 delivering nothing.

Until then the honest statement is that the pendant is a battery with a
microphone nobody reads, and both screens that mention it now say so.

## Tests that asserted the violation

Four, and they are the third instance of this shape found in the repo in one
night (a hook test asserting `/v1/auth/grant`; a test asserting the verb list
that ate a research query; these).

    test_long_lived_deepgram_key_never_enters_ios_source
        assert "connect(accessToken:" in swift        <- required the client
        assert 'setValue("Bearer ' in swift           <- required the credential
    test_pendant_frames_reach_transcriber_and_final_text_reaches_brain
        assert "transcriber.send(opusFrame: frame)"   <- required the forwarding
    test_ui_no_longer_claims_connected_pendant_drops_audio
        assert "Deepgram" in content                  <- required the UI name it
    run_audio_stress.sh
        grep BoundedOpusQueue TranscriberClient.swift <- required the wiring

Rewritten to the inverse invariant with the argument in each docstring, keeping
the protection each was really for. `DEEPGRAM_API_KEY not in swift` was kept: it
is trivially true now and should stay true forever.

**A suite that encodes what shipped rather than what was intended will defend
anything, including a thing an architecture law forbids.**

### One trap worth keeping

All of these now read CODE, not prose — whole-line comments are skipped, the way
`no_vendor_ears.py` does it. Every phrase they forbid is quoted in the comment
that removed it, and the first drafts of both the Python tests and
`run_local_ears_tests.sh` went RED on their own explanations.

The skip is **line-based**, not "cut from `//` to end of line". A vendor URL is
`"wss://host/..."`, and cutting at the first `//` would leave `"wss:` and hide
the hostname from the check hunting it.

## Still unproven

Law 3. Build 84 is compiled and installed on no phone. What is verified is that
the source cannot reach a vendor and the copy says what is true; what is
unverified is that any person has read the new sentences on a screen. The gates
here are `(tree)` checks, and `no_vendor_ears.py` states its own blind spots: a
vendor whose hostname is not in its registry, audio forwarded by a service
outside this repo, or a key supplied at runtime under another name.
