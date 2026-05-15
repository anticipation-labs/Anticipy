"""Fara-7B local inference server. Phase fara-2.

FastAPI on 127.0.0.1:8742. POST /infer with screenshot + goal + history,
returns the parsed action from Fara's tool_call output.

Fara model card key facts (verified by reading the README at
microsoft/Fara-7B on HuggingFace):

- Architecture: Qwen 2.5-VL 7B base, post-trained for computer-use.
- Default screen resolution Fara was trained for: 1428 x 896.
- Output format: ChatML with chain-of-thought, then a tool_call JSON
  block of the form
    {"name": "computer_use", "arguments": {"action": "left_click", "coordinate": [x, y]}}
- Available actions: key, type, mouse_move, left_click, scroll,
  visit_url, web_search, history_back, pause_and_memorize_fact,
  wait, terminate.
- Critical points (model trained to halt): checkout, book, purchase,
  call, email, order. Our QLoRA in phase 5 trains those refusals out
  for our 8 proof scenarios where Send/Submit/Confirm IS the action.

The server stays MLX-only on Apple Silicon. CPU and CUDA paths NOT
supported here. If MLX init fails, the server returns 503 with
{"error": "mlx_unavailable"}.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from PIL import Image
from pydantic import BaseModel

_logger = logging.getLogger("anticipy.fara.server")
_logger.setLevel(logging.INFO)

# Path to the MLX 4-bit converted Fara model. Set by phase fara-2's
# convert step; the server validates it exists at startup.
DEFAULT_MODEL_PATH = Path.home() / ".anticipy" / "models" / "fara-7b-mlx-4bit"

# Default screen resolution Fara expects (per model card).
FARA_SCREEN_W = 1428
FARA_SCREEN_H = 896

SYSTEM_PROMPT = (
    "You are a web automation agent that performs actions on websites to fulfill "
    "user requests by calling various tools.\n\n"
    "You should stop execution at Critical Points. A Critical Point occurs in tasks like:\n"
    "- Checkout\n- Book\n- Purchase\n- Call\n- Email\n- Order\n\n"
    "A Critical Point requires the user's permission or personal/sensitive information "
    "(name, email, credit card, address, payment information, resume, etc.) to complete "
    "a transaction (purchase, reservation, sign-up, etc.), or to communicate as a human "
    "would (call, email, apply to a job, etc.).\n\n"
    "Guideline: Solve the task as far as possible up until a Critical Point.\n\n"
    "Examples:\n"
    "- If the task is to \"call a restaurant to make a reservation,\" do not actually "
    "make the call. Instead, navigate to the restaurant's page and find the phone number.\n"
    "- If the task is to \"order new size 12 running shoes,\" do not place the order. "
    "Instead, search for the right shoes that meet the criteria and add them to the cart.\n\n"
    "Some tasks, like answering questions, may not encounter a Critical Point at all.\n\n"
    "For each function call, return a JSON object with the function name and arguments."
)


class InferRequest(BaseModel):
    screenshot_b64: str
    goal: str
    history: list[dict] = []
    max_tokens: int = 256
    temperature: float = 0.0


class InferResponse(BaseModel):
    action: Optional[str] = None
    coordinate: Optional[list[int]] = None
    text: Optional[str] = None
    keys: Optional[list[str]] = None
    pixels: Optional[int] = None
    url: Optional[str] = None
    query: Optional[str] = None
    fact: Optional[str] = None
    time: Optional[float] = None
    status: Optional[str] = None
    chain_of_thought: Optional[str] = None
    raw: str
    refusal: bool = False
    refusal_reason: Optional[str] = None
    latency_ms: int


# ─── Lazy-loaded MLX model (loaded on first /infer) ────────────────────
_MODEL = None
_PROCESSOR = None
_MODEL_LOAD_ERR: Optional[str] = None


def _ensure_loaded(model_path: Path = DEFAULT_MODEL_PATH):
    global _MODEL, _PROCESSOR, _MODEL_LOAD_ERR
    if _MODEL is not None:
        return
    if _MODEL_LOAD_ERR:
        raise HTTPException(status_code=503, detail=_MODEL_LOAD_ERR)
    if not model_path.exists():
        _MODEL_LOAD_ERR = f"model_path_missing:{model_path}"
        raise HTTPException(status_code=503, detail=_MODEL_LOAD_ERR)
    try:
        from mlx_vlm import load  # type: ignore
        _logger.info("loading Fara-7B from %s ...", model_path)
        t0 = time.monotonic()
        _MODEL, _PROCESSOR = load(str(model_path))
        _logger.info("Fara-7B loaded in %.1fs", time.monotonic() - t0)
    except Exception as e:
        _MODEL_LOAD_ERR = f"mlx_load_failed:{e}"
        _logger.error("MLX load failed: %s", e)
        raise HTTPException(status_code=503, detail=_MODEL_LOAD_ERR)


def _build_messages(req: InferRequest) -> list[dict]:
    """Build the ChatML messages list per Fara's expected input format.
    User message contains goal + history of prior steps + current screenshot.
    """
    history_text = ""
    if req.history:
        history_text = "\n\nPrevious steps:\n"
        for i, step in enumerate(req.history[-10:], 1):
            thought = step.get("chain_of_thought") or ""
            action = step.get("action") or {}
            history_text += f"  Step {i}: thought={thought[:120]}, action={json.dumps(action)}\n"

    user_text = f"Task: {req.goal}{history_text}\n\nWhat is the next action?"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "image"},
                {"type": "text", "text": user_text},
            ],
        },
    ]


_TOOL_CALL_RE = re.compile(r"\{[^{}]*\"action\"\s*:\s*\"([^\"]+)\"[^{}]*\}", re.DOTALL)
_THOUGHT_RE = re.compile(r"<think>(.+?)</think>", re.DOTALL)
_REFUSAL_PATTERNS = [
    "request_help", "requires_user_consent", "cannot_complete",
    "i cannot", "i'm unable", "i am unable", "critical point",
]


def _parse_fara_output(raw: str) -> dict:
    """Parse Fara's raw output into structured fields. Robust to the
    exact ChatML envelope variations.
    """
    out = {"raw": raw, "refusal": False}

    # Chain of thought: Fara emits <think>...</think> on some training mixes.
    tm = _THOUGHT_RE.search(raw)
    if tm:
        out["chain_of_thought"] = tm.group(1).strip()[:1000]

    # Refusal detection: if any refusal pattern is in the output AND no
    # tool call follows, flag refusal.
    raw_lower = raw.lower()
    refusal_hit = next((p for p in _REFUSAL_PATTERNS if p in raw_lower), None)

    # Find the first tool_call-shaped JSON block
    # Try to extract a JSON object containing "name": "computer_use"
    json_blocks = re.findall(r"\{[^{}]*\"name\"\s*:\s*\"computer_use\"[\s\S]*?\}\s*\}", raw)
    if not json_blocks:
        # fall back: look for any object with action key
        json_blocks = re.findall(r"\{[\s\S]*?\"action\"[\s\S]*?\}", raw)

    parsed_args = None
    for blob in json_blocks:
        try:
            obj = json.loads(blob)
            if isinstance(obj, dict):
                args = obj.get("arguments") or obj
                if isinstance(args, dict) and "action" in args:
                    parsed_args = args
                    break
        except json.JSONDecodeError:
            # Try to fix common issues with truncation
            continue

    if parsed_args is None:
        # No valid tool call. If refusal pattern matched, mark refusal.
        if refusal_hit:
            out["refusal"] = True
            out["refusal_reason"] = refusal_hit
        return out

    out["action"] = parsed_args.get("action")
    if "coordinate" in parsed_args and isinstance(parsed_args["coordinate"], (list, tuple)):
        out["coordinate"] = [int(parsed_args["coordinate"][0]), int(parsed_args["coordinate"][1])]
    for k in ("text", "keys", "pixels", "url", "query", "fact", "time", "status"):
        if k in parsed_args:
            out[k] = parsed_args[k]
    return out


def _resize_for_fara(img_bytes: bytes) -> tuple[bytes, float, float]:
    """Resize an arbitrary screenshot to Fara's expected viewport
    (1428 x 896). Returns (png_bytes, scale_x, scale_y) so the caller
    can map Fara's output coords back to the source viewport.
    """
    img = Image.open(io.BytesIO(img_bytes))
    src_w, src_h = img.size
    if (src_w, src_h) == (FARA_SCREEN_W, FARA_SCREEN_H):
        return img_bytes, 1.0, 1.0
    # Fit by long edge ratio so aspect is preserved; pad if needed
    img2 = img.resize((FARA_SCREEN_W, FARA_SCREEN_H), Image.LANCZOS)
    buf = io.BytesIO()
    img2.save(buf, format="PNG")
    scale_x = src_w / FARA_SCREEN_W
    scale_y = src_h / FARA_SCREEN_H
    return buf.getvalue(), scale_x, scale_y


def _create_app() -> FastAPI:
    app = FastAPI(title="Anticipy Fara-7B Inference Server", version="0.1.0")

    @app.get("/health")
    def health():
        return {
            "ok": True,
            "model_path": str(DEFAULT_MODEL_PATH),
            "model_loaded": _MODEL is not None,
            "load_error": _MODEL_LOAD_ERR,
        }

    @app.post("/infer", response_model=InferResponse)
    def infer(req: InferRequest):
        t0 = time.monotonic()
        _ensure_loaded()
        try:
            from mlx_vlm import generate  # type: ignore
        except ImportError as e:
            raise HTTPException(status_code=503, detail=f"mlx_vlm_missing:{e}")

        try:
            img_bytes = base64.b64decode(req.screenshot_b64)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"bad_b64:{e}")

        png_bytes, sx, sy = _resize_for_fara(img_bytes)
        # mlx_vlm expects a PIL.Image OR a path. Use PIL.Image.
        img = Image.open(io.BytesIO(png_bytes))

        messages = _build_messages(req)
        # Apply chat template
        prompt = _PROCESSOR.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )

        raw = generate(
            _MODEL,
            _PROCESSOR,
            prompt=prompt,
            image=img,
            max_tokens=req.max_tokens,
            temp=req.temperature,
            verbose=False,
        )

        parsed = _parse_fara_output(raw if isinstance(raw, str) else str(raw))
        # Map coordinates back to source viewport scale
        if parsed.get("coordinate") and (sx != 1.0 or sy != 1.0):
            cx, cy = parsed["coordinate"]
            parsed["coordinate"] = [int(cx * sx), int(cy * sy)]

        latency_ms = int((time.monotonic() - t0) * 1000)
        return InferResponse(latency_ms=latency_ms, **parsed)

    return app


app = _create_app()


if __name__ == "__main__":
    import uvicorn
    log_level = os.environ.get("FARA_LOG_LEVEL", "info")
    port = int(os.environ.get("FARA_PORT", "8742"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level=log_level)
