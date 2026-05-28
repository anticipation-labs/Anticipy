#!/usr/bin/env python3
"""Validate generated stranger persona/script hard-category contracts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable


HARD_CATEGORY_ALIASES = {
    "canvas": (
        "canvas",
        "canvas based design",
        "canvas design",
        "design tool",
        "design tools",
    ),
    "crm": (
        "crm",
        "customer relationship",
        "enterprise saas",
        "enterprise software",
        "salesforce",
        "hubspot",
    ),
    "ecommerce": (
        "e commerce",
        "ecommerce",
        "online shopping",
        "bot protection",
        "retail checkout",
    ),
    "native": (
        "native",
        "native mac",
        "mac app",
        "desktop app",
    ),
    "ambient": (
        "ambient",
        "ambient only",
        "no explicit utterance",
        "silent context",
    ),
}

SURFACE_EVIDENCE = {
    "canvas": (
        "canva",
        "figma",
        "figjam",
        "miro",
        "adobe express",
        "photoshop",
        "illustrator",
        "photopea",
        "sketch",
    ),
    "crm": (
        "salesforce",
        "hubspot",
        "pipedrive",
        "zoho",
        "zendesk",
        "freshsales",
        "close.com",
        "attio",
        "servicenow",
        "workday",
        "gong",
        "outreach",
        "jira",
        "linear",
        "asana",
        "airtable",
        "monday.com",
        "notion",
    ),
    "ecommerce": (
        "amazon",
        "shopify",
        "ebay",
        "etsy",
        "walmart",
        "target",
        "best buy",
        "costco",
        "ticketmaster",
        "stubhub",
        "instacart",
        "doordash",
        "uber eats",
        "apple store",
        "nike",
        "stripe checkout",
        "paypal checkout",
    ),
    "native": (
        "apple mail",
        "mail.app",
        "calendar.app",
        "notes.app",
        "messages.app",
        "finder",
        "preview",
        "textedit",
        "numbers.app",
        "pages.app",
        "keynote.app",
        "reminders.app",
        "system settings",
        "terminal.app",
        "safari.app",
        " mac mail",
        " mac calendar",
        " mac notes",
    ),
}

PLACEHOLDER_PATTERNS = (
    r"\bbrowser crm-style note\b",
    r"\bbrowser order follow-up\b",
    r"\bbrowser note standing in for a native app handoff\b",
    r"\blocal user-visible receipt surface\b",
    r"\breceipt_capture\b",
    r"\bsurface_receipt\.json\b",
    r"\bsurface\.html\b",
    r"\blocal receipt page\b",
    r"\blocal html receipt\b",
    r"\bplaceholder hard categor(?:y|ies)\b",
    r"\bfixture surface\b",
    r"\bmock surface\b",
    r"\bfake surface\b",
    r"\bstand-in surface\b",
    r"\bstanding in for\b",
    r"\blocalhost\b",
    r"\b127\.0\.0\.1\b",
    r"\bdata:text/html\b",
)

AMBIENT_PATTERNS = (
    r"\bambient\b",
    r"\bstays silent\b",
    r"\bstay silent\b",
    r"\bsilent while context changes\b",
    r"\bno explicit utterance\b",
    r"\bwithout (?:a )?(?:spoken )?prompt\b",
    r"\bcontext changes\b",
)

MOMENT_KEYS = ("moments", "script", "steps", "sequence")
UPLOADED_AUDIO_INPUT_FIDELITIES = {
    "audio_upload",
    "mp3_upload",
    "uploaded_audio",
}
UPLOADED_AUDIO_MOMENT_KINDS = {
    "audio_upload",
    "mp3_upload",
    "upload_audio",
    "uploads_audio",
}
TRANSCRIPT_AUDIT_AUDIO_VERDICTS = {"fail", "no_data"}


def load_json(path: Path) -> Any:
    path = resolve_input_path(path)
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        raise ValueError(f"{path} does not exist") from None
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc


def resolve_input_path(path: Path) -> Path:
    if path.exists() or path.is_absolute():
        return path
    cwd = Path.cwd().resolve()
    for parent in (cwd, *cwd.parents):
        if parent.name == ".worktrees":
            shared_path = parent.parent / path
            if shared_path.exists():
                return shared_path
            break
    return path


def iter_text(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from iter_text(item)
    elif isinstance(value, list):
        for item in value:
            yield from iter_text(item)
    elif isinstance(value, (str, int, float, bool)) and value is not None:
        yield str(value)


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9.]+", " ", text.lower()).strip()


def contains_phrase(haystack: str, phrase: str) -> bool:
    phrase = normalize(phrase)
    return bool(re.search(rf"(?<![a-z0-9.]){re.escape(phrase)}(?![a-z0-9.])", haystack))


def collect_category_values(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = normalize(str(key))
            if ("hard" in key_text and "categor" in key_text) or key_text in {
                "hard category focus",
                "hard category",
                "primary hard category",
            }:
                found.extend(str(part) for part in iter_text(item))
            else:
                found.extend(collect_category_values(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(collect_category_values(item))
    return found


def canonical_category(value: str) -> str | None:
    text = normalize(value)
    for category, aliases in HARD_CATEGORY_ALIASES.items():
        if any(contains_phrase(text, alias) for alias in aliases):
            return category
    return None


def find_moments(script: Any) -> list[Any]:
    if isinstance(script, list):
        return script
    if isinstance(script, dict):
        for key in MOMENT_KEYS:
            value = script.get(key)
            if isinstance(value, list):
                return value
    return []


def audit_requires_audio_asr(audit: Any) -> bool:
    if not isinstance(audit, dict):
        return False
    verdict = str(audit.get("verdict", "")).strip().lower().replace("-", "_").replace(" ", "_")
    return verdict in TRANSCRIPT_AUDIT_AUDIO_VERDICTS


def moment_has_uploaded_audio_asr(moment: Any) -> bool:
    if not isinstance(moment, dict):
        return False

    kind = str(moment.get("kind", "")).lower()

    fidelity = moment.get("input_fidelity")
    if isinstance(fidelity, str):
        fidelities = {fidelity.lower()}
    elif isinstance(fidelity, list):
        fidelities = {str(item).lower() for item in fidelity}
    else:
        fidelities = set()
    return kind in UPLOADED_AUDIO_MOMENT_KINDS and bool(
        fidelities & UPLOADED_AUDIO_INPUT_FIDELITIES
    )


def has_uploaded_audio_asr_coverage(script: Any) -> bool:
    return any(moment_has_uploaded_audio_asr(moment) for moment in find_moments(script))


def has_surface_evidence(category: str, full_text: str) -> bool:
    return any(contains_phrase(full_text, term) for term in SURFACE_EVIDENCE.get(category, ()))


def has_ambient_evidence(moments: list[Any], full_text: str) -> bool:
    moment_text = "\n".join(" ".join(iter_text(moment)) for moment in moments)
    text = normalize(f"{full_text}\n{moment_text}")
    return any(re.search(pattern, text) for pattern in AMBIENT_PATTERNS)


def validate(persona: Any, script: Any, transcript_audit: Any | None = None) -> list[str]:
    errors: list[str] = []
    full_text = normalize("\n".join(iter_text({"persona": persona, "script": script})))

    for pattern in PLACEHOLDER_PATTERNS:
        if re.search(pattern, full_text):
            errors.append(f"placeholder surface is forbidden: {pattern}")

    category_values = collect_category_values(persona) + collect_category_values(script)
    if not category_values:
        errors.append("missing explicit hard-category focus")

    categories: list[str] = []
    unknown_values: list[str] = []
    for value in category_values:
        category = canonical_category(value)
        if category and category not in categories:
            categories.append(category)
        elif not category:
            unknown_values.append(value)

    if category_values and not categories:
        errors.append(
            "hard-category focus is not one of canvas, CRM, e-commerce, native, or ambient"
        )
    elif unknown_values and len(unknown_values) == len(category_values):
        errors.append(f"unrecognized hard-category values: {', '.join(unknown_values)}")

    moments = find_moments(script)
    if not moments:
        errors.append("script must contain a non-empty moments/script/steps/sequence list")

    for category in categories:
        if category == "ambient":
            if not has_ambient_evidence(moments, full_text):
                errors.append("ambient hard category must include a silent/context-change moment")
            continue
        if not has_surface_evidence(category, full_text):
            errors.append(f"{category} hard category lacks a real matching user surface")

    if audit_requires_audio_asr(transcript_audit) and not has_uploaded_audio_asr_coverage(script):
        errors.append(
            "transcript audit is no_data/fail; next script must include "
            "kind upload_audio with input_fidelity uploaded_audio"
        )

    return errors


def latest_pair(root: Path) -> tuple[Path, Path]:
    root = resolve_input_path(root)
    pairs: list[tuple[float, Path, Path]] = []
    for persona in root.glob("*/persona.json"):
        script = persona.parent / "script.json"
        if script.exists():
            pairs.append((max(persona.stat().st_mtime, script.stat().st_mtime), persona, script))
    if not pairs:
        raise ValueError(f"no persona.json/script.json pairs found under {root}")
    _, persona, script = max(pairs, key=lambda item: item[0])
    return persona, script


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate that a generated stranger uses a real V6 hard category surface."
    )
    parser.add_argument("persona", nargs="?", type=Path)
    parser.add_argument("script", nargs="?", type=Path)
    parser.add_argument(
        "--latest",
        type=Path,
        help="Validate the newest persona.json/script.json pair under this strangers directory.",
    )
    parser.add_argument(
        "--transcript-audit",
        type=Path,
        help=(
            "When the last transcript audit is no_data or fail, require the script "
            "to exercise real audio ASR instead of transcript paste fidelity."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.latest:
        try:
            persona_path, script_path = latest_pair(args.latest)
        except ValueError as exc:
            print(f"stranger contract invalid: {exc}", file=sys.stderr)
            return 1
    elif args.persona and args.script:
        persona_path, script_path = args.persona, args.script
    else:
        print("usage: validate_stranger_contract.py PERSONA SCRIPT", file=sys.stderr)
        print("   or: validate_stranger_contract.py --latest state/strangers", file=sys.stderr)
        return 2

    try:
        persona = load_json(persona_path)
        script = load_json(script_path)
        transcript_audit = load_json(args.transcript_audit) if args.transcript_audit else None
    except ValueError as exc:
        print(f"stranger contract invalid: {exc}", file=sys.stderr)
        return 1

    errors = validate(persona, script, transcript_audit)
    if errors:
        print(
            f"stranger contract invalid for {persona_path} and {script_path}:",
            file=sys.stderr,
        )
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"stranger contract valid: {persona_path} {script_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
