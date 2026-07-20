"""Anticipy audio pipeline (the proven core of the phone app).

Takes the raw BLE audio stream captured from the pendant (length-prefixed
Opus packets, exactly the framing the firmware sends over GATT characteristic
19b10001-...), reassembles frames, decodes Opus @16kHz mono, and writes a WAV.
Transcription is then done by a cloud STT in the app; here we expose the decode
step that was proven on real hardware (Omar's 66s recording).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

import numpy as np
import opuslib
import soundfile as sf

SAMPLE_RATE = 16000
FRAME_SAMPLES = 960  # 60ms @ 16kHz


@dataclass
class DecodeResult:
    seconds: float
    frames: int
    bad_frames: int
    wav_path: str


def frames_from_ble_dump(raw: bytes) -> list[bytes]:
    """Parse the [uint16 len][payload] framing we captured off the pendant.

    Each BLE packet begins with a 3-byte Omi header (index lo, index hi,
    internal counter); a new audio frame starts when the internal counter is 0.
    """
    packets = []
    i = 0
    while i + 2 <= len(raw):
        (ln,) = struct.unpack("<H", raw[i : i + 2])
        i += 2
        packets.append(raw[i : i + ln])
        i += ln

    frames: list[bytes] = []
    cur = b""
    for p in packets:
        if len(p) < 3:
            continue
        internal = p[2]
        payload = p[3:]
        if internal == 0:
            if cur:
                frames.append(cur)
            cur = payload
        else:
            cur += payload
    if cur:
        frames.append(cur)
    return frames


def decode_dump_to_wav(dump_path: str, wav_path: str) -> DecodeResult:
    raw = open(dump_path, "rb").read()
    frames = frames_from_ble_dump(raw)
    dec = opuslib.Decoder(SAMPLE_RATE, 1)
    pcm = b""
    bad = 0
    for f in frames:
        try:
            pcm += dec.decode(f, FRAME_SAMPLES)
        except Exception:
            bad += 1
    arr = np.frombuffer(pcm, dtype="<i2").astype("float32") / 32768.0
    sf.write(wav_path, arr, SAMPLE_RATE)
    return DecodeResult(seconds=len(arr) / SAMPLE_RATE, frames=len(frames), bad_frames=bad, wav_path=wav_path)


if __name__ == "__main__":
    import sys
    r = decode_dump_to_wav(sys.argv[1], sys.argv[2])
    print(f"decoded {r.seconds:.1f}s from {r.frames} frames ({r.bad_frames} bad) -> {r.wav_path}")
