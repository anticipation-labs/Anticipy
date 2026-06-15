"""The always-on Mac-mic capture source — heard speech -> the engine, deterministically.

The real path (ffmpeg record -> Whisper -> emit) is proven live with audio; this pins the pure
logic so it can't silently regress: the noise filter (Whisper hallucinates "you"/"thank you" on
silence — a quiet room must never fabricate a task), the timestamp strip, emit_stub, and the
rolling-window loop emitting a real utterance while dropping a noise window.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_mac_mic.py
"""
import types

from anticipy_engine.capture import mac_mic as MM
from anticipy_engine.capture.mac_mic import MacMicSource, _clean_line, _is_noise


class FakeTranscript:
    def __init__(self, lines):
        self.lines = lines


def main():
    # a quiet room must never become a task: Whisper's stock silence-hallucinations are noise
    for n in ("", "you", "Thank you.", "thanks for watching!", "um", "uh", "♪", "so", "ok"):
        assert _is_noise(n), f"{n!r} should be filtered"
    for real in ("Remind me to call the dentist", "pick up the kids at 3", "buy milk on the way"):
        assert not _is_noise(real), real

    # the file transcriber prefixes [hh:mm:ss]; the mic strips it before the brain sees it
    assert _clean_line("[00:00:03] Schedule a meeting") == "Schedule a meeting"
    assert _clean_line("00:00:03-00:00:05] hello there") == "hello there"

    # emit_stub pushes a CaptureEvent through the sink as source 'mac_mic'
    heard = []
    MacMicSource(lambda ev: heard.append((ev.source, ev.text))).emit_stub("pick up the kids at 3")
    assert heard == [("mac_mic", "pick up the kids at 3")], heard

    # the rolling-window loop: a real utterance is emitted, a noise window is dropped, then it stops
    seq = [["[00:00:01] Remind me to call mom tomorrow"], ["you"], None]  # real, noise, sentinel->stop
    calls = {"i": 0}

    def fake_record(self):
        i = calls["i"]; calls["i"] += 1
        if seq[i] is None:
            self._running = False
            return None
        return f"/tmp/_fake_mic_{i}.wav"

    MM.transcribe_audio = lambda path: FakeTranscript(seq[int(str(path).split("_")[-1].split(".")[0])])
    got = []
    src = MacMicSource(lambda ev: got.append(ev.text))
    src._record_window = types.MethodType(fake_record, src)
    src._safe_unlink = staticmethod(lambda p: None)  # fake paths never existed
    src._running = True
    src._loop()
    assert got == ["Remind me to call mom tomorrow"], ("real emitted, noise dropped", got)
    assert src.utterances == 1 and src.windows == 2, (src.windows, src.utterances)

    print("PASS mac_mic: real mic source emits heard utterances to the brain, drops silence-noise, "
          "strips timestamps (live ffmpeg+Whisper capture proven separately)")


if __name__ == "__main__":
    main()
