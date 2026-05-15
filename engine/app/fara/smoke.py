"""One-shot Fara inference smoke. Used by phase fara-2 gate.

Loads the MLX 4-bit model, runs one inference against a real
screenshot with the exact system prompt from Fara's model card,
and reports the parsed action.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "engine"))

from app.fara.server import SYSTEM_PROMPT, _parse_fara_output  # noqa: E402

MODEL_PATH = Path.home() / ".anticipy" / "models" / "fara-7b-mlx-4bit"


def smoke(screenshot_path: Path, goal: str) -> dict:
    from mlx_vlm import generate, load

    t0 = time.monotonic()
    model, processor = load(str(MODEL_PATH))
    load_s = time.monotonic() - t0

    img = Image.open(screenshot_path).convert("RGB")
    if img.size != (1428, 896):
        img = img.resize((1428, 896), Image.LANCZOS)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "image"},
                {"type": "text", "text": f"Task: {goal}\n\nWhat is the next action?"},
            ],
        },
    ]
    prompt = processor.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )

    t1 = time.monotonic()
    out = generate(
        model, processor, prompt=prompt, image=img, max_tokens=256, temp=0.0, verbose=False
    )
    infer_s = time.monotonic() - t1

    raw = out if isinstance(out, str) else (out.text if hasattr(out, "text") else str(out))
    parsed = _parse_fara_output(raw)
    return {
        "load_s": load_s,
        "infer_s": infer_s,
        "raw": raw[:800],
        "parsed": parsed,
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: python -m app.fara.smoke <screenshot.png> <goal>", file=sys.stderr)
        sys.exit(2)
    result = smoke(Path(sys.argv[1]), sys.argv[2])
    print(json.dumps(result, indent=2, default=str))
