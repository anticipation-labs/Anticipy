"""
Verifier base helpers. Every verifier script imports from here.

Provides:
- VerifierBase: a class verifier scripts inherit from. Handles argparse,
  evidence dir, result.json writing, screenshot helpers.
- vision_assert(): send a screenshot to OpenRouter vision LLM with a YES/NO question.
- run_or_fail(): run a subprocess, capture output to evidence/logs/, fail loudly.

Frozen path: verifier/lib/base.py. Builders cannot edit this file.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import requests  # standard, installed in engine venv


@dataclass
class VerifierResult:
    verdict: str  # "PASS" or "FAIL"
    story_id: str
    reason: str = ""
    assertions: list[dict] = field(default_factory=list)
    evidence_dir: str = ""
    timing_ms: dict = field(default_factory=dict)
    extra: dict = field(default_factory=dict)


class VerifierBase:
    """Subclass this in each verifier script. Override `run()` and return a VerifierResult."""

    story_id: str = "OVERRIDE_ME"

    def __init__(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("--story-id", required=True)
        parser.add_argument("--evidence-dir", required=True)
        args = parser.parse_args()
        self.story_id = args.story_id
        self.evidence_dir = Path(args.evidence_dir)
        self.screenshots_dir = self.evidence_dir / "screenshots"
        self.logs_dir = self.evidence_dir / "logs"
        self.audio_dir = self.evidence_dir / "audio"
        self.network_dir = self.evidence_dir / "network"
        for d in (self.screenshots_dir, self.logs_dir, self.audio_dir, self.network_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.start_time = time.time()
        self.assertions: list[dict] = []

    # ----- subclass override -----

    def run(self) -> VerifierResult:
        raise NotImplementedError

    # ----- helpers -----

    def assertion(self, name: str, passed: bool, details: Any = None) -> bool:
        self.assertions.append({
            "name": name,
            "passed": bool(passed),
            "details": details,
            "at": time.time() - self.start_time,
        })
        return bool(passed)

    def fail(self, reason: str, extra: dict | None = None) -> VerifierResult:
        return VerifierResult(
            verdict="FAIL",
            story_id=self.story_id,
            reason=reason,
            assertions=self.assertions,
            evidence_dir=str(self.evidence_dir),
            timing_ms={"total_ms": int((time.time() - self.start_time) * 1000)},
            extra=extra or {},
        )

    def pass_(self, extra: dict | None = None) -> VerifierResult:
        return VerifierResult(
            verdict="PASS",
            story_id=self.story_id,
            reason="",
            assertions=self.assertions,
            evidence_dir=str(self.evidence_dir),
            timing_ms={"total_ms": int((time.time() - self.start_time) * 1000)},
            extra=extra or {},
        )

    def screencap(self, name: str = "screen") -> Path:
        """Take a full-screen screenshot. Returns the file path."""
        ts = int(time.time() * 1000)
        out = self.screenshots_dir / f"{name}_{ts}.png"
        subprocess.run(
            ["screencapture", "-x", str(out)],
            check=False,
            timeout=10,
        )
        return out

    def screencap_region(self, name: str, x: int, y: int, w: int, h: int) -> Path:
        """Take a region screenshot."""
        ts = int(time.time() * 1000)
        out = self.screenshots_dir / f"{name}_{ts}.png"
        subprocess.run(
            ["screencapture", "-x", "-R", f"{x},{y},{w},{h}", str(out)],
            check=False,
            timeout=10,
        )
        return out

    def run_cmd(self, cmd: list[str] | str, log_name: str | None = None, **kwargs) -> subprocess.CompletedProcess:
        """Run a subprocess, log stdout+stderr to evidence/logs/, return the result."""
        if isinstance(cmd, str):
            cmd_str = cmd
            shell = True
        else:
            cmd_str = " ".join(shlex.quote(c) for c in cmd)
            shell = False
        name = log_name or "cmd"
        log_path = self.logs_dir / f"{name}_{int(time.time()*1000)}.log"
        with open(log_path, "wb") as f:
            f.write(f"+ {cmd_str}\n".encode())
            try:
                result = subprocess.run(
                    cmd,
                    shell=shell,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    timeout=kwargs.get("timeout", 120),
                )
                f.write(result.stdout or b"")
                return result
            except subprocess.TimeoutExpired as e:
                f.write(f"\nTIMEOUT after {e.timeout}s\n".encode())
                raise

    def osascript(self, applescript: str, timeout: int = 30) -> tuple[int, str]:
        """Run an AppleScript via osascript. Returns (returncode, stdout_stderr_combined)."""
        result = subprocess.run(
            ["osascript", "-e", applescript],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
        out = (result.stdout or b"").decode("utf-8", errors="replace")
        log_path = self.logs_dir / f"osascript_{int(time.time()*1000)}.log"
        with open(log_path, "w") as f:
            f.write(applescript + "\n---\n" + out)
        return result.returncode, out

    def vision_assert(self, image_path: Path, question: str, expect_yes: bool = True, timeout: int = 60) -> tuple[bool, str]:
        """
        Send the image to OpenRouter vision LLM with a YES/NO question.
        Returns (matched_expectation, raw_response).
        """
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            return (False, "OPENROUTER_API_KEY not set in environment")

        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")

        # Use a vision-capable verifier model. Verifier calls are build cost,
        # but V6 keeps runtime and verifier defaults aligned where possible.
        body = {
            "model": os.environ.get("ANTICIPY_VERIFIER_VISION_MODEL", "moonshotai/kimi-k2.6"),
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"},
                        },
                        {
                            "type": "text",
                            "text": question + " Answer with exactly YES or NO and then a one-sentence justification.",
                        },
                    ],
                }
            ],
            "max_tokens": 200,
        }
        try:
            r = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=timeout,
            )
            r.raise_for_status()
            data = r.json()
            text = data["choices"][0]["message"]["content"]
            # Log the raw response
            log_path = self.logs_dir / f"vision_{int(time.time()*1000)}.log"
            with open(log_path, "w") as f:
                f.write(question + "\n---\n" + text)

            answer = text.strip().upper()
            matched = ("YES" in answer.split()[0] if answer else False) == expect_yes
            return (matched, text)
        except Exception as e:
            return (False, f"vision_assert error: {e}")


def write_result(result: VerifierResult, evidence_dir: Path) -> None:
    """Write the result.json file. The outer loop reads this."""
    out = evidence_dir / "result.json"
    with open(out, "w") as f:
        json.dump(asdict(result), f, indent=2, default=str)


def main_runner(verifier_cls):
    """
    Standard entry point. In each verifier script:

        from verifier.lib.base import VerifierBase, main_runner

        class MyVerifier(VerifierBase):
            def run(self):
                ...
                return self.pass_()

        if __name__ == "__main__":
            main_runner(MyVerifier)
    """
    v = verifier_cls()
    try:
        result = v.run()
    except Exception as e:
        import traceback
        result = v.fail(
            reason=f"verifier crashed: {e}",
            extra={"traceback": traceback.format_exc()},
        )
    write_result(result, v.evidence_dir)
    sys.exit(0 if result.verdict == "PASS" else 1)
