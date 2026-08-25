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
| **A** | On the tape, ~2 m from you, **screen up** | nothing — this is today's app | 3 min |
| **B** | On the same tape, same distance, **screen up** | **voice processing turned on** in the scratch recorder | 3 min |
| **C** | Held about 20 cm from your mouth | back to today's settings | 3 min |

**Screen up on both A and B.** Orientation selects which handset microphone
dominates, and the row for B used to omit it — which would have made the
difference between A and B partly the orientation and partly the setting, with
no way afterwards to say which.

Read **the whole script, out loud, every time**. Same voice, same pace, same
volume for A and B — you are the constant they are compared against.

## While you are reading

- **Read what is on the page.** Do not paraphrase, do not skip, do not
  improvise. The scoring compares your words against that exact page.
- **Fumbled a word? Keep going.** Fumbled a whole sentence, or lost your place?
  **Stop, delete that recording and start it again — and write down that you
  did.** A recording where you said something different from the page scores as
  lost words, and it would land on the wrong side of the argument.
- **Count your takes.** `manifest.json` has an `attempts` field, one number per
  arm, and it starts at 1. If you record an arm twice, put 2 there. This is not
  bookkeeping: re-recording a take until the number comes out right is the
  difference between measuring something and selecting it, and the scorer
  refuses an arm recorded more than twice. A retake for a fumbled read is fine.
  A retake **because you did not like the score** is the thing being ruled out,
  and neither you nor the scorer can tell them apart afterwards unless the
  count is written down at the time.
- Speak at a normal conversational volume — the volume you would use talking to
  someone across the table. Not projected, not quiet.
- **Do not read the script and then keep chatting into the same recording.**
  If you want free conversation too, that is a fourth, separate file. The
  scorer refuses a file with both in it, and it is right to.

## When you are done

Three WAVs and three transcripts from the scratch recorder, plus two the Mac
makes for you. **Scaffold the run
first**, then write straight into the paths the manifest names — do not invent
a flat naming scheme beside it and copy things across afterwards:

```sh
python3 proof/engine_or_audio.py --scaffold proof/runs/$(date +%F)
```

gives you exactly these, and nothing else:

```
proof/runs/<id>/arm_a/sf_ctx.txt      proof/runs/<id>/arm_a/sf_noctx.txt
proof/runs/<id>/arm_a/reference.txt
proof/runs/<id>/arm_b/sf_ctx.txt
proof/runs/<id>/arm_c/reference.txt
```

Five cells, and every one of them is read by a rule. **Every REFUSED line in
the report means something.** An earlier version of this page listed five flat
filenames while `--scaffold` wrote nine nested ones including two the page
never mentioned, so a correctly-run experiment printed four REFUSED lines that
were normal — which trains the reader to skim past the one line the whole
instrument depends on a human noticing.

### The provenance line

**Each transcript must open with one line naming where it came from:**

```
#anticipy: arm=A decoder=sf_ctx wav=arm_a.wav sha256=<sha256 of the WAV>
```

The scorer strips it before scoring and checks it against the cell it was filed
under. This is the whole mitigation for two failures that no arithmetic over
the text can catch:

- **Arm A's transcript filed under arm B.** Those are two recordings of the
  same page; nothing in the words separates them, and a swap reverses the
  answer about the audio session line.
- **A toggle that was never wired.** If `contextualStrings` is not actually
  being turned off for `sf_noctx`, the two transcripts are the same bytes and
  the scorer reads a difference of exactly zero as "the vocabulary API does
  nothing" — the strongest possible finding, produced by not having run the
  experiment. Identical bytes with two decoder names and one WAV hash on
  record is a real result. Identical bytes with nothing on record is refused.

If your recorder cannot write the line yet, add it by hand. It is one line.

Then, on the Mac:

```sh
python3 proof/reference_decode.py --check   # what decoder are you about to use?
python3 proof/reference_decode.py --wav arm_a.wav --out proof/runs/<id>/arm_a/reference.txt
python3 proof/reference_decode.py --wav arm_c.wav --out proof/runs/<id>/arm_c/reference.txt
python3 proof/engine_or_audio.py --run proof/runs/<id>
```

Run `--check` first and read what it says. The reference decoder on this
machine is `whisper base`, which is **not** the decoder §11 asked for — arm C
is the only thing standing behind it, and you should know that before you read
its numbers.

The last command prints the numbers and the verdict. **The rule it applies was
written down before you recorded anything** — run `--explain` to read it first
if you want to know what you are about to find out. Do not change it
afterwards.

## Two things that will happen and are not your fault

- **"CANNOT DECIDE"** is a real answer, and it has **two** live explanations,
  not one. Either recording C came out poorly, or **the reference decoder is
  too small** — the one on this machine is `whisper base`, a 74M-parameter
  model where §11 asked for large-v3 at 1550M. Both produce the same low score
  on arm C, so:

  1. Try **one** more recording of C, closer and quieter, and put `2` in the
     manifest's `attempts` for arm C.
  2. If it still does not clear, **stop re-recording**. Get the bigger model:
     `python3 proof/reference_decode.py --allow-download` fetches large-v3
     (~3 GB, network once) and decode again.

  Re-recording C a third time until it clears is not a fix; it turns a
  credibility check into a maximum over attempts, and the scorer refuses it.
- **A cell coming back REFUSED** means the scorer will not put a number on that
  file. Read the sentence it gives you; it names what it thinks went wrong.
  That is deliberate — a bad number here reads exactly like a real finding.
