"""Local audio transcription for realday ingestion.

This module is deliberately generic. It knows nothing about the owner, the eval
person, their apps, or any student-specific vocabulary. It only turns an audio
file into timestamped text lines using local ffmpeg plus an on-device Whisper
model.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Iterable, List, Sequence, Tuple


AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".aac", ".flac", ".ogg"}


@dataclass(frozen=True)
class AudioTranscript:
    lines: List[str]
    metadata: dict


def is_audio_file(path: Path) -> bool:
    return path.suffix.lower() in AUDIO_EXTENSIONS


def transcribe_audio(path: Path) -> AudioTranscript:
    """Transcribe one local audio file into timestamped text lines."""
    path = path.expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    if not is_audio_file(path):
        raise ValueError(f"not an audio file: {path}")

    sidecar = path.with_suffix(".transcript")
    cached = _read_cached_transcript(sidecar)
    if cached is not None:
        return AudioTranscript(
            lines=cached,
            metadata={
                "audio_path": str(path),
                "transcript_path": str(sidecar),
                "transcriber": "cached_sidecar",
                "cached": True,
                "segments_kept": len(cached),
            },
        )

    duration = _probe_duration(path)
    silence = _detect_silence(path)
    speech = _speech_intervals(duration, silence)
    speech = _pad_and_merge(
        speech,
        duration=duration,
        pad=float(os.environ.get("ANTICIPY_AUDIO_PAD_SECONDS", "0.5")),
        merge_gap=float(os.environ.get("ANTICIPY_AUDIO_MERGE_GAP_SECONDS", "0.8")),
        min_seconds=float(os.environ.get("ANTICIPY_AUDIO_MIN_SPEECH_SECONDS", "0.8")),
    )
    chunks = _split_intervals(
        speech,
        max_seconds=float(os.environ.get("ANTICIPY_AUDIO_CHUNK_SECONDS", "30")),
        overlap=float(os.environ.get("ANTICIPY_AUDIO_CHUNK_OVERLAP_SECONDS", "0.5")),
    )
    chunks = _cap_chunks(
        chunks,
        max_total_seconds=float(os.environ.get("ANTICIPY_REALDAY_AUDIO_MAX_SECONDS", "0") or "0"),
    )

    lines: List[str] = []
    segment_count = 0
    model_name = os.environ.get("ANTICIPY_WHISPER_MODEL", "tiny.en")
    model = _load_whisper_model(model_name)

    with tempfile.TemporaryDirectory(prefix="anticipy-audio-") as tmp:
        for idx, (start, end) in enumerate(chunks, start=1):
            wav = Path(tmp) / f"chunk-{idx:05d}.wav"
            _extract_wav(path, wav, start, end)
            result = model.transcribe(
                str(wav),
                fp16=False,
                verbose=False,
                condition_on_previous_text=False,
                language="en",
                temperature=0.0,
            )
            for seg in result.get("segments", []):
                if _drop_segment(seg):
                    continue
                text = _clean_text(str(seg.get("text", "")))
                if not text:
                    continue
                seg_start = start + float(seg.get("start", 0.0) or 0.0)
                seg_end = start + float(seg.get("end", 0.0) or 0.0)
                lines.append(f"[{_stamp(seg_start)}-{_stamp(seg_end)}] {text}")
                segment_count += 1

    transcript = AudioTranscript(
        lines=lines,
        metadata={
            "audio_path": str(path),
            "transcript_path": str(sidecar),
            "duration_seconds": round(duration, 3),
            "speech_intervals": len(speech),
            "chunks": len(chunks),
            "segments_kept": segment_count,
            "model": model_name,
            "transcriber": "local_whisper",
            "cached": False,
            "max_audio_seconds": float(os.environ.get("ANTICIPY_REALDAY_AUDIO_MAX_SECONDS", "0") or "0"),
        },
    )
    _write_cached_transcript(sidecar, transcript.lines)
    return transcript


def _read_cached_transcript(path: Path) -> List[str] | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    return [line.strip() for line in text.splitlines() if line.strip()]


def _write_cached_transcript(path: Path, lines: Sequence[str]) -> None:
    path.write_text("\n".join(lines).rstrip() + ("\n" if lines else ""), encoding="utf-8")


def _load_whisper_model(name: str):
    import whisper

    return whisper.load_model(name)


def _probe_duration(path: Path) -> float:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(proc.stdout.strip())


def _detect_silence(path: Path) -> List[Tuple[float, float]]:
    noise = os.environ.get("ANTICIPY_AUDIO_SILENCE_NOISE", "-35dB")
    min_silence = os.environ.get("ANTICIPY_AUDIO_MIN_SILENCE_SECONDS", "1")
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-af",
            f"silencedetect=noise={noise}:d={min_silence}",
            "-f",
            "null",
            "-",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    starts: List[float] = []
    intervals: List[Tuple[float, float]] = []
    for line in proc.stderr.splitlines():
        m_start = re.search(r"silence_start:\s*([0-9.]+)", line)
        if m_start:
            starts.append(float(m_start.group(1)))
            continue
        m_end = re.search(r"silence_end:\s*([0-9.]+)", line)
        if m_end and starts:
            intervals.append((starts.pop(0), float(m_end.group(1))))
    return intervals


def _speech_intervals(duration: float, silence: Sequence[Tuple[float, float]]) -> List[Tuple[float, float]]:
    if duration <= 0:
        return []
    out: List[Tuple[float, float]] = []
    pos = 0.0
    for start, end in sorted(silence):
        start = max(0.0, min(duration, start))
        end = max(start, min(duration, end))
        if start > pos:
            out.append((pos, start))
        pos = max(pos, end)
    if pos < duration:
        out.append((pos, duration))
    return out


def _pad_and_merge(
    intervals: Iterable[Tuple[float, float]],
    *,
    duration: float,
    pad: float,
    merge_gap: float,
    min_seconds: float,
) -> List[Tuple[float, float]]:
    padded = [
        (max(0.0, start - pad), min(duration, end + pad))
        for start, end in intervals
        if end - start >= min_seconds
    ]
    if not padded:
        return []
    merged: List[Tuple[float, float]] = []
    cur_start, cur_end = padded[0]
    for start, end in padded[1:]:
        if start <= cur_end + merge_gap:
            cur_end = max(cur_end, end)
        else:
            merged.append((cur_start, cur_end))
            cur_start, cur_end = start, end
    merged.append((cur_start, cur_end))
    return merged


def _split_intervals(
    intervals: Iterable[Tuple[float, float]],
    *,
    max_seconds: float,
    overlap: float,
) -> List[Tuple[float, float]]:
    out: List[Tuple[float, float]] = []
    max_seconds = max(5.0, max_seconds)
    overlap = max(0.0, min(overlap, max_seconds / 4))
    for start, end in intervals:
        cursor = start
        while cursor < end:
            chunk_end = min(end, cursor + max_seconds)
            if chunk_end - cursor >= 1.0:
                out.append((cursor, chunk_end))
            if chunk_end >= end:
                break
            cursor = max(cursor + 1.0, chunk_end - overlap)
    return out


def _cap_chunks(chunks: Sequence[Tuple[float, float]], *, max_total_seconds: float) -> List[Tuple[float, float]]:
    if max_total_seconds <= 0:
        return list(chunks)
    kept: List[Tuple[float, float]] = []
    total = 0.0
    for start, end in chunks:
        remaining = max_total_seconds - total
        if remaining <= 0:
            break
        if end - start > remaining:
            end = start + remaining
        kept.append((start, end))
        total += max(0.0, end - start)
    return kept


def _extract_wav(src: Path, dest: Path, start: float, end: float) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{max(0.1, end - start):.3f}",
            "-i",
            str(src),
            "-ar",
            "16000",
            "-ac",
            "1",
            str(dest),
        ],
        check=True,
    )


def _drop_segment(seg: dict) -> bool:
    text = _clean_text(str(seg.get("text", "")))
    if not text:
        return True
    no_speech = float(seg.get("no_speech_prob", 0.0) or 0.0)
    avg_logprob = float(seg.get("avg_logprob", 0.0) or 0.0)
    compression = float(seg.get("compression_ratio", 0.0) or 0.0)
    if no_speech >= 0.85:
        return True
    if avg_logprob <= -1.25:
        return True
    if compression >= 2.8:
        return True
    return _looks_repetitive(text)


def _looks_repetitive(text: str) -> bool:
    words = re.findall(r"[a-zA-Z']+", text.lower())
    if len(words) < 16:
        return False
    unique_ratio = len(set(words)) / max(1, len(words))
    return unique_ratio < 0.22


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _stamp(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"
