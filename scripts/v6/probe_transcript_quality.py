#!/usr/bin/env python3
"""Probe transcript-quality accounting for delivered audio ASR only."""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
WRITER = ROOT / "scripts" / "v6" / "write_stranger_receipts.py"
AUDIT = ROOT / "scripts" / "v6" / "transcript_audit.py"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_python(*args: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *(str(arg) for arg in args)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )


def writer_module() -> Any:
    spec = importlib.util.spec_from_file_location("write_stranger_receipts_probe", WRITER)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load write_stranger_receipts.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_stranger(
    state: Path,
    index: int,
    moments: list[dict[str, Any]],
    driver_result: dict[str, Any] | None = None,
    receipt: dict[str, Any] | None = None,
) -> Path:
    stranger_id = f"00000000-0000-4000-8000-{index:012d}"
    stranger_dir = state / "strangers" / stranger_id
    write_json(stranger_dir / "persona.json", {"uuid": stranger_id, "occupation": "Probe"})
    write_json(stranger_dir / "script.json", {"persona_uuid": stranger_id, "moments": moments})
    write_json(stranger_dir / "verdict.json", {"verdict": "pass"})
    if driver_result is not None:
        write_json(stranger_dir / "driver_result.json", driver_result)
    if receipt is not None:
        write_json(stranger_dir / "transcript_quality.json", receipt)
    return stranger_dir


def write_receipts(stranger_dir: Path) -> dict[str, Any]:
    run_python(WRITER, "--stranger-dir", stranger_dir)
    return read_json(stranger_dir / "transcript_quality.json")


def assert_unscored(receipt: dict[str, Any], label: str) -> None:
    if receipt.get("source") == "asr-transcript":
        raise AssertionError(f"{label} was written as an ASR transcript receipt")
    if receipt.get("wer") is not None:
        raise AssertionError(f"{label} has numeric WER: {receipt.get('wer')!r}")


def legacy_receipt(
    stranger_id: str,
    *,
    reference: str,
    hypothesis: str,
    evidence: dict[str, Any],
    input_fidelity: list[str] | str = "live_mic",
    wer: float = 1.0,
) -> dict[str, Any]:
    return {
        "schema": "anticipy.v6.transcript_quality",
        "stranger_id": stranger_id,
        "source": "asr-transcript",
        "evidence": evidence,
        "input_fidelity": input_fidelity,
        "reference": reference,
        "hypothesis": hypothesis,
        "wer": wer,
        "transcript_boundary_chars": len(hypothesis),
        "transcript_boundary_sha256": "probe",
    }


def run_delivered_audio_only() -> None:
    module = writer_module()
    if module.word_error_rate("Ask Priya Rao about Kubernetes", "Ask Priya Roy about Cubernets") <= 0:
        raise AssertionError("proper-name and jargon misses were hidden by normalization")

    with tempfile.TemporaryDirectory(prefix="anticipy-transcript-quality-") as tmp:
        state = Path(tmp)

        valid = make_stranger(
            state,
            1,
            [
                {
                    "kind": "speaks_aloud",
                    "input_fidelity": "live_mic",
                    "spoken_reference_text": "Send Priya Rao the 2 revised Kubernetes figures.",
                }
            ],
            {
                "transcript_boundary": {
                    "source": "live-mic-asr",
                    "kind": "speaks_aloud",
                    "input_fidelity": "live_mic",
                    "status": "delivered",
                    "text": "Send Priya Rao the two revised Kubernetes figures.",
                }
            },
        )
        valid_receipt = write_receipts(valid)
        if valid_receipt.get("source") != "asr-transcript":
            raise AssertionError(f"delivered audio was not scored: {valid_receipt}")
        if valid_receipt.get("wer") != 0.0:
            raise AssertionError(f"number-word normalization failed: {valid_receipt}")

        paste = make_stranger(
            state,
            2,
            [
                {
                    "kind": "transcript_paste",
                    "input_fidelity": "transcript_paste",
                    "spoken_reference_text": "This exact text was pasted.",
                }
            ],
            {
                "transcript_boundary": {
                    "source": "post_asr_inject",
                    "input_fidelity": "transcript_paste",
                    "text": "This exact text was pasted.",
                }
            },
        )
        assert_unscored(write_receipts(paste), "transcript paste")

        permission_timeout = make_stranger(
            state,
            3,
            [
                {
                    "kind": "speaks_aloud",
                    "input_fidelity": "live_mic",
                    "spoken_reference_text": "Tell Priya the microphone test is ready.",
                }
            ],
            {
                "moments": [
                    {
                        "kind": "speaks_aloud",
                        "input_fidelity": "live_mic",
                        "status": "permission_timeout",
                        "text": "Microphone permission timeout.",
                    }
                ]
            },
        )
        assert_unscored(write_receipts(permission_timeout), "permission-timeout UI text")

        undelivered = make_stranger(
            state,
            4,
            [
                {
                    "kind": "speaks_aloud",
                    "input_fidelity": "live_mic",
                    "spoken_reference_text": "Ask Priya to review the Q3 forecast.",
                }
            ],
            {
                "moments": [
                    {
                        "kind": "speaks_aloud",
                        "input_fidelity": "live_mic",
                        "status": "failed_before_live_mic",
                        "utterance": "Ask Priya to review the Q3 forecast.",
                    }
                ]
            },
        )
        assert_unscored(write_receipts(undelivered), "undelivered mic attempt")

        missing_reference = make_stranger(
            state,
            5,
            [{"kind": "speaks_aloud", "input_fidelity": "live_mic"}],
            {
                "transcript_boundary": {
                    "source": "live-mic-asr",
                    "kind": "speaks_aloud",
                    "input_fidelity": "live_mic",
                    "status": "delivered",
                    "text": "This has no reference.",
                }
            },
        )
        assert_unscored(write_receipts(missing_reference), "missing reference")

        bad_cases = [
            (
                6,
                "permission-timeout legacy receipt",
                "Tell Priya the microphone test is ready.",
                "Microphone permission timeout.",
                {"source": "live-mic-asr", "status": "permission_timeout", "reason": "microphone permission timeout"},
                "live_mic",
            ),
            (
                7,
                "paste legacy receipt",
                "This exact text was pasted.",
                "This exact text was pasted.",
                {"source": "post_asr_inject", "input_fidelity": "transcript_paste"},
                "transcript_paste",
            ),
            (
                8,
                "missing-reference legacy receipt",
                "",
                "This has no reference.",
                {"source": "live-mic-asr", "input_fidelity": "live_mic", "status": "delivered"},
                "live_mic",
            ),
            (
                9,
                "undelivered legacy receipt",
                "Ask Priya to review the Q3 forecast.",
                "Ask Priya to review the Q3 forecast.",
                {"source": "live-mic-asr", "status": "failed_before_live_mic"},
                "live_mic",
            ),
        ]
        for index, _label, reference, hypothesis, evidence, fidelity in bad_cases:
            stranger = make_stranger(
                state,
                index,
                [{"kind": "speaks_aloud", "input_fidelity": "live_mic", "spoken_reference_text": reference}],
            )
            write_json(
                stranger / "transcript_quality.json",
                legacy_receipt(stranger.name, reference=reference, hypothesis=hypothesis, evidence=evidence, input_fidelity=fidelity),
            )

        audit = run_python(AUDIT, "--state-dir", state)
        result = json.loads(audit.stdout)
        if result.get("verdict") != "pass":
            raise AssertionError(f"transcript audit failed: {result}")
        if result.get("sample_count") != 1:
            raise AssertionError(f"audit counted non-audio ASR receipts: {result}")
        if result.get("average_wer") != 0.0:
            raise AssertionError(f"audit average includes non-delivered boundaries: {result}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=["delivered-audio-only"], required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.case == "delivered-audio-only":
        run_delivered_audio_only()
    print(json.dumps({"case": args.case, "verdict": "pass"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
