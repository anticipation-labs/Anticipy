"""
Observation compression + prompt formatting.
The core IP — makes cheap models work well by constraining the action space.
"""

from __future__ import annotations

import random

from app.config import MAX_LABELED_ELEMENTS, MEMORY_MAX_CHARS

# Labels A through O (15 max)
LABELS = [chr(ord("A") + i) for i in range(MAX_LABELED_ELEMENTS)]

SYSTEM_PROMPT = """You are a browser automation agent. You see labeled interactive elements on a web page and pick one action.

RULES:
- Output ONLY valid JSON. No explanation, no markdown.
- Format: {"action":"<ACTION>","target":"<LABEL>","value":null}
- ACTION is one of: click, type, select, scroll, navigate, done, stuck, need_info
- TARGET is a single letter label (A-O) from the element list, or null for scroll/done/stuck/need_info
- VALUE is the text to type (for type/select/navigate actions), or null
- For navigate: target is null, value is the full URL
- For scroll: target is null, value is "up" or "down"
- For done: target is null, value is a plain English answer/summary of what was accomplished (if the goal asked for information, include the answer here)
- For stuck: target and value are both null
- For need_info: target is null, value describes what info you need
- If you can see the answer to the user's question in the PAGE TEXT, use done immediately with the answer as value
- Pick exactly ONE action per response."""


# Valid actions for validation
VALID_ACTIONS = {"click", "type", "select", "scroll", "navigate", "done", "stuck", "need_info"}


def extract_interactive_elements(tree: dict | None) -> list[dict]:
    """
    Walk the accessibility tree and extract interactive elements.
    Returns a list of dicts with 'label', 'role', 'name', and 'node' keys.
    Limited to MAX_LABELED_ELEMENTS. Labels are randomized to prevent position bias (V43).
    """
    if not tree:
        return []

    interactive_roles = {
        "link",
        "button",
        "textbox",
        "combobox",
        "listbox",
        "menuitem",
        "menuitemcheckbox",
        "menuitemradio",
        "option",
        "radio",
        "checkbox",
        "searchbox",
        "spinbutton",
        "slider",
        "switch",
        "tab",
        "treeitem",
    }

    # Names to skip — common nav/meta elements that waste label slots
    skip_names = {
        "jump to content", "skip to content", "main menu", "search",
        "log in", "create account", "sign in", "sign up", "donate",
        "view source", "view history", "talk", "read", "tools",
        "appearance", "hide", "show",
    }

    all_elements: list[dict] = []

    def walk(node: dict) -> None:
        role = (node.get("role") or "").lower()
        name = (node.get("name") or "").strip()
        if role in interactive_roles and name:
            all_elements.append(
                {
                    "role": role,
                    "name": name[:80],
                    "node": node,
                }
            )
        for child in node.get("children", []):
            walk(child)

    walk(tree)

    # Prioritize elements by likely importance
    # Forms/inputs first, then buttons, then content links, then nav links
    forms = []      # textbox, combobox, searchbox, checkbox, radio, select
    buttons = []    # button, submit
    content_links = []  # links with longer/unique names (likely content)
    nav_links = []  # short generic links (likely navigation)

    form_roles = {"textbox", "searchbox", "combobox", "listbox", "checkbox",
                  "radio", "spinbutton", "slider", "switch"}
    # option elements are low priority — they're dropdown choices, not primary inputs
    option_role = {"option"}

    # Track seen names to deduplicate
    seen_names = set()

    seen_button_count = {}  # track how many same-named buttons we keep

    for elem in all_elements:
        name_lower = elem["name"].lower()
        if name_lower in skip_names or len(elem["name"]) < 2:
            continue

        role = elem["role"]

        # Deduplicate links by name (nav links are truly duplicate)
        # But allow up to 3 same-named buttons (e.g., multiple "Add to cart")
        if role in ("link",):
            if name_lower in seen_names:
                continue
            seen_names.add(name_lower)
        elif role == "button":
            count = seen_button_count.get(name_lower, 0)
            if count >= 3:
                continue
            seen_button_count[name_lower] = count + 1
        else:
            if name_lower in seen_names:
                continue
            seen_names.add(name_lower)

        if role in form_roles:
            forms.append(elem)
        elif role == "button":
            buttons.append(elem)
        elif role in option_role:
            nav_links.append(elem)  # options go to lowest priority
        elif role == "link":
            # Heuristic: content links tend to be longer or contain numbers/special chars
            # Nav links tend to be short single words (category names)
            if len(elem["name"]) > 25 or any(c in elem["name"] for c in "0123456789£$€@#"):
                content_links.append(elem)
            else:
                nav_links.append(elem)
        else:
            content_links.append(elem)

    # Balanced assembly: ensure each category gets representation
    # Allocate: forms (all), buttons (up to 3), content links (up to 8), nav links (rest)
    selected_forms = forms[:MAX_LABELED_ELEMENTS]
    remaining = MAX_LABELED_ELEMENTS - len(selected_forms)
    selected_buttons = buttons[:min(3, remaining)]
    remaining -= len(selected_buttons)
    selected_content = content_links[:min(8, remaining)]
    remaining -= len(selected_content)
    selected_nav = nav_links[:remaining]
    combined = selected_forms + selected_buttons + selected_content + selected_nav

    # Assign stable labels (no shuffle — model needs consistent labels across steps)
    results: list[dict] = []
    for elem in combined:
        elem["label"] = LABELS[len(results)]
        results.append(elem)

    return results


def format_elements(elements: list[dict]) -> str:
    """Format labeled elements into a compact string for the prompt."""
    lines = []
    for elem in elements:
        lines.append(f"[{elem['label']}] {elem['role']}: {elem['name']}")
    return "\n".join(lines)


def compress_memory(memory: list[str]) -> str:
    """
    Keep a compressed memory of actions taken.
    Prunes oldest entries to stay under MEMORY_MAX_CHARS (V36).
    """
    combined = " | ".join(memory)
    if len(combined) <= MEMORY_MAX_CHARS:
        return combined
    # Keep only the most recent entries that fit
    trimmed: list[str] = []
    total = 0
    for entry in reversed(memory):
        if total + len(entry) + 3 > MEMORY_MAX_CHARS:
            break
        trimmed.insert(0, entry)
        total += len(entry) + 3
    return " | ".join(trimmed)


def validate_action(action: dict, elements: list[dict]) -> dict | None:
    """
    Validate that a model-produced action is well-formed and targets exist (V41).
    Returns the action if valid, None if invalid.
    """
    if not isinstance(action, dict):
        return None

    act = action.get("action", "")
    if act not in VALID_ACTIONS:
        return None

    target = action.get("target")

    # Actions that require a target label
    if act in ("click", "type", "select"):
        if not target:
            return None
        # Validate target exists in elements
        valid_labels = {e.get("label") for e in elements}
        if target not in valid_labels:
            return None

    # Type and select require a value
    if act in ("type", "select") and action.get("value") is None:
        return None

    # Navigate requires a value (URL)
    if act == "navigate" and not action.get("value"):
        return None

    return action


def format_prompt(
    goal: str,
    url: str,
    elements: list[dict],
    memory: list[str],
    step: int,
    max_steps: int,
    page_text: str = "",
    sub_goals: list[str] | None = None,
    current_sub_goal_idx: int = 0,
) -> list[dict]:
    """
    Build the complete message list for the LLM.
    Kept under ~800 tokens by aggressive compression.
    Includes original goal unchanged (V35) and current sub-goal tracking (V37).
    """
    elements_text = format_elements(elements)
    memory_text = compress_memory(memory) if memory else "none"

    # Include page text excerpt — prioritize content with prices/data
    text_snippet = ""
    if page_text:
        # Find the most useful section: look for prices, numbers, data
        content = page_text
        # Try to find where the main content starts (after nav)
        best_start = 0
        for marker in ["£", "$", "€", "price", "Price", "stock", "rating", "star",
                        "results", "Results", "showing", "items", "products"]:
            idx = content.find(marker)
            if idx > 50:
                # Go back a bit to capture context
                best_start = max(0, idx - 200)
                break
        if best_start > 0:
            content = content[best_start:]
        text_snippet = f"\nPAGE TEXT (excerpt): {content[:1200]}\n"

    # Sub-goal tracking (V37)
    sub_goal_text = ""
    if sub_goals and len(sub_goals) > 0:
        idx = min(current_sub_goal_idx, len(sub_goals) - 1)
        sub_goal_text = f"\nCURRENT STEP: {sub_goals[idx]} (step {idx + 1} of {len(sub_goals)})\n"

    # Include original goal unchanged (V35) — never truncate or modify
    user_msg = f"""GOAL: {goal}
URL: {url[:120]}
STEP: {step}/{max_steps}
HISTORY: {memory_text}{sub_goal_text}{text_snippet}
ELEMENTS:
{elements_text}

Pick ONE action as JSON. If you already have enough information to answer the user's question, use {{"action":"done","target":null,"value":"<your answer here>"}}."""

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]


def describe_action(action: dict) -> str:
    """Human-readable one-liner for an action dict."""
    act = action.get("action", "unknown")
    target = action.get("target")
    value = action.get("value")
    if act == "click" and target:
        return f"click [{target}]"
    if act == "type" and target and value:
        return f"type '{value[:30]}' into [{target}]"
    if act == "select" and target and value:
        return f"select '{value[:30]}' in [{target}]"
    if act == "scroll":
        return f"scroll {value or 'down'}"
    if act == "navigate" and value:
        return f"navigate to {value[:60]}"
    if act == "done":
        return "task completed"
    if act == "stuck":
        return "got stuck"
    if act == "need_info":
        return f"needs info: {value or ''}"[:60]
    return f"{act} {target or ''} {value or ''}".strip()
