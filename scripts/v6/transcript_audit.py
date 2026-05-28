#!/usr/bin/env python3
"""Audit V6 transcript quality receipts."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any
from uuid import UUID


STATE = Path("state")
WER_CEILING = 0.05
AUDIO_INPUT_FIDELITIES = {
    "audio",
    "audio_upload",
    "live_mic",
    "mic",
    "microphone",
    "mp3",
    "mp3_upload",
    "uploaded_audio",
}
AUDIO_MOMENT_KINDS = {
    "speaks_aloud",
    "audio_upload",
    "mp3_upload",
    "upload_audio",
    "uploads_audio",
}
PASTE_INPUT_FIDELITIES = {"paste", "transcript_paste"}
WER_RECEIPT_SOURCES = {
    "asr-transcript",
    "live-mic-asr",
    "mic-asr",
    "microphone-asr",
    "upload-asr",
}
TRANSCRIPT_TEXT_KEYS = {
    "asr_transcript",
    "final_transcript",
    "hypothesis",
    "text",
    "transcript",
}
REFERENCE_TEXT_KEYS = {
    "expected_transcript",
    "reference",
    "reference_text",
    "reference_transcript",
    "spoken_reference_text",
}
TRANSCRIPT_EVIDENCE_KEYS = {
    "actual_input_path",
    "input_fidelity",
    "kind",
    "origin",
    "path",
    "reason",
    "source",
    "status",
}
NON_AUDIO_EVIDENCE_MARKERS = {
    "audio not delivered",
    "driver failed moments",
    "failed before live mic",
    "failed before mic",
    "failed before microphone",
    "injected",
    "injection",
    "inject",
    "microphone permission",
    "missing reference",
    "no reference",
    "not delivered",
    "paste",
    "permission denied",
    "permission timeout",
    "post asr",
    "post asr inject",
    "transcript paste",
    "undelivered",
    "utterance not delivered",
}
AUDIO_EVIDENCE_MARKERS = {
    "api listen upload",
    "audio upload",
    "live mic",
    "mic",
    "microphone",
    "speaks aloud",
    "upload asr",
    "uploaded audio",
}


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def extract_wer(data: Any) -> float | None:
    if not isinstance(data, dict):
        return None
    if str(data.get("source", "")).lower() not in WER_RECEIPT_SOURCES:
        return None
    value = data.get("wer")
    if isinstance(value, (int, float)):
        return float(value)
    quality = data.get("transcript_quality")
    if isinstance(quality, dict) and isinstance(quality.get("wer"), (int, float)):
        return float(quality["wer"])
    return None


def input_fidelities(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value.lower()}
    if isinstance(value, list):
        values: set[str] = set()
        for item in value:
            values.update(input_fidelities(item))
        return values
    return set()


def normalized_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()


def has_marker(value: Any, markers: set[str]) -> bool:
    text = f" {normalized_text(value)} "
    return any(f" {marker} " in text for marker in markers)


def evidence_values(records: list[dict[str, Any]]) -> list[Any]:
    values: list[Any] = []
    for record in records:
        for key in TRANSCRIPT_EVIDENCE_KEYS:
            value = record.get(key)
            if isinstance(value, list):
                values.extend(value)
            elif value is not None:
                values.append(value)
    return values


def has_observed_transcript(receipt: Any) -> bool:
    if not isinstance(receipt, dict):
        return False
    chars = receipt.get("transcript_boundary_chars")
    if isinstance(chars, int):
        return chars > 0
    if isinstance(chars, float):
        return chars > 0
    for key in TRANSCRIPT_TEXT_KEYS:
        value = receipt.get(key)
        if isinstance(value, str) and value.strip():
            return True
    return False


def has_reference_transcript(receipt: Any) -> bool:
    if not isinstance(receipt, dict):
        return False
    for key in REFERENCE_TEXT_KEYS:
        value = receipt.get(key)
        if isinstance(value, str) and value.strip():
            return True
    quality = receipt.get("transcript_quality")
    if isinstance(quality, dict):
        return has_reference_transcript(quality)
    return False


def transcript_boundary_records(receipt: Any, driver_result: Any) -> list[dict[str, Any]]:
    receipt_evidence = receipt.get("evidence") if isinstance(receipt, dict) else None
    if isinstance(receipt_evidence, dict) and any(key in receipt_evidence for key in TRANSCRIPT_EVIDENCE_KEYS):
        return [receipt_evidence]

    if not isinstance(driver_result, dict):
        return []

    boundary = driver_result.get("transcript_boundary")
    if isinstance(boundary, dict):
        return [boundary]

    records: list[dict[str, Any]] = []
    for moment in driver_result.get("moments", []):
        if not isinstance(moment, dict):
            continue
        if any(key in moment for key in TRANSCRIPT_TEXT_KEYS | TRANSCRIPT_EVIDENCE_KEYS):
            records.append(moment)
    return records


def has_non_audio_transcript_evidence(records: list[dict[str, Any]]) -> bool:
    return any(has_marker(value, NON_AUDIO_EVIDENCE_MARKERS) for value in evidence_values(records))


def has_audio_transcript_evidence(records: list[dict[str, Any]]) -> bool:
    values = evidence_values(records)
    if any(has_marker(value, AUDIO_EVIDENCE_MARKERS) for value in values):
        return True
    return bool(input_fidelities(values) & AUDIO_INPUT_FIDELITIES)


def moment_input_fidelities(script: Any) -> set[str]:
    if not isinstance(script, dict):
        return set()
    fidelities: set[str] = set()
    for moment in script.get("moments", []):
        if not isinstance(moment, dict):
            continue
        fidelities.update(input_fidelities(moment.get("input_fidelity")))
        kind = moment.get("kind")
        if isinstance(kind, str) and kind in AUDIO_MOMENT_KINDS:
            fidelities.add(kind)
        if kind == "transcript_paste":
            fidelities.add("paste")
    return fidelities


def is_generated_stranger_dir(path: Path) -> bool:
    try:
        UUID(path.name)
    except ValueError:
        return False

    persona = read_json(path / "persona.json")
    script = read_json(path / "script.json")
    verdict = read_json(path / "verdict.json")
    if not isinstance(persona, dict) or not isinstance(script, dict) or not isinstance(verdict, dict):
        return False
    if persona.get("uuid") not in (None, path.name):
        return False
    if script.get("persona_uuid") not in (None, path.name):
        return False
    return True


def is_audio_asr_receipt(receipt: Any, script: Any, driver_result: Any) -> bool:
    if extract_wer(receipt) is None:
        return False
    if not has_observed_transcript(receipt):
        return False
    if not has_reference_transcript(receipt):
        return False
    receipt_fidelities = input_fidelities(receipt.get("input_fidelity")) if isinstance(receipt, dict) else set()
    if receipt_fidelities & PASTE_INPUT_FIDELITIES:
        return False

    boundary_records = transcript_boundary_records(receipt, driver_result)
    if has_non_audio_transcript_evidence(boundary_records):
        return False
    if has_audio_transcript_evidence(boundary_records):
        return True

    if receipt_fidelities:
        return bool(receipt_fidelities & AUDIO_INPUT_FIDELITIES)

    script_fidelities = moment_input_fidelities(script)
    if script_fidelities and script_fidelities <= PASTE_INPUT_FIDELITIES:
        return False
    return bool(script_fidelities & (AUDIO_INPUT_FIDELITIES | AUDIO_MOMENT_KINDS))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit V6 transcript quality receipts.")
    parser.add_argument("--state-dir", type=Path, default=STATE)
    return parser.parse_args()


def main() -> int:
    state = parse_args().state_dir
    receipt_paths = []
    for path in sorted((state / "strangers").glob("*/transcript_quality.json"), key=lambda p: p.stat().st_mtime):
        stranger_dir = path.parent
        if not is_generated_stranger_dir(stranger_dir):
            continue
        receipt = read_json(path)
        script = read_json(stranger_dir / "script.json")
        driver_result = read_json(stranger_dir / "driver_result.json")
        if is_audio_asr_receipt(receipt, script, driver_result):
            receipt_paths.append(path)
    wers = [extract_wer(read_json(path)) for path in receipt_paths[-20:]]
    wers = [wer for wer in wers if wer is not None]
    if not wers:
        result = {
            "verdict": "no_data",
            "reason": "no generated-stranger audio ASR transcript_quality.json files with WER",
            "wer_ceiling": WER_CEILING,
        }
        code = 2
    else:
        avg = sum(wers) / len(wers)
        result = {
            "verdict": "pass" if avg <= WER_CEILING else "fail",
            "sample_count": len(wers),
            "average_wer": round(avg, 6),
            "wer_ceiling": WER_CEILING,
        }
        code = 0 if result["verdict"] == "pass" else 1
    state.mkdir(exist_ok=True)
    (state / "last_v6_transcript_audit.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
