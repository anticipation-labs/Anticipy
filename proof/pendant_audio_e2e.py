#!/usr/bin/env python3
"""Prove raw pendant-style Opus packets become finalized Deepgram text."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

import requests
import websockets


def ogg_packets(path: Path) -> list[bytes]:
    """Extract codec packets from Ogg pages; skip OpusHead and OpusTags."""
    data = path.read_bytes()
    offset = 0
    packets: list[bytes] = []
    partial = bytearray()
    while offset < len(data):
        if data[offset:offset + 4] != b"OggS" or offset + 27 > len(data):
            raise RuntimeError("ffmpeg produced an invalid Ogg stream")
        segments = data[offset + 26]
        table_start = offset + 27
        table = data[table_start:table_start + segments]
        body_start = table_start + segments
        cursor = body_start
        for size in table:
            partial.extend(data[cursor:cursor + size])
            cursor += size
            if size < 255:
                packets.append(bytes(partial))
                partial.clear()
        offset = cursor
    if partial:
        raise RuntimeError("truncated Ogg packet")
    if len(packets) < 3 or packets[0][:8] != b"OpusHead":
        raise RuntimeError("Opus headers missing")
    return packets[2:]


def jwt_from_backend(base: str) -> str:
    suffix = uuid.uuid4().hex[:12]
    email = f"pendant-proof-{suffix}@example.com"
    password = "Pendant-proof-password-42!"
    signup = requests.post(f"{base}/api/collections/owners/records", json={
        "email": email, "password": password, "passwordConfirm": password,
        "legacy_uuid": f"pendant-proof-{suffix}",
        "phone": "+1555" + str(int(suffix[:8], 16))[-7:],
    }, timeout=15)
    signup.raise_for_status()
    auth = requests.post(f"{base}/api/collections/owners/auth-with-password", json={
        "identity": email, "password": password,
    }, timeout=15)
    auth.raise_for_status()
    owner_token = auth.json()["token"]
    issued = requests.post(f"{base}/transcription/token",
                           headers={"Authorization": owner_token}, timeout=20)
    issued.raise_for_status()
    token = issued.json().get("access_token")
    if not token:
        raise RuntimeError("backend returned no short-lived transcription token")
    return token


async def transcribe(token: str, packets: list[bytes]) -> tuple[str, int]:
    url = ("wss://api.deepgram.com/v1/listen?encoding=opus&sample_rate=16000"
           "&channels=1&punctuate=true&smart_format=true&interim_results=false"
           "&endpointing=500")
    transcripts: list[str] = []
    messages = 0
    async with websockets.connect(
            url, additional_headers={"Authorization": f"Bearer {token}"},
            open_timeout=20, ping_interval=10) as socket:
        for packet in packets:
            await socket.send(packet)
            await asyncio.sleep(0.015)
        await socket.send(json.dumps({"type": "Finalize"}))
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                raw = await asyncio.wait_for(socket.recv(), timeout=3)
            except asyncio.TimeoutError:
                continue
            if not isinstance(raw, str):
                continue
            message = json.loads(raw)
            messages += 1
            if message.get("type") == "Results" and message.get("is_final", True):
                alternatives = message.get("channel", {}).get("alternatives", [])
                text = alternatives[0].get("transcript", "") if alternatives else ""
                if text.strip():
                    transcripts.append(text.strip())
            if message.get("type") in {"Metadata", "Finalize"} and transcripts:
                break
        await socket.send(json.dumps({"type": "CloseStream"}))
    return " ".join(transcripts), messages


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="http://127.0.0.1:18094")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    phrase = "Anticipy audio pipeline test, blue lantern forty two."
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="anticipy-pendant-audio-") as folder:
        root = Path(folder)
        aiff, ogg = root / "speech.aiff", root / "speech.ogg"
        subprocess.run(["say", "-v", "Samantha", "-r", "170", "-o", str(aiff), phrase],
                       check=True, capture_output=True)
        subprocess.run([
            "/opt/homebrew/bin/ffmpeg", "-hide_banner", "-loglevel", "error",
            "-i", str(aiff), "-ar", "16000", "-ac", "1", "-c:a", "libopus",
            "-application", "voip", "-frame_duration", "20", "-f", "ogg", str(ogg),
        ], check=True, capture_output=True)
        packets = ogg_packets(ogg)
        token = jwt_from_backend(args.backend.rstrip("/"))
        transcript, messages = asyncio.run(transcribe(token, packets))
    normalized = transcript.lower()
    ok = ("blue" in normalized and "lantern" in normalized
          and ("42" in normalized or "forty two" in normalized))
    report = {
        "ok": ok,
        "raw_opus_packets": len(packets),
        "final_transcript": transcript,
        "provider_messages": messages,
        "used_short_lived_backend_jwt": True,
        "seconds": round(time.perf_counter() - started, 2),
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, sort_keys=True))
    if not ok:
        raise SystemExit("FAIL: raw Opus did not produce the expected finalized phrase")


if __name__ == "__main__":
    main()
