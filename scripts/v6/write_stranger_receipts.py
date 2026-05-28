#!/usr/bin/env python3
"""Write per-stranger runtime cost and transcript-quality receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


CEILING_PER_TASK_USD = 0.002
HTTP_TIMEOUT_SECONDS = 2.0
TRANSCRIPT_ENDPOINTS = (
    "/api/listen/transcript",
    "/api/listen/state",
    "/api/listen/status",
    "/api/app/state",
)
COST_ENDPOINTS = (
    "/api/runtime/cost",
    "/api/runtime/costs",
    "/api/cost",
    "/api/costs",
    "/api/usage",
    "/api/metrics",
    "/api/listen/state",
    "/api/app/state",
)
COST_KEYS = (
    "cost_usd",
    "total_usd",
    "runtime_cost_usd",
    "estimated_cost_usd",
    "amount_usd",
)
TOKEN_KEYS = (
    "prompt_tokens",
    "completion_tokens",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "tokens",
)
TRANSCRIPT_KEYS = (
    "asr_transcript",
    "final_transcript",
    "transcript",
    "utterance",
    "text",
)
RAW_ASR_TRANSCRIPT_KEYS = (
    "raw_asr_transcript",
)
REFERENCE_TRANSCRIPT_KEYS = (
    "transcript_reference_text",
    "text_reference",
    "spoken_reference_text",
    "utterance",
    "transcript",
    "text",
    "expected_transcript",
    "reference_text",
    "reference_transcript",
)
REFERENCE_ONLY_TRANSCRIPT_MARKERS = (
    "spoken_reference_text",
    "reference_text",
    "reference_transcript",
    "expected_spoken_text",
    "expected_transcript",
)
ASR_TRANSCRIPT_MARKERS = (
    "asr",
    "final_transcript",
    "observed_transcript",
    "transcript_boundary",
    "upload_response",
)
TRANSCRIPT_EVIDENCE_KEYS = (
    "source",
    "origin",
    "actual_input_path",
    "input_mode",
    "source_mode",
    "input_fidelity",
    "kind",
    "reason",
    "status",
    "delivered",
    "audio_delivered",
)
AUDIO_INPUT_FIDELITIES = (
    "audio",
    "audio_upload",
    "live_mic",
    "mic",
    "microphone",
    "mp3",
    "mp3_upload",
    "uploaded_audio",
)
AUDIO_MOMENT_KINDS = (
    "speaks_aloud",
    "audio_upload",
    "mp3_upload",
    "upload_audio",
    "uploads_audio",
)
PASTE_INPUT_FIDELITIES = (
    "paste",
    "transcript_paste",
    "transcript_upload",
    "uploaded_text_transcript",
    "text_transcript_upload",
)
NON_AUDIO_TRANSCRIPT_MARKERS = (
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
)
AUDIO_EVIDENCE_MARKERS = (
    "api listen upload",
    "audio upload",
    "live mic",
    "mic",
    "microphone",
    "speaks aloud",
    "upload asr",
    "uploaded audio",
)
UNDELIVERED_TRANSCRIPT_PATH_MARKERS = (
    "driver_failed_moments",
    "not_delivered",
    "undelivered",
)
FAILED_BEFORE_TRANSCRIPT_STATUSES = (
    "failed_before_live_mic",
    "failed_before_mic",
    "failed_before_microphone",
    "not_delivered",
    "undelivered",
)
ONES_AND_TEENS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
}
TENS = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return None


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compact_path(path: tuple[Any, ...]) -> str:
    out: list[str] = []
    for part in path:
        if isinstance(part, int):
            out.append(f"[{part}]")
        elif out:
            out.append(f".{part}")
        else:
            out.append(str(part))
    return "".join(out) if out else "$"


def value_at_path(data: Any, path: tuple[Any, ...]) -> Any:
    value = data
    for part in path:
        if isinstance(value, dict):
            value = value.get(part)
        elif isinstance(value, list) and isinstance(part, int) and 0 <= part < len(value):
            value = value[part]
        else:
            return None
    return value


def candidate_evidence_metadata(data: Any, path: tuple[Any, ...]) -> dict[str, Any]:
    parent = value_at_path(data, path[:-1])
    if not isinstance(parent, dict):
        return {}
    metadata: dict[str, Any] = {}
    for key in TRANSCRIPT_EVIDENCE_KEYS:
        value = parent.get(key)
        if isinstance(value, bool):
            metadata[key] = value
        elif isinstance(value, (str, int, float)):
            metadata[key] = value
        elif isinstance(value, list) and all(isinstance(item, str) for item in value):
            metadata[key] = value
    return metadata


def normalized_marker_text(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(normalized_marker_text(item) for item in value)
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()


def has_marker(value: Any, markers: tuple[str, ...]) -> bool:
    text = f" {normalized_marker_text(value)} "
    return any(f" {marker} " in text for marker in markers)


def input_fidelity_set(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value.lower()}
    if isinstance(value, list):
        values: set[str] = set()
        for item in value:
            values.update(input_fidelity_set(item))
        return values
    return set()


def transcript_evidence_values(
    origin: str,
    data: Any,
    path: tuple[Any, ...],
    metadata: dict[str, Any] | None = None,
) -> list[Any]:
    values: list[Any] = [origin, compact_path(path)]
    parent = value_at_path(data, path[:-1])
    if isinstance(parent, dict):
        for key in TRANSCRIPT_EVIDENCE_KEYS:
            value = parent.get(key)
            if value is not None:
                values.append(value)
    if metadata:
        values.extend(metadata.values())
    return values


def is_non_audio_transcript_candidate(
    origin: str,
    data: Any,
    path: tuple[Any, ...],
    metadata: dict[str, Any],
) -> bool:
    return any(
        has_marker(value, NON_AUDIO_TRANSCRIPT_MARKERS)
        for value in transcript_evidence_values(origin, data, path, metadata)
    )


def has_audio_transcript_evidence(
    origin: str,
    data: Any,
    path: tuple[Any, ...],
    metadata: dict[str, Any],
    script_has_audio: bool,
) -> bool:
    values = transcript_evidence_values(origin, data, path, metadata)
    if not script_has_audio:
        lowered_path = compact_path(path).lower()
        fidelity = input_fidelity_set(metadata.get("input_fidelity"))
        input_mode = str(metadata.get("input_mode", "")).lower()
        source_mode = str(metadata.get("source_mode", "")).lower()
        if (
            fidelity & set(PASTE_INPUT_FIDELITIES)
            or input_mode in PASTE_INPUT_FIDELITIES
            or source_mode == "transcript_upload"
            or "transcript_boundary" in lowered_path
        ):
            return True
    if input_fidelity_set(metadata.get("input_fidelity")) & set(AUDIO_INPUT_FIDELITIES):
        return True
    kind = str(metadata.get("kind", "")).lower()
    if kind in AUDIO_MOMENT_KINDS:
        return True
    if any(has_marker(value, AUDIO_EVIDENCE_MARKERS) for value in values):
        return True
    lowered_path = compact_path(path).lower()
    return script_has_audio and any(marker in lowered_path for marker in ASR_TRANSCRIPT_MARKERS)


def is_undelivered_transcript_candidate(
    origin: str,
    data: Any,
    path: tuple[Any, ...],
    leaf_key: str,
) -> bool:
    lowered_path = compact_path(path).lower()
    if any(marker in lowered_path for marker in UNDELIVERED_TRANSCRIPT_PATH_MARKERS):
        return True

    parent = value_at_path(data, path[:-1])
    if isinstance(parent, dict):
        status = str(parent.get("status", "")).lower()
        if any(marker in status for marker in FAILED_BEFORE_TRANSCRIPT_STATUSES):
            return True
        if parent.get("delivered") is False or parent.get("audio_delivered") is False:
            return True

    # Driver results can include the scripted utterance. That is only evidence
    # of what should have been said, not proof that the live mic produced ASR.
    if (
        origin == "driver_result.json"
        and leaf_key == "utterance"
        and "asr" not in lowered_path
        and "transcript" not in lowered_path
    ):
        return True

    return False


def fetch_json(base_url: str, endpoint: str) -> Any:
    url = base_url.rstrip("/") + endpoint
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            content_type = response.headers.get("Content-Type", "")
            body = response.read(1_000_000)
    except (OSError, urllib.error.URLError, TimeoutError):
        return None
    if "json" not in content_type and not body.lstrip().startswith((b"{", b"[")):
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def collect_engine_snapshots(engine_url: str | None, endpoints: tuple[str, ...]) -> list[tuple[str, Any]]:
    if not engine_url:
        return []
    snapshots: list[tuple[str, Any]] = []
    for endpoint in endpoints:
        data = fetch_json(engine_url, endpoint)
        if data is not None:
            snapshots.append((f"engine:{endpoint}", data))
    return snapshots


def find_engine_url(args_url: str | None, driver_result: Any) -> str | None:
    if args_url:
        return args_url
    for key in ("ANTICIPY_ENGINE_URL", "ENGINE_URL", "BASE_URL"):
        value = os.environ.get(key)
        if value:
            return value
    for _, value, _ in walk(driver_result):
        if isinstance(value, str) and value.startswith(("http://127.0.0.1:", "http://localhost:")):
            return value
    return None


def walk(data: Any, path: tuple[Any, ...] = ()) -> list[tuple[tuple[Any, ...], Any, str | None]]:
    rows: list[tuple[tuple[Any, ...], Any, str | None]] = []
    if isinstance(data, dict):
        for key, value in data.items():
            rows.extend(walk(value, (*path, key)))
    elif isinstance(data, list):
        for index, value in enumerate(data):
            rows.extend(walk(value, (*path, index)))
    else:
        leaf_key = str(path[-1]).lower() if path else None
        rows.append((path, data, leaf_key))
    return rows


def expected_transcript(script: Any) -> str:
    audio_expected = expected_transcript_from_moments(audio_transcript_moments(script))
    if audio_expected:
        return audio_expected
    return expected_transcript_from_moments(transcript_paste_moments(script))


def expected_transcript_from_moments(
    moments: Any,
    keys: tuple[str, ...] = REFERENCE_TRANSCRIPT_KEYS,
) -> str:
    pieces: list[str] = []
    for moment in moments:
        if not isinstance(moment, dict):
            continue
        for key in keys:
            value = moment.get(key)
            if isinstance(value, str) and value.strip():
                pieces.append(value.strip())
                break
    return " ".join(pieces).strip()


def input_fidelities(script: Any) -> list[str]:
    if not isinstance(script, dict):
        return []
    values: list[str] = []
    for moment in script.get("moments", []):
        if isinstance(moment, dict):
            value = moment.get("input_fidelity")
            if isinstance(value, str) and value not in values:
                values.append(value)
    return values


def is_paste_moment(moment: dict[str, Any]) -> bool:
    kind = str(moment.get("kind", "")).lower()
    fidelity = str(moment.get("input_fidelity", "")).lower()
    return (
        kind in PASTE_INPUT_FIDELITIES
        or fidelity in PASTE_INPUT_FIDELITIES
        or "paste" in kind
        or "paste" in fidelity
    )


def is_audio_moment(moment: dict[str, Any]) -> bool:
    if is_paste_moment(moment):
        return False
    kind = str(moment.get("kind", "")).lower()
    fidelity = str(moment.get("input_fidelity", "")).lower()
    return kind in AUDIO_MOMENT_KINDS or fidelity in AUDIO_INPUT_FIDELITIES


def audio_transcript_moments(script: Any) -> list[dict[str, Any]]:
    if not isinstance(script, dict):
        return []
    moments: list[dict[str, Any]] = []
    for moment in script.get("moments", []):
        if isinstance(moment, dict) and is_audio_moment(moment):
            moments.append(moment)
    return moments


def has_audio_boundary(script: Any) -> bool:
    return bool(audio_transcript_moments(script))


def is_paste_boundary(script: Any) -> bool:
    if not isinstance(script, dict):
        return False
    return bool(transcript_paste_moments(script))


def transcript_paste_moments(script: Any) -> list[dict[str, Any]]:
    if not isinstance(script, dict):
        return []
    moments: list[dict[str, Any]] = []
    for moment in script.get("moments", []):
        if not isinstance(moment, dict):
            continue
        kind = str(moment.get("kind", "")).lower()
        fidelity = str(moment.get("input_fidelity", "")).lower()
        if (
            kind in PASTE_INPUT_FIDELITIES
            or fidelity in PASTE_INPUT_FIDELITIES
            or "paste" in kind
            or "paste" in fidelity
            or kind in {"transcript_upload", "upload_transcript"}
        ):
            moments.append(moment)
    return moments


def words(text: str) -> list[str]:
    return normalize_speech_tokens(re.findall(r"[a-z0-9']+", text.lower()))


def normalize_speech_tokens(tokens: list[str]) -> list[str]:
    normalized: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.isdigit():
            normalized.append(str(int(token)))
            index += 1
            continue
        if token in TENS:
            value = TENS[token]
            if index + 1 < len(tokens) and tokens[index + 1] in ONES_AND_TEENS:
                value += ONES_AND_TEENS[tokens[index + 1]]
                index += 2
            else:
                index += 1
            normalized.append(str(value))
            continue
        if token in ONES_AND_TEENS:
            normalized.append(str(ONES_AND_TEENS[token]))
            index += 1
            continue
        normalized.append(token)
        index += 1
    return normalized


def word_error_rate(reference: str, hypothesis: str) -> float:
    ref = words(reference)
    hyp = words(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    previous = list(range(len(hyp) + 1))
    for i, ref_word in enumerate(ref, start=1):
        current = [i]
        for j, hyp_word in enumerate(hyp, start=1):
            substitution = previous[j - 1] + (0 if ref_word == hyp_word else 1)
            insertion = current[j - 1] + 1
            deletion = previous[j] + 1
            current.append(min(substitution, insertion, deletion))
        previous = current
    return previous[-1] / len(ref)


def transcript_candidates(
    snapshots: list[tuple[str, Any]],
    expected: str,
    script_has_audio: bool,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    expected_words = set(words(expected))
    for origin, data in snapshots:
        for path, value, leaf_key in walk(data):
            if not isinstance(value, str):
                continue
            text = value.strip()
            if not text:
                continue
            key = leaf_key or ""
            lowered_path = compact_path(path).lower()
            if key in RAW_ASR_TRANSCRIPT_KEYS or any(
                marker in lowered_path for marker in RAW_ASR_TRANSCRIPT_KEYS
            ):
                continue
            if not any(name in key or name in lowered_path for name in TRANSCRIPT_KEYS):
                continue
            if any(marker in key or marker in lowered_path for marker in REFERENCE_ONLY_TRANSCRIPT_MARKERS):
                continue
            if is_undelivered_transcript_candidate(origin, data, path, key):
                continue
            metadata = candidate_evidence_metadata(data, path)
            if script_has_audio and is_non_audio_transcript_candidate(origin, data, path, metadata):
                continue
            if not has_audio_transcript_evidence(origin, data, path, metadata, script_has_audio):
                continue
            token_set = set(words(text))
            overlap = len(token_set & expected_words) if expected_words else 0
            key_score = 10 if "transcript" in lowered_path or "asr" in lowered_path else 0
            asr_score = 20 if any(marker in lowered_path for marker in ASR_TRANSCRIPT_MARKERS) else 0
            candidates.append(
                {
                    "text": text,
                    "origin": origin,
                    "path": compact_path(path),
                    "score": asr_score + key_score + overlap,
                    "metadata": metadata,
                }
            )
    return sorted(candidates, key=lambda row: (row["score"], len(row["text"])), reverse=True)


def write_transcript_quality(stranger_dir: Path, script: Any, snapshots: list[tuple[str, Any]]) -> dict[str, Any]:
    expected = expected_transcript(script)
    audio_boundary = has_audio_boundary(script)
    candidates = transcript_candidates(snapshots, expected, audio_boundary) if expected else []
    paste_boundary = is_paste_boundary(script)
    if candidates:
        observed = candidates[0]["text"]
        evidence = {"origin": candidates[0]["origin"], "path": candidates[0]["path"]}
        evidence.update(candidates[0].get("metadata") or {})
        source = str(evidence.get("source") or "asr-transcript").lower()
        if source not in {
            "asr-transcript",
            "live-mic-asr",
            "mic-asr",
            "microphone-asr",
            "upload-asr",
            "transcript-paste",
            "transcript-upload",
        }:
            source = "asr-transcript"
        reason = None
        wer = round(word_error_rate(expected, observed), 6)
    else:
        observed = ""
        if paste_boundary and not audio_boundary:
            source = "transcript-paste"
            reason = "transcript paste is perfect-fidelity input, not delivered audio ASR"
            evidence = {"origin": "script:transcript_paste", "path": "moments", "input_fidelity": "transcript_paste"}
        elif not audio_boundary:
            source = "no-audio-asr-boundary"
            reason = "script has no delivered audio moment to score"
            evidence = {"origin": "script", "path": "moments"}
        elif not expected:
            source = "missing-audio-reference"
            reason = "audio moment has no spoken reference transcript"
            evidence = {"origin": "script", "path": "moments"}
        else:
            source = "audio-asr-missing"
            reason = "no delivered audio ASR transcript boundary found"
            evidence = {"origin": "missing", "path": None}

    receipt = {
        "schema": "anticipy.v6.transcript_quality",
        "stranger_id": stranger_dir.name,
        "generated_at": utc_now(),
        "source": source,
        "evidence": evidence,
        "input_fidelity": input_fidelities(script),
        "reference": expected,
        "hypothesis": observed,
        "transcript_boundary_sha256": text_hash(observed),
        "transcript_boundary_chars": len(observed),
    }
    if reason is None:
        receipt["wer"] = wer
    else:
        receipt["reason"] = reason
        receipt["wer"] = None
    write_json(stranger_dir / "transcript_quality.json", receipt)
    return receipt


def cost_value(data: dict[str, Any]) -> float | None:
    for key in COST_KEYS:
        value = as_number(data.get(key))
        if value is not None:
            return value
    return None


def looks_like_call(data: dict[str, Any], path: tuple[Any, ...]) -> bool:
    lowered_path = compact_path(path).lower()
    if "call" in lowered_path or "request" in lowered_path or "usage" in lowered_path:
        return True
    if any(key in data for key in ("model", "provider", "endpoint")):
        return True
    if any(key in data for key in TOKEN_KEYS):
        return True
    return False


def collect_cost_calls(data: Any, origin: str, path: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    if isinstance(data, dict):
        cost = cost_value(data)
        if cost is not None and looks_like_call(data, path):
            call: dict[str, Any] = {
                "cost_usd": round(cost, 10),
                "origin": origin,
                "path": compact_path(path),
            }
            for key in ("model", "provider", "endpoint", *TOKEN_KEYS):
                value = data.get(key)
                if isinstance(value, (str, int, float)) and not isinstance(value, bool):
                    call[key] = value
            calls.append(call)
        for key, value in data.items():
            calls.extend(collect_cost_calls(value, origin, (*path, key)))
    elif isinstance(data, list):
        for index, value in enumerate(data):
            calls.extend(collect_cost_calls(value, origin, (*path, index)))
    return calls


def collect_totals(data: Any, origin: str, path: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    totals: list[dict[str, Any]] = []
    if isinstance(data, dict):
        cost = cost_value(data)
        if cost is not None and not looks_like_call(data, path):
            totals.append({"cost_usd": float(cost), "origin": origin, "path": compact_path(path)})
        for key, value in data.items():
            totals.extend(collect_totals(value, origin, (*path, key)))
    elif isinstance(data, list):
        for index, value in enumerate(data):
            totals.extend(collect_totals(value, origin, (*path, index)))
    return totals


def parse_jsonish_file(path: Path) -> list[Any]:
    try:
        if path.stat().st_size > 2_000_000:
            return []
    except OSError:
        return []
    if path.suffix == ".jsonl":
        rows: list[Any] = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        except OSError:
            return []
        return rows
    if path.suffix == ".json":
        data = read_json(path)
        return [] if data is None else [data]
    return []


def runtime_data_snapshots() -> list[tuple[str, Any]]:
    data_dir = os.environ.get("ANTICIPY_DATA_DIR")
    if not data_dir:
        return []
    root = Path(data_dir)
    if not root.exists():
        return []
    snapshots: list[tuple[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in {".json", ".jsonl"}:
            continue
        lowered = path.name.lower()
        if not any(token in lowered for token in ("cost", "usage", "ledger", "llm", "token", "metric")):
            continue
        for index, data in enumerate(parse_jsonish_file(path)):
            suffix = f":{index}" if path.suffix == ".jsonl" else ""
            snapshots.append((f"data:{path.relative_to(root)}{suffix}", data))
    return snapshots


def dedupe_calls(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for call in calls:
        fingerprint = json.dumps(call, sort_keys=True)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        unique.append(call)
    return unique


def write_cost_breakdown(
    stranger_dir: Path,
    transcript_receipt: dict[str, Any],
    snapshots: list[tuple[str, Any]],
) -> dict[str, Any]:
    calls: list[dict[str, Any]] = []
    totals: list[dict[str, Any]] = []
    for origin, data in snapshots:
        calls.extend(collect_cost_calls(data, origin))
        totals.extend(collect_totals(data, origin))
    calls = dedupe_calls(calls)
    if calls:
        total = sum(float(call.get("cost_usd") or 0.0) for call in calls)
        source = "runtime-call-ledger"
    elif totals:
        total = max(total_row["cost_usd"] for total_row in totals)
        source = "runtime-total-ledger"
    else:
        total = 0.0
        source = "runtime-ledger-no-llm-calls"

    receipt = {
        "schema": "anticipy.v6.cost_breakdown",
        "stranger_id": stranger_dir.name,
        "generated_at": utc_now(),
        "source": source,
        "total_usd": round(total, 10),
        "ceiling_per_task_usd": CEILING_PER_TASK_USD,
        "within_ceiling": total <= CEILING_PER_TASK_USD,
        "calls": calls,
        "totals": totals,
        "transcript_boundary_sha256": transcript_receipt["transcript_boundary_sha256"],
    }
    write_json(stranger_dir / "cost_breakdown.json", receipt)
    return receipt


def write_fallback_driver_result(
    stranger_dir: Path,
    exit_code: int | None,
    persona_file: str | None,
    script_file: str | None,
) -> dict[str, Any] | None:
    if exit_code is None or exit_code == 0:
        return None
    if read_json(stranger_dir / "driver_result.json") is not None:
        return None

    result: dict[str, Any] = {
        "schema": "anticipy.v6.driver_result",
        "stranger_id": stranger_dir.name,
        "generated_at": utc_now(),
        "ok": False,
        "driver_failed": True,
        "driver_exit_code": exit_code,
        "failure_phase": "stranger-driver-dispatch",
        "evidence": {
            "origin": "scripts/v6/dispatch_stranger_driver.sh",
            "reason": "driver exited before writing driver_result.json",
        },
    }
    if persona_file:
        result["persona_file"] = persona_file
    if script_file:
        result["script_file"] = script_file
    write_json(stranger_dir / "driver_result.json", result)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stranger-dir", required=True, type=Path)
    parser.add_argument("--engine-url")
    parser.add_argument("--driver-exit-code", type=int)
    parser.add_argument("--persona-file")
    parser.add_argument("--script-file")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    stranger_dir = args.stranger_dir
    write_fallback_driver_result(
        stranger_dir,
        args.driver_exit_code,
        args.persona_file,
        args.script_file,
    )
    script = read_json(stranger_dir / "script.json")
    if script is None and args.script_file:
        script = read_json(Path(args.script_file))
    driver_result = read_json(stranger_dir / "driver_result.json")
    engine_url = find_engine_url(args.engine_url, driver_result)

    transcript_snapshots: list[tuple[str, Any]] = []
    if driver_result is not None:
        transcript_snapshots.append(("driver_result.json", driver_result))
    transcript_snapshots.extend(collect_engine_snapshots(engine_url, TRANSCRIPT_ENDPOINTS))
    transcript_receipt = write_transcript_quality(stranger_dir, script, transcript_snapshots)

    cost_snapshots: list[tuple[str, Any]] = []
    if driver_result is not None:
        cost_snapshots.append(("driver_result.json", driver_result))
    cost_snapshots.extend(runtime_data_snapshots())
    cost_snapshots.extend(collect_engine_snapshots(engine_url, COST_ENDPOINTS))
    write_cost_breakdown(stranger_dir, transcript_receipt, cost_snapshots)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
