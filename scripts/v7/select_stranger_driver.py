#!/usr/bin/env python3
"""Select and run the strongest available V7 stranger driver.

The generated-stranger gate still supports the prompt-driven driver for
unsupported surfaces, but the common public-product input modes have
deterministic drivers. This selector keeps those runs cheap and repeatable
without pretending that unsupported scripts were covered.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable


DRIVERS = {
    "uploaded_audio": "scripts/v7/drive_audio_upload_ui.py",
    "transcript_paste": "scripts/v7/drive_transcript_paste_ui.py",
    "computer_microphone": "scripts/v7/drive_computer_mic_ui.py",
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def iter_objects(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from iter_objects(item)
    elif isinstance(value, list):
        for item in value:
            yield from iter_objects(item)


def normalized_fidelities(moment: dict[str, Any]) -> set[str]:
    value = moment.get("input_fidelity")
    if isinstance(value, str):
        return {value.lower()}
    if isinstance(value, list):
        return {str(item).lower() for item in value}
    return set()


def classify(script: Any) -> tuple[str | None, str]:
    moments = list(iter_objects(script))

    for moment in moments:
        kind = str(moment.get("kind") or "").lower()
        fidelities = normalized_fidelities(moment)
        if kind in {"upload_audio", "audio_upload", "mp3_upload", "uploads_audio"}:
            return "uploaded_audio", f"matched moment kind {kind}"
        if fidelities & {"uploaded_audio", "audio_upload", "mp3_upload"}:
            return "uploaded_audio", "matched uploaded-audio input_fidelity"

    for moment in moments:
        kind = str(moment.get("kind") or "").lower()
        fidelities = normalized_fidelities(moment)
        if kind in {
            "transcript_paste",
            "transcript_upload",
            "upload_transcript",
            "text_transcript_upload",
        }:
            return "transcript_paste", f"matched transcript kind {kind}"
        if fidelities & {"transcript_paste", "transcript_upload", "uploaded_text_transcript"}:
            return "transcript_paste", "matched transcript input_fidelity"

    for moment in moments:
        kind = str(moment.get("kind") or "").lower()
        fidelities = normalized_fidelities(moment)
        if kind == "speaks_aloud" and "computer_microphone" in fidelities:
            return "computer_microphone", "matched speaks_aloud computer_microphone"

    return None, "no deterministic V7 driver supports this script"


def truncate(text: str, limit: int = 16000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[truncated {len(text) - limit} chars]"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stranger-dir", required=True, type=Path)
    parser.add_argument("--persona-file", required=True, type=Path)
    parser.add_argument("--script-file", required=True, type=Path)
    parser.add_argument("--engine-url", default="http://127.0.0.1:8731")
    parser.add_argument("--public-url", default="https://www.anticipy.ai/app")
    args = parser.parse_args()

    script = load_json(args.script_file)
    mode, reason = classify(script)
    selector_path = args.stranger_dir / "driver_selector.json"

    if not mode:
        write_json(
            selector_path,
            {
                "schema": "anticipy.v7.stranger_driver_selector",
                "supported": False,
                "selected_mode": None,
                "reason": reason,
            },
        )
        print(json.dumps({"supported": False, "reason": reason}, sort_keys=True))
        return 2

    driver = DRIVERS[mode]
    command = [
        sys.executable,
        driver,
        "--stranger-dir",
        str(args.stranger_dir),
        "--persona-file",
        str(args.persona_file),
        "--script-file",
        str(args.script_file),
        "--engine-url",
        args.engine_url,
        "--public-url",
        args.public_url,
    ]
    proc = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    write_json(
        selector_path,
        {
            "schema": "anticipy.v7.stranger_driver_selector",
            "supported": True,
            "selected_mode": mode,
            "reason": reason,
            "driver": driver,
            "command": command,
            "exit_code": proc.returncode,
            "stdout": truncate(proc.stdout),
            "stderr": truncate(proc.stderr),
        },
    )
    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
