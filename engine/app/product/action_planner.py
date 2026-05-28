"""ActionPlanner: pick the next primitive given intent + live surface state.

Calls OpenRouter with a cheap model cascade:
  deepseek/deepseek-chat-v4-flash -> moonshotai/kimi-k2.6-instruct ->
  google/gemini-flash-2.5

When DOM is weak/empty (canvas apps), this swaps to a vision-capable model
(kimi-k2.6-vision) and includes the screenshot as base64.

Output contract: {"primitive": "...", "args": {...}, "why": "..."}.
Always returns valid JSON; on parse failure we return a "read" no-op so the
dispatcher can recover instead of crashing.
"""

from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
TEXT_CASCADE = [
    "deepseek/deepseek-v4-flash",
    "moonshotai/kimi-k2.6",
    "google/gemini-3.5-flash",
]
VISION_MODEL = "moonshotai/kimi-k2.6"
DEFAULT_TIMEOUT = 20.0


@dataclass
class PlannerStep:
    primitive: str
    args: dict[str, Any] = field(default_factory=dict)
    why: str = ""
    model: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"primitive": self.primitive, "args": dict(self.args),
                "why": self.why, "model": self.model}


class ActionPlanner:
    """Pick the next primitive. Cheap models only. Never blocks for long."""

    PRIMITIVES = (
        "read", "open", "click", "type", "key", "wait", "verify",
        "ask_user", "notify_user", "done",
    )

    SYSTEM_PROMPT = (
        "You are Anticipy's action planner. The user has an intent. You receive "
        "the current visible surface (URL, title, DOM/AX summary) and history "
        "of prior primitives. Pick exactly ONE next primitive that moves the "
        "intent forward by the smallest sensible step.\n\n"
        "Allowed primitives: read, open, click, type, key, wait, verify, "
        "ask_user, notify_user, done.\n\n"
        "Output ONLY a JSON object with keys primitive, args, why. No prose.\n"
        "Args by primitive:\n"
        '  open: {"url_or_app": "https://..."}\n'
        '  click: {"target": "css-selector OR M3"}\n'
        '  type:  {"text": "...", "selector": "optional css"}\n'
        '  key:   {"key": "return", "modifiers": []}\n'
        '  wait:  {"condition": {"url_contains": "..."}, "timeout": 10}\n'
        '  verify:{"expected": {"url_contains": "...", "title_contains": "..."}}\n'
        '  read:  {"surface_target": "active_tab"}\n'
        '  ask_user: {"question": "...", "options": []}\n'
        '  notify_user: {"message": "..."}\n'
        '  done: {} (only when verify just passed)\n\n'
        "Hard rules:\n"
        "- Prefer the smallest primitive that advances. Never plan multiple "
        "actions in one step.\n"
        "- After typing into a search box, the next step is usually key:return.\n"
        "- After any action that should change the page, plan wait or verify.\n"
        "- Never decline. If truly stuck, return ask_user with a specific "
        "question. Never invent a primitive name."
    )

    def __init__(self, *, api_key: str | None = None,
                 timeout: float = DEFAULT_TIMEOUT,
                 cascade: list[str] | None = None,
                 vision_model: str = VISION_MODEL) -> None:
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self.timeout = float(timeout)
        self.cascade = list(cascade or TEXT_CASCADE)
        self.vision_model = vision_model

    # ----------------------------------------------------------- public api

    def plan_next_primitive(
        self,
        intent: str,
        current_surface: dict[str, Any],
        history: list[dict[str, Any]],
        memory_context: dict[str, Any] | None = None,
    ) -> PlannerStep:
        memory_context = memory_context or {}
        weak_dom = self._dom_is_weak(current_surface)
        prompt_messages = self._build_messages(
            intent, current_surface, history, memory_context, weak_dom,
        )

        # Vision path: weak DOM AND we have a screenshot path.
        screenshot_path = current_surface.get("screenshot_path", "")
        models = list(self.cascade)
        if weak_dom and screenshot_path and Path(str(screenshot_path)).exists():
            models = [self.vision_model] + models
            prompt_messages = self._attach_image(prompt_messages, str(screenshot_path))

        last_err = ""
        for model in models:
            text, err = self._call_openrouter(model, prompt_messages)
            if err:
                last_err = err
                continue
            step = self._parse_step(text, model=model)
            if step is not None:
                return step
            last_err = f"unparseable response from {model}: {text[:200]}"

        # Cascade fully exhausted: emit safe re-read so dispatcher can retry.
        return PlannerStep(
            primitive="read", args={"surface_target": "active_tab"},
            why=f"planner cascade failed: {last_err[:160]}",
            model="cascade-failed", raw={"error": last_err},
        )

    # ----------------------------------------------------------- internals

    def _dom_is_weak(self, surface: dict[str, Any]) -> bool:
        dom = str(surface.get("dom_text") or surface.get("dom_structure") or "")
        if len(dom) < 200:
            return True
        if "data-bridge='applescript'" in dom:
            return True
        return False

    def _build_messages(self, intent: str, surface: dict[str, Any],
                        history: list[dict[str, Any]],
                        memory: dict[str, Any], weak: bool) -> list[dict[str, Any]]:
        url = surface.get("url", "")
        title = surface.get("title", "")
        dom_text = str(surface.get("dom_text") or "")[:8000]
        ax = str(surface.get("dom_structure") or "")[:2000]
        marks = surface.get("visible_elements_with_set_of_mark_labels") or []
        marks_text = "\n".join(
            f"  {m.get('label')}: {m.get('name', '')[:80]}" for m in marks[:24]
        ) if marks else "(none)"
        hist_lines: list[str] = []
        for h in (history or [])[-8:]:
            p = h.get("primitive", "?")
            ok = "ok" if h.get("ok") else "FAIL"
            why = (h.get("why") or "")[:80]
            err = (h.get("error") or "")[:80]
            hist_lines.append(f"  - {p} [{ok}] {why} {err}".rstrip())
        history_text = "\n".join(hist_lines) if hist_lines else "  (none yet)"
        mem_text = ", ".join(f"{k}={str(v)[:60]}" for k, v in memory.items())
        weak_hint = ""
        if weak:
            weak_hint = (
                "\n\nNOTE: DOM is weak/empty (canvas or restricted page). "
                "Use the Set-of-Mark labels above to click, or use osascript-"
                "friendly primitives (type, key).")
        user = (
            f"USER INTENT:\n  {intent}\n\n"
            f"CURRENT SURFACE:\n  url: {url}\n  title: {title}\n"
            f"  DOM (truncated): {dom_text[:2000]}\n"
            f"  AX tree: {ax}\n"
            f"  Set-of-Mark labels:\n{marks_text}\n\n"
            f"HISTORY (most recent last):\n{history_text}\n\n"
            f"MEMORY CONTEXT: {mem_text or '(none)'}{weak_hint}\n\n"
            "Output JSON only."
        )
        return [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ]

    def _attach_image(self, messages: list[dict[str, Any]],
                      image_path: str) -> list[dict[str, Any]]:
        try:
            with open(image_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
        except Exception:
            return messages
        out = list(messages)
        out[-1] = {
            "role": "user",
            "content": [
                {"type": "text", "text": out[-1]["content"]},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ],
        }
        return out

    def _call_openrouter(self, model: str,
                         messages: list[dict[str, Any]]) -> tuple[str, str]:
        if not self.api_key:
            return "", "OPENROUTER_API_KEY missing"
        body = json.dumps({
            "model": model,
            "messages": messages,
            "temperature": 0.0,
            "max_tokens": 400,
            "response_format": {"type": "json_object"},
        }).encode("utf-8")
        req = urllib.request.Request(
            OPENROUTER_URL, data=body, method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://anticipy.ai",
                "X-Title": "Anticipy Action Planner",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not text:
                return "", f"empty content from {model}"
            return text, ""
        except urllib.error.HTTPError as exc:
            try:
                msg = exc.read().decode("utf-8", "replace")[:200]
            except Exception:
                msg = ""
            return "", f"http {exc.code} {model}: {msg}"
        except Exception as exc:
            return "", f"{type(exc).__name__}: {exc}"

    def _parse_step(self, text: str, *, model: str) -> PlannerStep | None:
        if not text:
            return None
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned,
                              flags=re.IGNORECASE)
        try:
            obj = json.loads(cleaned)
        except Exception:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if not match:
                return None
            try:
                obj = json.loads(match.group(0))
            except Exception:
                return None
        if not isinstance(obj, dict):
            return None
        primitive = str(obj.get("primitive") or "").strip()
        if primitive not in self.PRIMITIVES:
            return None
        args = obj.get("args") or {}
        if not isinstance(args, dict):
            args = {}
        why = str(obj.get("why") or "")[:240]
        return PlannerStep(primitive=primitive, args=args, why=why,
                           model=model, raw=obj)


__all__ = ["ActionPlanner", "PlannerStep", "TEXT_CASCADE", "VISION_MODEL"]
