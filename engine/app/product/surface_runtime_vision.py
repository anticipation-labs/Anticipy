"""Vision surface runtime for canvas/no-DOM apps.

When an app has no addressable DOM (Figma, Canva, native windows, in-game UI),
this adapter falls back to a pure-vision loop: capture a screenshot, ask a
vision LLM (Kimi K2.6 primary, Gemini 2.5 Flash fallback) to enumerate every
clickable element with bounding boxes, overlay numeric Set-of-Mark labels, and
expose helpers for description-based lookup and post-action state verification.

This module never imports the frozen action_engine package. Other agents own
the planner/dispatcher; we provide a pure adapter they call on "no_dom".
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:  # pragma: no cover - environmental
    raise RuntimeError(
        "Pillow required for vision adapter. Install via 'pip install Pillow'."
    ) from exc


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# Live OpenRouter catalog id. The spec called this "kimi-k2.6-vision" but the
# actual catalog model is "moonshotai/kimi-k2.6" (multimodal: text+image). The
# `-vision` suffix returns HTTP 400 "not a valid model ID". Same model.
PRIMARY_MODEL = "moonshotai/kimi-k2.6"
FALLBACK_MODEL = "google/gemini-2.5-flash"
SCREENSHOT_DIR = Path(os.environ.get(
    "ANTICIPY_VISION_SCREENSHOTS",
    str(Path.home() / ".anticipy" / "screenshots" / "vision"),
))

PRICING_PER_MTOK = {
    PRIMARY_MODEL: {"in": 0.60, "out": 2.50},
    FALLBACK_MODEL: {"in": 0.075, "out": 0.30},
}

LABEL_PROMPT = (
    "Screenshot of an application surface. Enumerate every clickable element "
    "(buttons, inputs, links, menu items, icons, toggles, tabs, handles). "
    "For each return bbox=[x,y,w,h] in PIXELS (top-left x,y plus width,height), "
    "hint_text (short description like 'Compose button' or 'search input'), and "
    "role in {button,input,link,menu,tab,icon,other}. "
    "Return ONLY JSON: {\"elements\":[{\"bbox\":[x,y,w,h],\"hint_text\":\"...\","
    "\"role\":\"...\"},...]}. Skip decorations and plain text. Cap at 40, "
    "ranked by interaction likelihood."
)

TEXT_REGION_PROMPT = (
    "Screenshot of an application surface. Extract all visible text regions "
    "(headings, body copy, labels, captions). For each return text (under 200 "
    "chars), bbox=[x,y,w,h] in PIXELS, role in {heading,body,label,caption,other}."
    " Return ONLY JSON: {\"regions\":[{\"text\":\"...\",\"bbox\":[x,y,w,h],"
    "\"role\":\"...\"},...]}. Cap at 60. Skip empty regions."
)

VERIFY_PROMPT_TMPL = (
    "Screenshot AFTER an action. EXPECTED post-action state:\n{expected}\n"
    "Answer ONLY JSON: {{\"match\":true|false,\"what_is_visible\":"
    "\"one short sentence describing what you actually see\"}}"
)


@dataclass
class VisionCallResult:
    ok: bool
    content: str
    model: str
    latency_s: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "model": self.model,
            "latency_s": round(self.latency_s, 3),
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "error": self.error,
        }


class VisionSurface:
    """Pure-vision adapter for canvas/no-DOM apps.

    The action dispatcher calls this when the DOM surface returns no
    clickable selectors. Every method returns a JSON-serializable dict.
    No global state. No frozen-path imports.
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        screenshot_dir: Path = SCREENSHOT_DIR,
        primary_model: str = PRIMARY_MODEL,
        fallback_model: str = FALLBACK_MODEL,
        request_timeout_s: float = 60.0,
    ) -> None:
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        if not self.api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY required for VisionSurface "
                "(source .env.local before instantiating)."
            )
        self.screenshot_dir = Path(screenshot_dir)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.primary_model = primary_model
        self.fallback_model = fallback_model
        self.request_timeout_s = float(request_timeout_s)

    # ---------------------------------------------------------------- API

    def label_clickables(self, screenshot_bytes: bytes) -> dict[str, Any]:
        """Detect and label every clickable element via vision LLM cascade."""
        call = self._call_vision_json(screenshot_bytes, LABEL_PROMPT)
        img_w, img_h = self._image_size(screenshot_bytes)
        elements: list[dict[str, Any]] = []
        for idx, raw in enumerate(self._extract_list(call.content, "elements"), 1):
            bbox = self._normalize_bbox(raw.get("bbox"), img_w, img_h)
            if bbox is None:
                continue
            elements.append({"label_id": idx, "bbox": bbox,
                             "hint_text": str(raw.get("hint_text", ""))[:200],
                             "role": str(raw.get("role", "other"))[:32]})
        return {
            "labeled_screenshot_path": self._overlay_marks(screenshot_bytes,
                                                           elements),
            "elements": elements,
            "call": call.to_dict(),
            "image_size": [img_w, img_h],
        }

    def extract_text_regions(self, screenshot_bytes: bytes) -> dict[str, Any]:
        """Vision-only text extraction for canvas surfaces."""
        call = self._call_vision_json(screenshot_bytes, TEXT_REGION_PROMPT)
        img_w, img_h = self._image_size(screenshot_bytes)
        regions: list[dict[str, Any]] = []
        for raw in self._extract_list(call.content, "regions"):
            bbox = self._normalize_bbox(raw.get("bbox"), img_w, img_h)
            text = str(raw.get("text", "")).strip()
            if bbox is None or not text:
                continue
            regions.append({"text": text[:400], "bbox": bbox,
                            "role": str(raw.get("role", "other"))[:32]})
        return {"regions": regions, "call": call.to_dict()}

    def find_element_by_description(
        self, screenshot_bytes: bytes, description: str
    ) -> Optional[dict[str, Any]]:
        """Locate an element by natural-language description.

        Returns {label_id, bbox, confidence, hint_text} or None when no match.
        """
        labeled = self.label_clickables(screenshot_bytes)
        elements = labeled.get("elements", [])
        if not elements:
            return None
        desc = (description or "").strip()
        if not desc:
            return None

        catalog = "\n".join(
            f"#{el['label_id']} role={el['role']} hint={el['hint_text']!r}"
            for el in elements
        )
        prompt = (
            "From the labeled element catalog below, pick the SINGLE element "
            f"that best matches the description: {desc!r}\n\n"
            f"CATALOG:\n{catalog}\n\n"
            "Return ONLY JSON: {\"label_id\": <int or null>, "
            "\"confidence\": <float 0..1>, "
            "\"reasoning\": \"one short sentence\"}\n"
            "Use null if no element plausibly matches."
        )
        call = self._call_vision_json(screenshot_bytes, prompt)
        parsed = self._parse_json(call.content) or {}
        label_id = parsed.get("label_id")
        if not isinstance(label_id, int):
            return None
        match = next((el for el in elements if el["label_id"] == label_id), None)
        if not match:
            return None
        confidence = parsed.get("confidence", 0.0)
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.0
        return {
            "label_id": match["label_id"],
            "bbox": match["bbox"],
            "hint_text": match["hint_text"],
            "role": match["role"],
            "confidence": max(0.0, min(1.0, confidence)),
            "reasoning": str(parsed.get("reasoning", ""))[:300],
            "labeled_screenshot_path": labeled.get("labeled_screenshot_path", ""),
        }

    def verify_state(
        self, screenshot_bytes: bytes, expected_description: str
    ) -> dict[str, Any]:
        """Check whether the current surface matches an expected post-action state."""
        expected = (expected_description or "").strip()
        prompt = VERIFY_PROMPT_TMPL.format(expected=expected or "<no expectation given>")
        call = self._call_vision_json(screenshot_bytes, prompt)
        parsed = self._parse_json(call.content) or {}
        match = bool(parsed.get("match"))
        what = str(parsed.get("what_is_visible", "")).strip()[:400]
        return {
            "match": match,
            "what_is_visible": what or "(vision returned no description)",
            "call": call.to_dict(),
        }

    # ---------------------------------------------------------------- internals

    def _call_vision_json(self, png_bytes: bytes, prompt: str) -> VisionCallResult:
        """Cascade: try primary, fall back on failure or empty content."""
        b64 = base64.b64encode(png_bytes).decode("ascii")
        for model in (self.primary_model, self.fallback_model):
            t0 = time.time()
            result = self._post_chat(model, prompt, b64)
            result.latency_s = time.time() - t0
            if result.ok and result.content.strip():
                return result
            # try fallback
        return result  # type: ignore[return-value]

    def _post_chat(self, model: str, prompt: str, image_b64: str) -> VisionCallResult:
        # Reasoning OFF: both Kimi and Gemini are reasoning-capable but would
        # otherwise spend the budget on internal CoT and return empty content.
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
            ]}],
            "max_tokens": 2048,
            "temperature": 0.0,
            "reasoning": {"enabled": False},
        }
        req = urllib.request.Request(
            OPENROUTER_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://anticipy.ai",
                "X-Title": "Anticipy vision adapter",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.request_timeout_s) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            return VisionCallResult(
                ok=False, content="", model=model, latency_s=0.0,
                error=f"HTTP {exc.code}: {exc.read()[:300].decode('utf-8', 'replace')}",
            )
        except Exception as exc:
            return VisionCallResult(ok=False, content="", model=model, latency_s=0.0,
                                    error=f"{type(exc).__name__}: {exc}")
        try:
            content = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            content = ""
        usage = data.get("usage") or {}
        p_tok = int(usage.get("prompt_tokens", 0) or 0)
        c_tok = int(usage.get("completion_tokens", 0) or 0)
        rate = PRICING_PER_MTOK.get(model, {"in": 0.0, "out": 0.0})
        cost = (p_tok / 1_000_000.0) * rate["in"] + (c_tok / 1_000_000.0) * rate["out"]
        return VisionCallResult(ok=bool(content), content=content, model=model,
                                latency_s=0.0, prompt_tokens=p_tok,
                                completion_tokens=c_tok, cost_usd=cost)

    def _parse_json(self, raw: str) -> Optional[dict[str, Any]]:
        if not raw:
            return None
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```\s*$", "", text)
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

    def _extract_list(self, raw: str, key: str) -> list[dict[str, Any]]:
        parsed = self._parse_json(raw) or {}
        value = parsed.get(key, [])
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    def _normalize_bbox(
        self, bbox_raw: Any, img_w: int, img_h: int
    ) -> Optional[list[int]]:
        if not isinstance(bbox_raw, (list, tuple)) or len(bbox_raw) != 4:
            return None
        try:
            x, y, w, h = [float(v) for v in bbox_raw]
        except (TypeError, ValueError):
            return None
        # Heuristic: if all values <= 1.0 the model returned normalized coords.
        if max(x, y, w, h) <= 1.0 and img_w > 0 and img_h > 0:
            x, y, w, h = x * img_w, y * img_h, w * img_w, h * img_h
        x = max(0, int(round(x)))
        y = max(0, int(round(y)))
        w = max(1, int(round(w)))
        h = max(1, int(round(h)))
        if img_w and x + w > img_w:
            w = max(1, img_w - x)
        if img_h and y + h > img_h:
            h = max(1, img_h - y)
        return [x, y, w, h]

    def _image_size(self, png_bytes: bytes) -> tuple[int, int]:
        try:
            with Image.open(io.BytesIO(png_bytes)) as im:
                return im.size
        except Exception:
            return (0, 0)

    def _overlay_marks(self, png_bytes: bytes,
                       elements: list[dict[str, Any]]) -> str:
        ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        out_path = self.screenshot_dir / f"{ts}_labeled.png"
        try:
            with Image.open(io.BytesIO(png_bytes)) as src:
                img = src.convert("RGBA")
        except Exception:
            return ""
        draw = ImageDraw.Draw(img, "RGBA")
        font = self._load_font(size=14)
        for el in elements:
            x, y, w, h = el["bbox"]
            draw.rectangle([(x, y), (x + w, y + h)],
                           outline=(255, 64, 64, 255), width=2)
            label = str(el["label_id"])
            tw, th = self._text_size(draw, label, font)
            pad = 3
            box_w, box_h = tw + 2 * pad, th + 2 * pad
            lx, ly = x, max(0, y - box_h)
            draw.rectangle([(lx, ly), (lx + box_w, ly + box_h)],
                           fill=(255, 64, 64, 230))
            draw.text((lx + pad, ly + pad), label,
                      fill=(255, 255, 255, 255), font=font)
        try:
            img.convert("RGB").save(out_path, format="PNG", optimize=True)
            return str(out_path)
        except Exception:
            return ""

    def _load_font(self, size: int = 14) -> Any:
        for candidate in ("/System/Library/Fonts/Helvetica.ttc",
                          "/System/Library/Fonts/Supplemental/Arial.ttf",
                          "/Library/Fonts/Arial.ttf"):
            try:
                return ImageFont.truetype(candidate, size=size)
            except Exception:
                continue
        return ImageFont.load_default()

    def _text_size(self, draw: Any, text: str, font: Any) -> tuple[int, int]:
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            return (bbox[2] - bbox[0], bbox[3] - bbox[1])
        except Exception:
            return (8 * len(text), 12)
