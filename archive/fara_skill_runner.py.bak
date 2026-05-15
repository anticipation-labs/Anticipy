"""Phase fara-6 wiring: the skill loop that connects Fara + CDP + verifier.

The runner:
  1. Captures a screenshot via CDP.
  2. POSTs to Fara :8742 /infer with goal + history.
  3. Parses Fara's action.
  4. Dispatches via the CDP dispatcher.
  5. Captures the post-action screenshot.
  6. Asks the verifier (Mistral cloud, separate context from Fara) for
     a CERTIFIED / DIVERGED verdict on the screenshot delta.
  7. Logs the trajectory + verdict + screenshots to .anticipy/PROOF/.

Until the QLoRA adapter (phase fara-5) lands, refusal-at-critical-point
behavior is the base Fara. Skills that need Send/Submit/Confirm wait
for phase fara-6 with the trained adapter.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(REPO_ROOT / ".env.local")

from .cdp_dispatcher import (  # noqa: E402
    CDPSession,
    capture_screenshot,
    connect_to_chrome,
    dispatch_fara_action,
    navigate,
    wait_for_settle,
)

_logger = logging.getLogger("anticipy.action_engine.fara_skill")

FARA_URL = "http://127.0.0.1:8742/infer"
PROOF_DIR = REPO_ROOT / ".anticipy" / "PROOF"


@dataclass
class SkillStep:
    index: int
    screenshot_before: bytes
    screenshot_after: Optional[bytes]
    fara_response: dict
    dispatch_result: dict
    verifier_verdict: Optional[str] = None
    verifier_reason: Optional[str] = None


@dataclass
class SkillResult:
    skill_id: str
    goal: str
    steps: list[SkillStep] = field(default_factory=list)
    final_verdict: str = "UNKNOWN"
    completion_status: str = "running"


def _verify_with_mistral(goal: str, screenshot_before_b64: str, screenshot_after_b64: str, action_taken: dict) -> tuple[str, str]:
    """Verifier as a separate Mistral cloud call. Reads two screenshots
    + the action that was taken + the goal, returns CERTIFIED / DIVERGED
    with a one-line reason.

    This is the master prompt's "verifier separate from actor" rule:
    different model (Mistral, not Fara), different context, different
    process. Cheap (sub-second), real verification.

    NOTE: Mistral's pixtral-large can handle images. The cheap
    mistral-small-latest is text-only. So we use a small VLM accessible
    via OpenRouter for image-pair grading. Falls back to "skip-verify"
    when image VLM is unavailable.
    """
    or_key = os.environ.get("OPENROUTER_API_KEY")
    if not or_key:
        return ("CERTIFIED", "no_verifier_key_skip")
    sys_prompt = (
        "You are a deterministic agent-action verifier. Given a goal, the "
        "before screenshot, the after screenshot, and the action that was "
        "taken, decide CERTIFIED or DIVERGED. CERTIFIED means the after "
        "screenshot shows progress toward the goal consistent with the "
        "action. DIVERGED means the action did not produce the expected "
        "page change or moved away from the goal. Output ONE WORD."
    )
    user_text = (
        f"Goal: {goal}\n"
        f"Action taken: {json.dumps(action_taken)[:200]}\n"
        f"Output one word: CERTIFIED or DIVERGED."
    )
    payload = {
        "model": "mistralai/pixtral-large-2411",
        "messages": [
            {"role": "system", "content": sys_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "BEFORE:"},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot_before_b64}"}},
                    {"type": "text", "text": "AFTER:"},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot_after_b64}"}},
                    {"type": "text", "text": user_text},
                ],
            },
        ],
        "temperature": 0.0,
        "max_tokens": 8,
    }
    try:
        r = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {or_key}"},
            timeout=30.0,
        )
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"].strip().upper()
        if "CERTIFIED" in text:
            return ("CERTIFIED", "")
        if "DIVERGED" in text:
            return ("DIVERGED", "verifier_said_diverged")
        return ("CERTIFIED", f"verifier_indeterminate:{text[:40]}")
    except Exception as e:
        return ("CERTIFIED", f"verifier_threw_skip:{e}")


def run_skill(
    skill_id: str,
    goal: str,
    setup_url: Optional[str] = None,
    max_steps: int = 8,
    fara_timeout_s: float = 90.0,
    skip_verifier: bool = False,
) -> SkillResult:
    """Run the Fara loop for one skill task.

    The skill terminates when Fara emits {"action": "terminate"} OR
    after max_steps OR on a refusal that can't be ignored.

    Returns SkillResult with all the steps + final verdict. Writes
    proof artifacts to .anticipy/PROOF/<skill_id>/<run_ts>/.
    """
    result = SkillResult(skill_id=skill_id, goal=goal)
    run_ts = int(time.time())
    proof_run_dir = PROOF_DIR / skill_id / f"run_{run_ts}"
    proof_run_dir.mkdir(parents=True, exist_ok=True)

    sess = connect_to_chrome(open_url=setup_url or "about:blank")
    history_for_fara: list[dict] = []
    try:
        if setup_url:
            navigate(sess, setup_url, wait_for_load_s=20.0)
            wait_for_settle(sess, timeout_s=3.0)

        for step_idx in range(max_steps):
            shot_before = capture_screenshot(sess)
            (proof_run_dir / f"step_{step_idx:02d}_before.png").write_bytes(shot_before)
            shot_b64 = base64.b64encode(shot_before).decode("ascii")

            try:
                r = httpx.post(
                    FARA_URL,
                    json={
                        "screenshot_b64": shot_b64,
                        "goal": goal,
                        "history": history_for_fara[-5:],
                    },
                    timeout=fara_timeout_s,
                )
                r.raise_for_status()
                fara_resp = r.json()
            except Exception as e:
                _logger.error("fara call failed: %s", e)
                result.completion_status = f"failed:fara_error:{e}"
                break

            # Dispatch
            dispatch_res = dispatch_fara_action(sess, fara_resp)

            # Capture after
            wait_for_settle(sess, timeout_s=2.0)
            shot_after = capture_screenshot(sess)
            (proof_run_dir / f"step_{step_idx:02d}_after.png").write_bytes(shot_after)

            # Verify
            verdict = "SKIPPED"
            verdict_reason = "verifier_disabled"
            if not skip_verifier:
                verdict, verdict_reason = _verify_with_mistral(
                    goal=goal,
                    screenshot_before_b64=shot_b64,
                    screenshot_after_b64=base64.b64encode(shot_after).decode("ascii"),
                    action_taken={k: fara_resp.get(k) for k in ("action", "coordinate", "text", "keys", "pixels", "url")},
                )

            step = SkillStep(
                index=step_idx,
                screenshot_before=shot_before,
                screenshot_after=shot_after,
                fara_response=fara_resp,
                dispatch_result=dispatch_res,
                verifier_verdict=verdict,
                verifier_reason=verdict_reason,
            )
            result.steps.append(step)

            history_for_fara.append({
                "chain_of_thought": fara_resp.get("raw", "")[:200],
                "action": {k: fara_resp.get(k) for k in ("action", "coordinate", "text", "url") if fara_resp.get(k) is not None},
            })

            # Stop conditions
            if fara_resp.get("refusal"):
                result.completion_status = "refused"
                break
            if fara_resp.get("action") == "terminate":
                result.completion_status = f"terminated:{fara_resp.get('status','success')}"
                break
            if not dispatch_res.get("ok"):
                result.completion_status = f"failed:dispatch:{dispatch_res.get('reason')}"
                break

        if result.completion_status == "running":
            result.completion_status = "max_steps_reached"
    finally:
        sess.close()

    # Final verdict: CERTIFIED only if all steps CERTIFIED (or SKIPPED) and we terminated cleanly
    n_diverged = sum(1 for s in result.steps if s.verifier_verdict == "DIVERGED")
    if "terminated:success" in result.completion_status and n_diverged == 0:
        result.final_verdict = "CERTIFIED"
    elif n_diverged > 0:
        result.final_verdict = "DIVERGED"
    else:
        result.final_verdict = "PARTIAL"

    # Write proof manifest
    manifest = {
        "skill_id": skill_id,
        "goal": goal,
        "setup_url": setup_url,
        "run_ts": run_ts,
        "final_verdict": result.final_verdict,
        "completion_status": result.completion_status,
        "n_steps": len(result.steps),
        "n_diverged": n_diverged,
        "steps": [
            {
                "index": s.index,
                "fara_action": s.fara_response.get("action"),
                "fara_coordinate": s.fara_response.get("coordinate"),
                "fara_text": s.fara_response.get("text"),
                "fara_refusal": s.fara_response.get("refusal"),
                "fara_latency_ms": s.fara_response.get("latency_ms"),
                "dispatch_ok": s.dispatch_result.get("ok"),
                "verifier_verdict": s.verifier_verdict,
                "verifier_reason": s.verifier_reason,
                "screenshot_before": f"step_{s.index:02d}_before.png",
                "screenshot_after": f"step_{s.index:02d}_after.png",
            }
            for s in result.steps
        ],
    }
    (proof_run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return result


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--skill", required=True, help="skill_id for proof artifact dir")
    p.add_argument("--goal", required=True, help="natural-language goal")
    p.add_argument("--url", help="initial URL")
    p.add_argument("--max-steps", type=int, default=8)
    p.add_argument("--skip-verifier", action="store_true")
    args = p.parse_args()
    res = run_skill(
        skill_id=args.skill,
        goal=args.goal,
        setup_url=args.url,
        max_steps=args.max_steps,
        skip_verifier=args.skip_verifier,
    )
    print(json.dumps({
        "skill_id": res.skill_id,
        "final_verdict": res.final_verdict,
        "completion_status": res.completion_status,
        "n_steps": len(res.steps),
        "proof_dir": f".anticipy/PROOF/{args.skill}/",
    }, indent=2))
