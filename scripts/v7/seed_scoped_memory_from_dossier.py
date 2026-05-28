"""Seed V7 scoped memory from ~/.anticipy/dossier.json.

One-shot CLI. Reads the local dossier (people, preferences, aliases,
do-not-touch) and writes them into the account/device scoped store
via `ScopedMemory`. Idempotent: re-running with the same dossier will
deactivate prior matching keys and re-add with the latest values (the
`write(dedupe=True)` contract).

Usage:

  python scripts/v7/seed_scoped_memory_from_dossier.py \
      --account-id <account_id> \
      --device-id <device_id> \
      [--dossier ~/.anticipy/dossier.json]

Exits 0 on success even if the dossier is empty or missing (so the
loop can call it unconditionally during onboarding).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow direct execution: `python scripts/v7/seed_scoped_memory_from_dossier.py`
_ROOT = Path(__file__).resolve().parents[2]
_ENGINE = _ROOT / "engine"
if str(_ENGINE) not in sys.path:
    sys.path.insert(0, str(_ENGINE))

from app.product.scoped_memory import (  # noqa: E402
    KIND_ALIAS,
    KIND_DO_NOT_TOUCH,
    KIND_PERSON,
    KIND_PREFERENCE,
    ScopedMemory,
)


def _load_dossier(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"warn: failed to parse dossier at {path}: {exc}",
              file=sys.stderr)
        return {}


def _iter_people(dossier: dict):
    """Normalize people from several known dossier shapes."""
    people = dossier.get("people")
    if isinstance(people, dict):
        for relation, info in people.items():
            if isinstance(info, str):
                yield {"name": info, "role": relation}
            elif isinstance(info, dict):
                yield {
                    "name": info.get("name") or relation,
                    "email": info.get("email"),
                    "role": info.get("role") or relation,
                    "gender": info.get("gender"),
                }
    elif isinstance(people, list):
        for p in people:
            if isinstance(p, dict) and p.get("name"):
                yield p


def _iter_preferences(dossier: dict):
    prefs = dossier.get("preferences")
    if isinstance(prefs, dict):
        for k, v in prefs.items():
            yield {"key": str(k), "value": "" if v is None else str(v)}
    elif isinstance(prefs, list):
        for p in prefs:
            if isinstance(p, dict) and p.get("key"):
                yield {"key": str(p["key"]),
                       "value": "" if p.get("value") is None else str(p["value"])}


def _iter_aliases(dossier: dict):
    aliases = dossier.get("aliases")
    if isinstance(aliases, dict):
        for alias, target in aliases.items():
            yield {"alias": str(alias), "target": str(target)}
    elif isinstance(aliases, list):
        for a in aliases:
            if isinstance(a, dict) and a.get("alias") and a.get("target"):
                yield {"alias": str(a["alias"]), "target": str(a["target"])}


def _iter_do_not_touch(dossier: dict):
    raw = dossier.get("do_not_touch") or dossier.get("doNotTouch") or []
    if isinstance(raw, list):
        for item in raw:
            if item:
                yield str(item)
    elif isinstance(raw, dict):
        for k in raw:
            if k:
                yield str(k)


def seed(scope: ScopedMemory, dossier: dict) -> dict:
    counts = {"people": 0, "preferences": 0, "aliases": 0, "do_not_touch": 0}
    for p in _iter_people(dossier):
        scope.write(
            kind=KIND_PERSON,
            key=p["name"],
            value=p.get("email") or p["name"],
            source="dossier",
            provenance="seed_from_dossier",
            extra={
                "email": p.get("email") or "",
                "role": p.get("role") or "",
                "gender": str(p.get("gender") or "").lower(),
            },
        )
        counts["people"] += 1

    for pref in _iter_preferences(dossier):
        scope.write(
            kind=KIND_PREFERENCE,
            key=pref["key"],
            value=pref["value"],
            source="dossier",
            provenance="seed_from_dossier",
        )
        counts["preferences"] += 1

    for al in _iter_aliases(dossier):
        scope.write(
            kind=KIND_ALIAS,
            key=al["alias"],
            value=al["target"],
            source="dossier",
            provenance="seed_from_dossier",
        )
        counts["aliases"] += 1

    for dnt in _iter_do_not_touch(dossier):
        scope.write(
            kind=KIND_DO_NOT_TOUCH,
            key=dnt,
            value=dnt,
            source="dossier",
            provenance="seed_from_dossier",
        )
        counts["do_not_touch"] += 1

    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seed V7 scoped memory from a local dossier file.")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--device-id", required=True)
    parser.add_argument(
        "--dossier",
        default=str(Path.home() / ".anticipy" / "dossier.json"),
        help="Path to dossier JSON. Default: ~/.anticipy/dossier.json",
    )
    args = parser.parse_args(argv)

    scope = ScopedMemory(args.account_id, args.device_id)
    dossier_path = Path(args.dossier).expanduser()
    dossier = _load_dossier(dossier_path)

    if not dossier:
        print(json.dumps({
            "ok": True,
            "dossier_path": str(dossier_path),
            "dossier_found": False,
            "counts": {},
            "diag": scope.diag(),
        }))
        return 0

    counts = seed(scope, dossier)
    print(json.dumps({
        "ok": True,
        "dossier_path": str(dossier_path),
        "dossier_found": True,
        "counts": counts,
        "diag": scope.diag(),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
