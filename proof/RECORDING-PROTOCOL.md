# Recording protocol — the engine-or-audio-path experiment

You are making **three recordings of the same page of text**, about three
minutes each. Twenty minutes, one room, one phone. Everything else is scoring,
and the Mac does that.

The question being settled: **are words being lost because the recognizer is
weak, or because the microphone is set up to hear badly?** Nobody knows. Two
of the three recordings differ by one setting; the third exists to prove the
scoring is trustworthy.

## Before you start

- A build of the app carrying the **scratch recorder** — the thing that writes
  the microphone tap to a WAV file and can decode it offline. If you do not
  have that build, stop; it is the missing piece and nothing here works
  without it. (`.superpowers/sdd/agc-harness-report.md` says exactly what it
  has to do.)
- The script: **`proof/fixtures/read_aloud_script.txt`**. Print it, or put it
  on a laptop screen you can read from without leaning in.
- A normal room. Not a studio, not a café. Some background noise is the point —
  this product lives on a table in a real room.
- **Put a piece of tape on the table where the phone goes.** Recordings one and
  two must be from the same spot to within a few centimetres, or you are
  measuring where you put the phone.

## The three recordings

| | Where the phone is | What is different | Roughly |
|---|---|---|---|
| **A** | On the tape, ~2 m from you, screen up | nothing — this is today's app | 3 min |
| **B** | On the same tape, same distance | **voice processing turned on** in the scratch recorder | 3 min |
| **C** | Held about 20 cm from your mouth | back to today's settings | 3 min |

Read **the whole script, out loud, every time**. Same voice, same pace, same
volume for A and B — you are the constant they are compared against.

## While you are reading

- **Read what is on the page.** Do not paraphrase, do not skip, do not
  improvise. The scoring compares your words against that exact page.
- **Fumbled a word? Keep going.** Fumbled a whole sentence, or lost your place?
  **Stop, delete that recording and start it again.** A recording where you
  said something different from the page scores as lost words, and it would
  land on the wrong side of the argument.
- Speak at a normal conversational volume — the volume you would use talking to
  someone across the table. Not projected, not quiet.
- **Do not read the script and then keep chatting into the same recording.**
  If you want free conversation too, that is a fourth, separate file. The
  scorer refuses a file with both in it, and it is right to.

## When you are done

Three WAVs, three transcripts from the scratch recorder, named so nobody can
mix them up:

```
arm_a.wav   arm_a_sf_ctx.txt   arm_a_sf_noctx.txt
arm_b.wav   arm_b_sf_ctx.txt
arm_c.wav
```

**The names are load-bearing.** The scorer catches an obviously wrong file. It
cannot catch arm A's transcript filed under arm B — those are two recordings of
the same page and no arithmetic can tell them apart. Getting them swapped would
reverse the answer.

Then, on the Mac:

```sh
python3 proof/engine_or_audio.py --scaffold proof/runs/$(date +%F)
# copy the transcripts into the paths the manifest names, then:
python3 proof/reference_decode.py --wav arm_a.wav --out proof/runs/<id>/arm_a/reference.txt
python3 proof/reference_decode.py --wav arm_c.wav --out proof/runs/<id>/arm_c/reference.txt
python3 proof/engine_or_audio.py --run proof/runs/<id>
```

The last command prints the numbers and the verdict. **The rule it applies was
written down before you recorded anything** — run `--explain` to read it first
if you want to know what you are about to find out. Do not change it
afterwards.

## Two things that will happen and are not your fault

- **"CANNOT DECIDE"** is a real answer. It usually means recording C came out
  poorly, which means the reference decoder has not proved it can hear a clean
  recording of this script — so nothing it says about recordings A and B can be
  trusted yet. Re-record C closer and quieter.
- **A cell coming back REFUSED** means the scorer will not put a number on that
  file. Read the sentence it gives you; it names what it thinks went wrong.
  That is deliberate — a bad number here reads exactly like a real finding.
