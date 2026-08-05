"""Proof: she knows HIS voice, and learns the people around him.

Omar, 2026-08-05: "tell me we recognize your voice, and then we start to
recognize people around you's voice as well."

Day 1 he talks with a friend. Day 2 — separate recordings, different
sentences — the SAME friend must come back as the SAME person, a brand
new voice must be recognised as new (not silently folded into anyone),
and nobody but Omar may ever be called Omar.

That last one is the whole reason the thresholds moved: a third voice
scored 0.667 against the owner profile, so the original 0.60 gate would
have put a stranger's promises in his mouth.

Run: PYTHONPATH=. python3 proof/voice_roster_proof.py [<models dir>]
"""
from __future__ import annotations

import os
import sys
import tempfile
import wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from proof.voice_roster import VoiceRoster, cosine  # noqa: E402

MODELS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", ".speaker-models")
CLIPS = os.environ.get("VOICE_CLIPS", "")


def load(path: str) -> np.ndarray:
    w = wave.open(path, "rb")
    return (np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
            .astype(np.float32) / 32768.0)


def main() -> int:
    try:
        import sherpa_onnx
    except ImportError:
        print("SKIP voice roster — pip install sherpa-onnx numpy")
        return 0
    emb_model = os.path.join(MODELS, "emb.onnx")
    if not os.path.exists(emb_model) or not CLIPS:
        print("SKIP voice roster — needs .speaker-models/emb.onnx and "
              "VOICE_CLIPS=<dir with omar.wav friend.wav omar_later.wav "
              "friend_later.wav v3.wav>")
        return 0

    ex = sherpa_onnx.SpeakerEmbeddingExtractor(
        sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=emb_model))

    def embed(name):
        st = ex.create_stream()
        st.accept_waveform(16000, load(os.path.join(CLIPS, name)))
        st.input_finished()
        return np.array(ex.compute(st))

    roster = VoiceRoster(os.path.join(tempfile.mkdtemp(), "roster.json"))
    failures = []

    # --- day 1 -----------------------------------------------------------
    roster.enroll_owner(embed("omar.wav"))
    d1_friend = roster.identify(embed("friend.wav"))
    print(f"day 1  friend speaks  -> {d1_friend['tag']} "
          f"(score {d1_friend['score']:.3f})")
    if not d1_friend["tag"].startswith("other:"):
        failures.append(f"the friend was not learned as a person: {d1_friend}")
    friend_id = d1_friend["id"]

    # --- day 2, entirely separate recordings ------------------------------
    d2_owner = roster.identify(embed("omar_later.wav"))
    print(f"day 2  Omar speaks    -> {d2_owner['tag']} "
          f"(score {d2_owner['score']:.3f})")
    if d2_owner["tag"] != "owner":
        failures.append(f"Omar was not recognised on day 2: {d2_owner}")

    d2_friend = roster.identify(embed("friend_later.wav"))
    print(f"day 2  friend again   -> {d2_friend['tag']} "
          f"(score {d2_friend['score']:.3f})")
    if d2_friend["id"] != friend_id:
        failures.append(
            f"the same friend came back as someone else: {d2_friend}")

    d2_new = roster.identify(embed("v3.wav"))
    print(f"day 2  a NEW person   -> {d2_new['tag']} "
          f"(score {d2_new['score']:.3f})")
    if d2_new["tag"] == "owner":
        failures.append(
            f"A STRANGER WAS CALLED OMAR — their promises would become his: "
            f"{d2_new}")
    if d2_new["id"] in (friend_id, None) and d2_new["tag"] != "unknown":
        failures.append(f"the new person was folded into someone else: {d2_new}")

    # --- naming works, and survives ---------------------------------------
    roster.name_person(friend_id, "Sarah")
    again = roster.identify(embed("friend.wav"))
    print(f"after naming          -> {again['tag']} name={again['name']}")
    if again["name"] != "Sarah":
        failures.append(f"the learned name did not stick: {again}")

    print()
    if failures:
        for f in failures:
            print(f"FAIL {f}")
        print("\nVOICE ROSTER: NOT READY")
        return 1
    print("PASS his voice is recognised across days")
    print("PASS a recurring person is recognised as the SAME person")
    print("PASS a new voice is new, and nobody else is ever called Omar")
    print("PASS a name attaches to a voice and sticks")
    print("\nVOICE ROSTER: READY")
    return 0


if __name__ == "__main__":
    sys.exit(main())
