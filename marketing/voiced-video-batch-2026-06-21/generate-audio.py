from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import requests
from dotenv import load_dotenv
from pydub import AudioSegment
from pydub.generators import Sine, WhiteNoise


ROOT = Path(__file__).resolve().parent
ROWS = json.loads((ROOT / "videos.json").read_text())
AUDIO_DIR = ROOT / "renders" / "audio"
RAW_DIR = AUDIO_DIR / "raw"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR.mkdir(parents=True, exist_ok=True)

for env_path in [
    "/Users/omarebrahim/Anticipy/.env.local",
    "/Users/omarebrahim/anticipy-video/.env",
    "/Users/omarebrahim/Anticipy-Content/.env",
]:
    if Path(env_path).exists():
        load_dotenv(env_path, override=False)


ELEVEN_VOICE_ID = "CwhRBWXzGAHq8TQ4Fs17"  # Roger - laid-back, casual, resonant


def eleven_tts(text: str, output: Path) -> bool:
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        return False
    body = {
        "text": text.replace("small cough. ", ""),
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.32,
            "similarity_boost": 0.78,
            "style": 0.42,
            "use_speaker_boost": True,
        },
    }
    response = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVEN_VOICE_ID}",
        headers={
            "xi-api-key": api_key,
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
        },
        params={"output_format": "mp3_44100_128"},
        json=body,
        timeout=120,
    )
    if response.status_code >= 400:
        print(f"ElevenLabs failed: {response.status_code} {response.text[:240]}")
        return False
    output.write_bytes(response.content)
    return True


def openai_tts(text: str, output: Path) -> bool:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return False
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        with client.audio.speech.with_streaming_response.create(
            model="gpt-4o-mini-tts",
            voice="ash",
            input=text.replace("small cough. ", ""),
            instructions=(
                "Speak like a slightly tired founder recording a real voice memo. "
                "Natural, imperfect, dry, not announcer-like. Keep ums and small hesitations."
            ),
            response_format="mp3",
        ) as response:
            response.stream_to_file(output)
        return True
    except Exception as exc:
        print(f"OpenAI TTS failed: {exc}")
        return False


def edge_tts(text: str, output: Path) -> bool:
    cmd = [
        "edge-tts",
        "--voice",
        "en-US-BrianMultilingualNeural",
        "--rate=-5%",
        "--pitch=-2Hz",
        "--text",
        text.replace("small cough. ", ""),
        "--write-media",
        str(output),
    ]
    result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    if result.returncode != 0:
        print(result.stderr)
        return False
    return True


def cough() -> AudioSegment:
    first = WhiteNoise().to_audio_segment(duration=180).high_pass_filter(150).low_pass_filter(2600) - 10
    second = WhiteNoise().to_audio_segment(duration=230).high_pass_filter(120).low_pass_filter(2100) - 13
    chest = Sine(120).to_audio_segment(duration=260) - 24
    sound = first.fade_in(8).fade_out(80) + AudioSegment.silent(duration=55) + second.fade_in(10).fade_out(120)
    return sound.overlay(chest).fade_out(120)


def click(duration=55, gain=-21) -> AudioSegment:
    return (WhiteNoise().to_audio_segment(duration=duration).high_pass_filter(1800).low_pass_filter(7000) + gain).fade_out(duration)


def process_voice(row: dict, raw_mp3: Path, out_wav: Path) -> None:
    speech = AudioSegment.from_file(raw_mp3)
    speech = speech.set_frame_rate(48000).set_channels(1)

    bed = WhiteNoise().to_audio_segment(duration=len(speech) + 900).low_pass_filter(420).high_pass_filter(70) - 47
    mix = bed.overlay(speech + 3, position=110)

    if "small cough" in row["voice"]:
        mix = mix.overlay(cough(), position=120)

    for pos in [4600, 9800, 15050, 21000]:
        if pos < len(mix) - 300:
            mix = mix.overlay(click(), position=pos)

    temp = out_wav.with_suffix(".premaster.wav")
    mix.export(temp, format="wav")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(temp),
            "-af",
            "highpass=f=80,acompressor=threshold=-20dB:ratio=2.8:attack=4:release=55,loudnorm=I=-14:TP=-1.5:LRA=8",
            "-ar",
            "48000",
            "-ac",
            "2",
            str(out_wav),
        ],
        check=True,
    )
    temp.unlink(missing_ok=True)


for row in ROWS:
    raw = RAW_DIR / f"{row['id']}.mp3"
    final = AUDIO_DIR / f"{row['id']}.wav"
    if final.exists():
        print(f"Skipping existing voice for {row['id']}")
        continue
    print(f"Generating voice for {row['id']}")
    ok = eleven_tts(row["voice"], raw) or openai_tts(row["voice"], raw) or edge_tts(row["voice"], raw)
    if not ok:
        raise RuntimeError(f"No TTS provider succeeded for {row['id']}")
    process_voice(row, raw, final)

print(f"Generated {len(ROWS)} mastered voice tracks.")
