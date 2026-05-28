"""
Audio helpers for the verifier. Uses BlackHole 2ch as virtual loopback.

The user must have:
- BlackHole 2ch installed
- A Multi-Output Device "Anticipy Loopback" containing Built-in Output + BlackHole 2ch,
  set as the default system output.

With that setup:
- Capturing the BlackHole input device records anything the system plays.
- Setting input to BlackHole and playing audio to BlackHole effectively pipes audio
  into the mic input (useful for testing the listening pipeline).
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path


BLACKHOLE_INPUT_NAME = "BlackHole 2ch"
LOOPBACK_OUTPUT_NAME = "Anticipy Loopback"


def capture_system_audio(out_path: Path, duration_secs: float, device: str = BLACKHOLE_INPUT_NAME) -> bool:
    """
    Capture system audio (whatever is playing) to a wav file via BlackHole.
    Uses ffmpeg with avfoundation backend.
    """
    # Find the input device index for BlackHole
    idx = _find_avfoundation_input(device)
    if idx is None:
        return False
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "avfoundation",
        "-i", f":{idx}",
        "-t", str(duration_secs),
        "-ac", "1",
        "-ar", "16000",
        str(out_path),
    ]
    try:
        p = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=duration_secs + 15)
        return p.returncode == 0 and out_path.exists() and out_path.stat().st_size > 1000
    except subprocess.TimeoutExpired:
        return False


def play_audio(audio_path: Path, blocking: bool = True) -> bool:
    """Play an audio file through the default output (which is Anticipy Loopback)."""
    if blocking:
        p = subprocess.run(["afplay", str(audio_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
        return p.returncode == 0
    else:
        subprocess.Popen(["afplay", str(audio_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True


def say_to_loopback(text: str, voice: str = "Samantha") -> Path:
    """Use macOS `say` to synthesize text. Returns the AIFF path."""
    out = Path(f"/tmp/say_{int(time.time()*1000)}.aiff")
    subprocess.run(["say", "-v", voice, "-o", str(out), text], check=True, timeout=60)
    return out


def set_default_input(device_name: str) -> bool:
    """
    Set the default system audio input device.
    Requires `switchaudio-source` (brew install switchaudio-osx).
    """
    p = subprocess.run(
        ["SwitchAudioSource", "-t", "input", "-s", device_name],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
    )
    return p.returncode == 0


def set_default_output(device_name: str) -> bool:
    p = subprocess.run(
        ["SwitchAudioSource", "-t", "output", "-s", device_name],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
    )
    return p.returncode == 0


def _find_avfoundation_input(device_name: str) -> int | None:
    """Run ffmpeg -list_devices and find the index of a named input device."""
    p = subprocess.run(
        ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
    )
    text = (p.stdout + p.stderr).decode("utf-8", errors="replace")
    # The output looks like:
    # [AVFoundation indev @ 0x...] AVFoundation audio devices:
    # [AVFoundation indev @ 0x...] [0] BlackHole 2ch
    # [AVFoundation indev @ 0x...] [1] Built-in Microphone
    in_audio = False
    for line in text.splitlines():
        if "audio devices" in line.lower():
            in_audio = True
            continue
        if in_audio:
            # Parse [N] Name
            line = line.strip()
            if "]" in line:
                idx_part, name_part = line.rsplit("[", 1)[-1].split("]", 1)
                try:
                    idx = int(idx_part.strip())
                except ValueError:
                    continue
                if device_name.lower() in name_part.lower().strip():
                    return idx
    return None


def transcribe_with_deepgram(wav_path: Path, api_key: str | None = None, timeout: int = 60) -> str | None:
    """Send a wav to Deepgram and return the transcript text. None on failure."""
    api_key = api_key or os.environ.get("DEEPGRAM_API_KEY")
    if not api_key:
        return None
    import requests
    with open(wav_path, "rb") as f:
        data = f.read()
    try:
        r = requests.post(
            "https://api.deepgram.com/v1/listen?model=nova-3&smart_format=true",
            headers={
                "Authorization": f"Token {api_key}",
                "Content-Type": "audio/wav",
            },
            data=data,
            timeout=timeout,
        )
        r.raise_for_status()
        j = r.json()
        return j["results"]["channels"][0]["alternatives"][0]["transcript"]
    except Exception:
        return None


def word_error_rate(reference: str, hypothesis: str) -> float:
    """Standard WER. Lowercase, strip punctuation, compute edit distance over words."""
    import re
    def norm(s: str) -> list[str]:
        s = s.lower()
        s = re.sub(r"[^a-z0-9 ']", " ", s)
        return [t for t in s.split() if t]
    r = norm(reference)
    h = norm(hypothesis)
    if not r:
        return 1.0 if h else 0.0
    # Levenshtein on word lists
    d = [[0] * (len(h) + 1) for _ in range(len(r) + 1)]
    for i in range(len(r) + 1):
        d[i][0] = i
    for j in range(len(h) + 1):
        d[0][j] = j
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            cost = 0 if r[i - 1] == h[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
    return d[len(r)][len(h)] / len(r)
