#!/usr/bin/env python3
"""Probe that MP3 eval sends an absolute transcript path to /eval/run."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path


def _post_json(url: str, payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {"raw": raw}
        return exc.code, data


def main() -> int:
    engine_url = os.environ.get("ANTICIPY_ENGINE_URL", "http://127.0.0.1:8731")
    endpoint = engine_url.rstrip("/") + "/eval/run"

    with tempfile.TemporaryDirectory(prefix="anticipy-mp3-eval-path-") as td:
        transcript_path = (Path(td) / "transcript.txt").resolve()
        transcript_path.write_text(
            "I need to draft a reminder to myself to review the chemistry "
            "lab notes before Friday. This held out transcript path probe "
            "should be read from its absolute filesystem path.",
            encoding="utf-8",
        )
        payload = {
            "transcript_path": str(transcript_path),
            "mode": "eval",
            "dry_run": True,
            "max_windows": 1,
        }
        status, data = _post_json(endpoint, payload)

    blob = json.dumps(data, sort_keys=True)
    if "transcript_path not found" in blob:
        raise AssertionError(f"/eval/run still lost transcript_path: {data}")
    if status != 200 or data.get("ok") is not True:
        raise AssertionError(
            f"/eval/run did not accept absolute transcript path; "
            f"status={status} response={data}"
        )
    if data.get("transcript_path") != str(transcript_path):
        raise AssertionError(
            f"/eval/run did not echo the resolved absolute path; "
            f"expected={transcript_path} response={data}"
        )
    if int(data.get("windows_processed") or 0) < 1:
        raise AssertionError(f"/eval/run did not process a window: {data}")

    print(
        "mp3 eval path probe passed:",
        json.dumps(
            {
                "endpoint": endpoint,
                "transcript_path": str(transcript_path),
                "windows_processed": data.get("windows_processed"),
                "action_count": data.get("action_count"),
            },
            sort_keys=True,
        ),
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"mp3 eval path probe failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
