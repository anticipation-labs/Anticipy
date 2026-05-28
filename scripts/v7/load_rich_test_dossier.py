"""Load the rich V7 test dossier into the running engine.

This is the loader for ``state/v7/test_dossier_rich.json``. It exercises
the memory pipeline rather than just writing a file: it POSTs into every
live engine endpoint that can ingest a dossier, then falls back to the
canonical disk locations the V7 dossier-active loader reads from when
those endpoints are not yet wired up on the packaged engine.

Why both: per ``state/v7/packaged_engine_fix_notes.md`` the packaged
Anticipy.app currently serves the legacy ``/api/dossier`` and
``/api/dossier/write`` endpoints as HTTP 410 (the dossier_store module
is missing from the bundle), and the M1 routes (``/api/dossier/active``,
``/api/dossier/refresh``, ``/api/dossier/context``) plus the scoped
memory routes (``/api/memory/seed``, ``/api/memory/write``) live in
source but failed to attach in the packaged build. Restarting the
engine is not allowed by the parent task. So this loader tries every
live HTTP entrypoint first, then guarantees on-disk presence in the
exact paths the V7 dossier-active loader will read once those routes
come online. Whichever key wins, the rich dossier is there.

The dossier is written under the account_id namespace
``e2e_rich_test_2026_05_28`` so the existing 46 verified strangers and
the legacy ``USER_ID`` dossier are untouched.

Usage:

  python scripts/v7/load_rich_test_dossier.py
      [--engine http://127.0.0.1:8731]
      [--dossier state/v7/test_dossier_rich.json]
      [--account-id e2e_rich_test_2026_05_28]
      [--device-id macbook_e2e_rich_2026_05_28]

Exit 0 if at least one ingest path succeeded (HTTP or disk).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DOSSIER = _ROOT / "state" / "v7" / "test_dossier_rich.json"
DEFAULT_ENGINE = os.environ.get(
    "ANTICIPY_ENGINE_URL", "http://127.0.0.1:8731"
).rstrip("/")
DEFAULT_ACCOUNT = "e2e_rich_test_2026_05_28"
DEFAULT_DEVICE = "macbook_e2e_rich_2026_05_28"


def _post_json(url: str, payload: dict, timeout: float = 30.0) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8") or "{}"
            return {
                "ok": True,
                "status": r.status,
                "body": json.loads(raw) if raw else {},
            }
    except urllib.error.HTTPError as exc:
        try:
            err_body = exc.read().decode("utf-8") or ""
            err_json = json.loads(err_body) if err_body else {}
        except Exception:
            err_json = {"raw_error": str(exc)}
        return {
            "ok": False, "status": exc.code,
            "body": err_json, "error": str(exc),
        }
    except Exception as exc:
        return {"ok": False, "status": 0, "error": str(exc)}


def _get_json(url: str, timeout: float = 10.0) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            raw = r.read().decode("utf-8") or "{}"
            return {
                "ok": True, "status": r.status,
                "body": json.loads(raw) if raw else {},
            }
    except urllib.error.HTTPError as exc:
        try:
            err_body = exc.read().decode("utf-8") or ""
            err_json = json.loads(err_body) if err_body else {}
        except Exception:
            err_json = {"raw_error": str(exc)}
        return {
            "ok": False, "status": exc.code,
            "body": err_json, "error": str(exc),
        }
    except Exception as exc:
        return {"ok": False, "status": 0, "error": str(exc)}


def _try_dossier_active(engine: str, account_id: str) -> dict:
    """M1 readback. If the router is wired, GET returns the snapshot."""
    url = f"{engine}/api/dossier/active?account_id={account_id}"
    return _get_json(url)


def _try_memory_seed(
    engine: str, account_id: str, device_id: str, dossier: dict,
) -> dict:
    """Try the V7 scoped-memory seed endpoint (canonical product write)."""
    people_payload = []
    for p in dossier.get("people", []):
        people_payload.append({
            "name": p.get("name", ""),
            "email": p.get("email", ""),
            "role": p.get("role", ""),
            "gender": "f" if "she" in (p.get("pronouns") or "").lower()
                     else ("m" if "he" in (p.get("pronouns") or "").lower()
                           else ""),
        })
    prefs_payload = [
        {"key": k, "value": str(v)}
        for k, v in (dossier.get("preferences") or {}).items()
    ]
    aliases_payload = [
        {"alias": k, "target": v}
        for k, v in (dossier.get("aliases") or {}).items()
    ]
    dnt_payload = []
    for d in (dossier.get("do_not_touch") or []):
        if isinstance(d, dict):
            dnt_payload.append(d.get("pattern", ""))
        else:
            dnt_payload.append(str(d))
    payload = {
        "account_id": account_id,
        "device_id": device_id,
        "people": people_payload,
        "preferences": prefs_payload,
        "aliases": aliases_payload,
        "do_not_touch": [x for x in dnt_payload if x],
        "source": "rich_test_dossier_2026_05_28",
    }
    return _post_json(f"{engine}/api/memory/seed", payload)


def _try_memory_provision(
    engine: str, account_id: str, device_id: str,
) -> dict:
    payload = {
        "account_id": account_id,
        "device_id": device_id,
        "build_id": "rich_test_dossier_v1",
        "site_url": "",
    }
    return _post_json(f"{engine}/api/memory/provision", payload)


def _try_memory_write_each(
    engine: str, account_id: str, device_id: str, dossier: dict,
) -> dict:
    """Per-row write for projects, recurring patterns, places. These do not
    map to the basic seed kinds; we write them via the generic write
    endpoint so they live in scoped memory as typed rows."""
    out = {"projects": 0, "recurring_patterns": 0, "places": 0,
           "errors": []}
    rows = []
    for proj in (dossier.get("projects") or []):
        rows.append(("project", proj.get("name", ""),
                     json.dumps(proj, ensure_ascii=False)))
    for pat in (dossier.get("recurring_patterns") or []):
        rows.append(("recurring_pattern", pat.get("name", ""),
                     json.dumps(pat, ensure_ascii=False)))
    places = (dossier.get("places") or {})
    for pl in (places.get("named_places") or []):
        rows.append(("place_named", pl.get("name", ""),
                     json.dumps(pl, ensure_ascii=False)))
    for loc in (places.get("frequented_locations") or []):
        rows.append(("place_frequented", loc.get("name", ""),
                     json.dumps(loc, ensure_ascii=False)))

    for kind, key, value in rows:
        if not key:
            continue
        res = _post_json(f"{engine}/api/memory/write", {
            "account_id": account_id,
            "device_id": device_id,
            "kind": kind,
            "key": key,
            "value": value,
            "source": "rich_test_dossier_2026_05_28",
            "provenance": "load_rich_test_dossier",
            "dedupe": True,
        })
        if res.get("ok"):
            if kind == "project":
                out["projects"] += 1
            elif kind == "recurring_pattern":
                out["recurring_patterns"] += 1
            else:
                out["places"] += 1
        else:
            out["errors"].append({
                "kind": kind, "key": key,
                "status": res.get("status"),
                "error": res.get("error") or res.get("body"),
            })
            if len(out["errors"]) > 3:
                break
    return out


def _disk_targets(account_id: str) -> list[Path]:
    """The exact paths the V7 dossier-active loader scans, in priority
    order. See engine/app/product/dossier_active_loader.py _candidate_paths.
    """
    home = Path.home()
    return [
        home / ".anticipy" / "v7" / "dossiers" / account_id / "dossier.json",
        home / ".anticipy" / "v7" / "dossiers" / account_id
             / "rich_dossier.json",
    ]


def _write_disk_fallback(dossier: dict, account_id: str) -> dict:
    """Place the dossier where the V7 loader will find it once registered.
    Account-scoped only, never touching the global USER_ID file or the
    pre-V7 ``~/.anticipy/dossier.json`` so existing strangers remain
    valid. Idempotent: rewriting refreshes the timestamp.
    """
    written: list[str] = []
    for target in _disk_targets(account_id):
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                json.dumps(dossier, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            written.append(str(target))
        except Exception as exc:
            return {"ok": False, "error": f"{target}: {exc}",
                    "written": written}
    return {"ok": True, "written": written}


def _try_legacy_dossier_write(
    engine: str, user_id: str, dossier: dict,
) -> dict:
    """Last-ditch path. The packaged engine returns HTTP 410 here, but if
    a future build re-enables dossier_store we want to still seed it.
    Writes a single 'rich_profile' key holding the whole dossier dict.
    """
    return _post_json(f"{engine}/api/dossier/write", {
        "user_id": user_id,
        "key": "rich_profile",
        "value": dossier,
    })


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", default=DEFAULT_ENGINE)
    parser.add_argument("--dossier", default=str(DEFAULT_DOSSIER))
    parser.add_argument("--account-id", default=DEFAULT_ACCOUNT)
    parser.add_argument("--device-id", default=DEFAULT_DEVICE)
    parser.add_argument("--report", default="")
    args = parser.parse_args(argv)

    dossier_path = Path(args.dossier).expanduser()
    if not dossier_path.exists():
        print(json.dumps({"ok": False,
                          "error": f"dossier not found at {dossier_path}"}))
        return 2
    dossier = json.loads(dossier_path.read_text(encoding="utf-8"))

    started = time.time()
    report = {
        "ok": False,
        "engine": args.engine,
        "account_id": args.account_id,
        "device_id": args.device_id,
        "dossier_source": str(dossier_path),
        "counts": {
            "people": len(dossier.get("people", [])),
            "projects": len(dossier.get("projects", [])),
            "recurring_patterns": len(
                dossier.get("recurring_patterns", [])
            ),
            "preferences": len(dossier.get("preferences", {})),
            "named_places": len(
                (dossier.get("places") or {}).get("named_places", [])
            ),
            "frequented_locations": len(
                (dossier.get("places") or {}).get(
                    "frequented_locations", []
                )
            ),
            "do_not_touch": len(dossier.get("do_not_touch", [])),
            "aliases": len(dossier.get("aliases", {})),
            "recent_topics": len(dossier.get("recent_topics", [])),
        },
        "steps": [],
    }

    # 1. probe engine health first; if it is dead, only disk write remains.
    health = _get_json(f"{args.engine}/health", timeout=4.0)
    report["steps"].append({"step": "health", "result": health})

    # 2. probe whether the M1 reader is alive.
    pre_active = _try_dossier_active(args.engine, args.account_id)
    report["steps"].append({"step": "pre_dossier_active",
                            "result": pre_active})

    # 3. try memory provision + seed (scoped product write surface).
    prov = _try_memory_provision(args.engine, args.account_id,
                                 args.device_id)
    report["steps"].append({"step": "memory_provision", "result": prov})
    seed = _try_memory_seed(args.engine, args.account_id,
                            args.device_id, dossier)
    report["steps"].append({"step": "memory_seed", "result": seed})

    # 4. extended write: projects, recurring patterns, places.
    if seed.get("ok"):
        extra = _try_memory_write_each(args.engine, args.account_id,
                                       args.device_id, dossier)
        report["steps"].append({"step": "memory_write_extras",
                                "result": extra})

    # 5. legacy dossier/write path. Almost certainly 410 today.
    legacy = _try_legacy_dossier_write(args.engine, args.account_id,
                                       dossier)
    report["steps"].append({"step": "legacy_dossier_write",
                            "result": legacy})

    # 6. disk fallback. The dossier loader reads
    # ``~/.anticipy/v7/dossiers/<account_id>/dossier.json`` first. Write
    # under our account_id namespace so we never trample existing data.
    disk = _write_disk_fallback(dossier, args.account_id)
    report["steps"].append({"step": "disk_fallback", "result": disk})

    # 7. readback via M1 active loader (will work once routes attach).
    post_active = _try_dossier_active(args.engine, args.account_id)
    report["steps"].append({"step": "post_dossier_active",
                            "result": post_active})

    ingest_ok = (
        seed.get("ok") or legacy.get("ok") or disk.get("ok")
    )
    report["ok"] = bool(ingest_ok)
    report["elapsed_s"] = round(time.time() - started, 2)
    report["readback_loaded"] = bool(
        (post_active.get("body") or {}).get("loaded")
    )
    print(json.dumps(report, indent=2))

    if args.report:
        Path(args.report).write_text(
            json.dumps(report, indent=2), encoding="utf-8",
        )

    return 0 if ingest_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
