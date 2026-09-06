#!/bin/sh
# The sound layer — the first noise this product has ever made.
#
#   sh app/ios/Tests/run_sound_tests.sh
#
# Anticipy listens for a living and, until 2026-09-06, made no sound at all.
# The argument for fixing that is Apple's own film `Design Is How It Works`,
# which has no dialogue: its entire caption track is confirmation sounds.
#
# SoundPolicy is pure Foundation, so the production source compiles straight in.
# The source facts below are the rules that cannot be expressed as a walk.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

policy="$app/SoundPolicy.swift"
engine="$app/SoundEngine.swift"
session="$app/AnticipyApp.swift"
listener="$app/Audio/PhoneListener.swift"
sounds="$app/Resources/Sound"
for f in "$policy" "$engine" "$session" "$listener"; do
    [ -f "$f" ] || { echo "missing $f"; exit 2; }
done

code() { sed 's://.*$::' "$1" | sed 's:///.*$::'; }

# ============================================ EVERY CUE HAS A FILE BESIDE IT
# The enum's raw value IS the filename. A rename in one place and not the other
# is a cue that silently stops existing — `SoundEngine` returns nil and plays
# nothing, with no error anywhere.
for cue in listen-open heard listen-close needs-you done; do
    [ -f "$sounds/$cue.caf" ] || {
        echo "SoundPolicy.Cue names '$cue' but Resources/Sound/$cue.caf is missing."
        echo
        echo "The raw value is the filename. A cue with no file plays nothing and"
        echo "says nothing — AudioServicesCreateSystemSoundID just fails and the"
        echo "engine returns. Regenerate with: python3 app/ios/Tools/synth_cues.py"
        exit 2
    }
    grep -q "\"$cue\"" "$policy" || { echo "$cue.caf exists but no Cue names it"; exit 2; }
done
extra=$(ls "$sounds" 2>/dev/null | grep -c '\.caf$' || true)
if [ "$extra" != "5" ]; then
    echo "Resources/Sound holds $extra cue files; the vocabulary is FIVE."
    echo "A product that makes six noises is a product somebody turns off."
    exit 2
fi

# ================================================== THE BREATHS BRACKET THE ENGINE
# THE most breakable rule in this feature, and it is invisible.
#
# `listen-open` is tonal. SoundPolicy refuses a tonal cue whenever the mic is
# running on the speaker route, because our capture session is `.measurement`
# (no echo cancellation) pointed at `.defaultToSpeaker` — a pitched sound played
# an inch from a live mic can be transcribed and posted as a line the owner
# never said. Played BEFORE `listener.start()` the engine is not up yet and the
# rule never has to refuse.
#
# Move the call below the start and the cue silently stops existing on every
# phone without headphones. Nobody notices a sound that is missing.
# Scoped to startListening() alone. `listener.start()` also appears in
# resumeListeningIfWanted(), which deliberately plays NO cue: a resume restores
# a standing wish after a phone call or a relaunch, and a breath on every
# foreground would be noise rather than confirmation.
fn=$(awk '/^    func startListening\(\) \{/{g=1} g{print} g&&/^    \}$/{exit}' "$session")
# Comments stripped first: the header above the call explains the rule and
# names `listener.start()` in prose, which would otherwise match before the
# real call and fail a correct file.
fnc=$(printf '%s\n' "$fn" | sed 's://.*$::')
open_line=$(printf '%s\n' "$fnc" | grep -n 'playCue(.listenOpen)' | head -1 | cut -d: -f1)
start_line=$(printf '%s\n' "$fnc" | grep -n 'listener.start()' | head -1 | cut -d: -f1)
if [ -z "$open_line" ] || [ -z "$start_line" ] || [ "$open_line" -ge "$start_line" ]; then
    echo "listen-open is not played BEFORE listener.start()."
    echo
    echo "It is a tonal cue, and a tonal cue over a live microphone on the"
    echo "speaker route is refused by SoundPolicy — so moved inside the running"
    echo "window it goes silent on every phone without headphones, with nothing"
    echo "anywhere reporting a missing sound."
    exit 2
fi
fn2=$(awk '/^    func stopListening\(\) \{/{g=1} g{print} g&&/^    \}$/{exit}' "$session")
fn2c=$(printf '%s\n' "$fn2" | sed 's://.*$::')
close_line=$(printf '%s\n' "$fn2c" | grep -n 'playCue(.listenClose)' | head -1 | cut -d: -f1)
stop_line=$(printf '%s\n' "$fn2c" | grep -n 'listener.stop()' | head -1 | cut -d: -f1)
if [ -z "$close_line" ] || [ -z "$stop_line" ] || [ "$close_line" -le "$stop_line" ]; then
    echo "listen-close is not played AFTER listener.stop(). Same rule, mirrored:"
    echo "the engine has to be down before a pitched cue is safe on the speaker."
    exit 2
fi

# =========================================== THE PERMISSION THIS ALL RESTS ON
# `setAllowHapticsAndSystemSoundsDuringRecording(true)` was added on build 32
# because iOS silently mutes the Taptic Engine for a whole app while a recording
# session is live. The same call is what permits SYSTEM SOUNDS over that
# session. Delete it and every cue dies the moment listening starts — silently,
# because iOS reports nothing.
if ! grep -q 'setAllowHapticsAndSystemSoundsDuringRecording(true)' "$listener"; then
    echo "PhoneListener no longer allows system sounds during recording."
    echo
    echo "That one call is what lets ANY cue play while she is listening, and it"
    echo "is also what keeps the haptics alive (build 32's 'I feel no haptics"
    echo "anywhere' report). iOS surfaces nothing when it is missing."
    exit 2
fi

# ====================================== THE ENGINE USES THE BLESSED PATH ONLY
# AVAudioPlayer would play through the app's OWN session — .playAndRecord,
# .measurement, primary mic pinned — and taking that session for playback risks
# a route change mid-capture, which is exactly what PhoneListener rebuilds the
# engine for. The cue would cost a gap in somebody's transcript.
if code "$engine" | grep -qE 'AVAudioPlayer|AVPlayer|AVAudioEngine'; then
    echo "SoundEngine plays through an AV player instead of a system sound."
    code "$engine" | grep -nE 'AVAudioPlayer|AVPlayer|AVAudioEngine'
    exit 2
fi
if ! grep -q 'AudioServicesPlaySystemSound' "$engine"; then
    echo "SoundEngine no longer uses the system-sound path."
    exit 2
fi
# It must not touch the capture session's configuration.
if code "$engine" | grep -qE 'setCategory|setActive|setMode'; then
    echo "SoundEngine reconfigures the audio session."
    echo "The capture path owns that configuration and rebuilds its engine on a"
    echo "route change. A cue may read the route; it may never set one."
    code "$engine" | grep -nE 'setCategory|setActive|setMode'
    exit 2
fi

# ================================================== A REFUSAL IS NEVER SILENT
if ! code "$policy" | grep -q 'case refuse(Refusal)'; then
    echo "SoundPolicy no longer returns a REASON when it declines to play."
    echo "This codebase does not have functions that refuse silently: the"
    echo "refusals are the interesting half and Developer Diagnostics shows them."
    exit 2
fi

# ====================================================== NOTHING READS THE WORDS
# Law 1. A cue is chosen by flags, counts and a clock — never by looking at what
# anybody said.
if code "$policy" | grep -qE 'NSRegularExpression|range\(of:|localizedCaseInsensitiveContains|hasPrefix\("|contains\("'; then
    echo "SoundPolicy reads the WORDS of something."
    echo "Law 1: nothing but a model decides what a sentence MEANS, and a cue is"
    echo "certainly not allowed to."
    code "$policy" | grep -nE 'NSRegularExpression|range\(of:|localizedCaseInsensitiveContains|hasPrefix\("|contains\("'
    exit 2
fi

# ============================== THE DEAFNESS DOMINATES ALL FOUR SINKS
# The tap feeds FOUR consumers, not two: the speaker-identity embedder, the
# analyzer, the recognizer request, and the orphan replay queue. A deafen check
# below any of them lets a cue reach a VOICEPRINT — which the owner cannot see
# happen and cannot undo.
tap_start=$(grep -n 'input.installTap(onBus: 0' "$listener" | head -1 | cut -d: -f1)
deaf=$(grep -n 'self.deafUntil > CACurrentMediaTime()' "$listener" | head -1 | cut -d: -f1)
if [ -z "$deaf" ]; then
    echo "The capture tap no longer goes deaf while the app is making a noise."
    echo
    echo "The session is .measurement — no echo cancellation — pointed at"
    echo ".defaultToSpeaker, so every cue arrives back at the tap at full"
    echo "strength. Without this the app records its own voice."
    exit 2
fi
for sink in 'self.speaker?.accept(buffer)' 'self.analyzerEngine?.append(buffer)'             'req.append(buffer)' 'self.orphanBuffers.append(buffer)'; do
    line=$(grep -n -- "$sink" "$listener" | head -1 | cut -d: -f1)
    [ -n "$line" ] || { echo "the tap's sink '$sink' moved; re-point this leg"; exit 2; }
    if [ "$deaf" -ge "$line" ]; then
        echo "The deafen check does not dominate the sink '$sink'."
        echo "A deafen below any sink is a cue reaching that consumer — and one"
        echo "of them is the on-device voiceprint."
        exit 2
    fi
done
if ! grep -q 'listener?.deafUntil = CACurrentMediaTime()' "$engine"; then
    echo "SoundEngine no longer arms the deafness window."
    exit 2
fi
# ARMED BEFORE THE NOISE, never after: the tap reads it on the audio thread.
arm=$(code "$engine" | grep -n 'deafUntil = CACurrentMediaTime' | head -1 | cut -d: -f1)
play=$(code "$engine" | grep -n 'AudioServicesPlaySystemSound' | head -1 | cut -d: -f1)
if [ -z "$arm" ] || [ -z "$play" ] || [ "$arm" -ge "$play" ]; then
    echo "The deafness is armed at or after the sound, so the first buffers of"
    echo "the app's own cue reach the microphone."
    exit 2
fi

# ========================= THE FIRST COMPLETED ERRAND IS NOT SILENT
# `if !seenDoneJobIDs.isEmpty` was a live defect: the set is ALSO empty on the
# refresh that first fills it, so an owner's first-ever finished errand arrived
# with no haptic, no cue and no ceremony. Anchored to the symbol, never a line
# window — a windowed version of this leg was green over the unfixed code.
if code "$session" | grep -q 'seenDoneJobIDs.isEmpty\|seenWaitingJobIDs.isEmpty'; then
    echo "The first-completion defect is back."
    echo
    echo "An empty seen-set is not evidence that this is the first refresh — it"
    echo "is also what the refresh that FIRST FILLS IT looks like, which is the"
    echo "one carrying somebody's first-ever completed errand."
    code "$session" | grep -n 'seenDoneJobIDs.isEmpty\|seenWaitingJobIDs.isEmpty'
    exit 2
fi
if ! grep -q 'hasRefreshedBefore' "$session"; then
    echo "Nothing records whether a refresh has happened before."
    exit 2
fi

# ================================ THE LEDGER IS PERSON STATE
if ! grep -q 'removeObject(forKey: "ceremony.spent")' "$session"; then
    echo "The ceremony ledger survives a change of owner."
    echo "The next person on this handset would find their first finished"
    echo "errands arriving in silence, marked as already seen by somebody else."
    exit 2
fi

# ---------------------------------------------------------------- the walk
cp "$here/SoundTests.swift" "$out/main.swift"
swiftc "$policy" "$out/main.swift" -o "$out/soundtests"
"$out/soundtests"
