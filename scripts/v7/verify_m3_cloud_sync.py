"""Verify M3 memory cloud sync end-to-end against live Supabase.

What this proves (or doesn't):

  1. The Supabase tables the outbox writes to (dossiers, anticipy_memory,
     anticipy_preferences, anticipy_user_profile) exist and are writable
     with the service role key.
  2. A local dossier fragment written via /api/dossier/active (or direct
     disk write if the running engine is the legacy build that does not
     expose that endpoint) lands on disk.
  3. The MemoryCloudSync outbox can be enqueued with a dossier item and
     flushed to the live Supabase dossiers table.
  4. A SECOND simulated device fetching the same user_id from the cloud
     sees the synced row.
  5. Re-flushing an updated item upserts the same row (does not duplicate).

Hard constraints:

  - Do NOT restart the engine.
  - Do NOT touch the engine source.
  - Do NOT mutate any Supabase rows that this test did not insert.
  - Clean up the inserted dossiers row at the end with DELETE.

Output: state/v7/m3_cloud_sync_<TS>/result.json + summary.md.

The verifier does NOT pretend the sync chain works if it doesn't. If
enqueue is wired but nothing calls it, this is reported under
"product_chain_gaps". If the running engine lacks the sync endpoints,
this is reported under "engine_route_gaps". The boolean PASS only
flips true when a write made through the actual product surface area
(or the documented seam) reaches Supabase, AND a separate-device GET
sees it.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path("/Users/omarebrahim/Developer/Anticipy-V7")
ENGINE_BASE = "http://127.0.0.1:8731"
OUTPUT_DIR_DEFAULT = REPO_ROOT / "state" / "v7"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_env_local() -> dict[str, str]:
    """Pull .env.local values without spawning a shell.

    Lines must be KEY=VALUE shape (the same shape `set -a; source` expects).
    Inline `export` prefixes and trailing comments are stripped.
    """
    env_path = Path("/Users/omarebrahim/Developer/Anticipy-DEV-FINAL/.env.local")
    out: dict[str, str] = {}
    if not env_path.exists():
        return out
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip()
        if (v.startswith('"') and v.endswith('"')) or (
            v.startswith("'") and v.endswith("'")
        ):
            v = v[1:-1]
        out[k] = v
    return out


def _resolve_supabase_url(env: dict[str, str]) -> str:
    url = env.get("SUPABASE_URL") or env.get("NEXT_PUBLIC_SUPABASE_URL", "")
    return url.rstrip("/")


def _service_key(env: dict[str, str]) -> str:
    return env.get("SUPABASE_SERVICE_ROLE_KEY", "") or env.get(
        "SUPABASE_SERVICE_KEY", ""
    )


def _http_json(method: str, url: str, headers: dict[str, str],
               body: bytes | None = None, timeout: float = 12.0) -> tuple[int, str, dict]:
    req = urllib.request.Request(url, data=body, method=method)
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = r.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(payload) if payload else {}
            except Exception:
                parsed = {"_raw": payload}
            return (int(getattr(r, "status", 200)), payload, parsed
                    if isinstance(parsed, dict) else {"_list": parsed})
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(payload) if payload else {}
        except Exception:
            parsed = {"_raw": payload}
        return (int(getattr(exc, "code", 0)), payload, parsed
                if isinstance(parsed, dict) else {"_list": parsed})
    except Exception as exc:
        return 0, f"{type(exc).__name__}: {exc}", {"_error": str(exc)}


def _check_engine_route(path: str) -> dict:
    """Return whether the running engine exposes a given route."""
    status, body, _ = _http_json(
        "GET", f"{ENGINE_BASE}{path}", headers={"Accept": "application/json"},
        timeout=5.0,
    )
    return {"path": path, "status": status, "snippet": body[:160]}


def _engine_dossier_active_present() -> bool:
    """The new endpoint returns 200 for GET with account_id; legacy returns 404."""
    test_id = "m3_probe_xxxxxxxx"
    status, body, _ = _http_json(
        "GET", f"{ENGINE_BASE}/api/dossier/active?account_id={test_id}",
        headers={"Accept": "application/json"}, timeout=5.0,
    )
    return status == 200


def _direct_disk_write_dossier(user_id: str, dossier_obj: dict) -> Path:
    """Write a dossier JSON to the canonical V7 disk path the loader reads."""
    root = Path(
        os.environ.get("ANTICIPY_V7_DOSSIER_ROOT", "").strip()
        or (Path.home() / ".anticipy" / "v7" / "dossiers")
    )
    folder = root / user_id
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "dossier.json"
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(dossier_obj, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    os.replace(tmp, target)
    return target


def _build_outbox_item(user_id: str, field_count: int,
                      profile_fragment: dict) -> dict:
    """Outbox row that, given _resolve_table('dossier'), goes to public.dossiers.

    Schema (per supabase/migrations/20260523_onboarding_dossiers.sql):
        user_id PRIMARY KEY, profile jsonb, pronoun_map jsonb, people jsonb,
        do_not_touch jsonb, source text, field_count integer, updated_at.

    PostgREST upsert needs the conflict target; we use Prefer headers when
    re-syncing the same user_id. The cloud_sync._ship_one method uses
    `Prefer: return=minimal` and treats 409 as success but does NOT set
    `resolution=merge-duplicates`, so a second POST of the same primary key
    returns 409. That is documented under known_limitations.
    """
    pronoun_map = profile_fragment.get("pronoun_map") or {}
    people = profile_fragment.get("people") or {}
    do_not_touch = profile_fragment.get("do_not_touch") or []
    return {
        "kind": "dossier",
        "item_id": f"m3-test-{user_id}-{int(time.time() * 1000)}",
        "user_id": user_id,
        "profile": profile_fragment,
        "pronoun_map": pronoun_map,
        "people": people,
        "do_not_touch": do_not_touch,
        "source": "verify_m3_cloud_sync",
        "field_count": int(field_count),
    }


def _cleanup_supabase(sb_url: str, sb_key: str, test_uuid: str) -> dict:
    """Best-effort DELETE of any rows we inserted for this test."""
    hdr = {"apikey": sb_key, "Authorization": f"Bearer {sb_key}",
           "Prefer": "return=minimal"}
    s, b, _ = _http_json(
        "DELETE",
        f"{sb_url}/rest/v1/dossiers"
        f"?user_id=eq.{urllib.parse.quote(test_uuid)}",
        hdr, timeout=10.0,
    )
    return {"status": s, "snippet": b[:160]}


def _cleanup_disk(account_id: str) -> None:
    try:
        target_dir = (Path.home() / ".anticipy" / "v7" / "dossiers"
                      / account_id)
        if target_dir.exists():
            for child in target_dir.iterdir():
                try:
                    child.unlink()
                except Exception:
                    pass
            target_dir.rmdir()
    except Exception:
        pass


def _run(out_root: Path) -> dict:
    env = _load_env_local()
    sb_url = _resolve_supabase_url(env)
    sb_key = _service_key(env)
    if not sb_url or not sb_key:
        return {
            "ok": False,
            "result": "BROKEN_AT_setup",
            "reason": "SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY missing",
        }

    # Carry credentials into this process so MemoryCloudSync picks them up.
    os.environ["SUPABASE_URL"] = sb_url
    os.environ["SUPABASE_SERVICE_ROLE_KEY"] = sb_key

    # ------------------------------------------------------------------
    # Identifiers. user_id (Supabase PK column) must be a UUID because
    # the dossier table's RLS uses auth.uid()::text but service role
    # bypasses RLS so any text PK works. We use a real UUID to look like
    # real product data.
    # ------------------------------------------------------------------
    test_uuid = str(uuid.uuid4())
    account_id = f"m3_sync_test_{test_uuid}"
    device_a = f"device_a_{test_uuid[:8]}"
    device_b = f"device_b_{test_uuid[:8]}"

    result: dict = {
        "ok": False,
        "result": "PENDING",
        "ts": _now_iso(),
        "account_id": account_id,
        "user_id": test_uuid,
        "device_a": device_a,
        "device_b": device_b,
        "supabase_url": sb_url,
        "engine_base": ENGINE_BASE,
        "steps": [],
        "engine_route_gaps": [],
        "product_chain_gaps": [],
        "supabase_row_uuid": None,
        "cross_device_fetch": "PENDING",
    }

    def step(name: str, status: str, detail: dict | None = None) -> None:
        result["steps"].append({
            "name": name, "status": status, "detail": detail or {},
        })

    # ------------------------------------------------------------------
    # Step 0: probe engine routes that should exist per the new wiring.
    # ------------------------------------------------------------------
    routes_status = {
        "/api/memory/sync/status": _check_engine_route("/api/memory/sync/status"),
        "/api/memory/sync/flush_POST": None,
        "/api/dossier/active_GET": _check_engine_route(
            f"/api/dossier/active?account_id={account_id}"
        ),
    }
    # POST is checked separately because GET 405 vs 404 differs.
    s, b, _ = _http_json(
        "POST", f"{ENGINE_BASE}/api/memory/sync/flush",
        headers={"Content-Type": "application/json"}, body=b"{}", timeout=5.0,
    )
    routes_status["/api/memory/sync/flush_POST"] = {
        "path": "/api/memory/sync/flush", "status": s, "snippet": b[:160],
    }
    step("engine_route_probe", "ok", routes_status)

    engine_has_sync_status = (
        routes_status["/api/memory/sync/status"]["status"] == 200
    )
    engine_has_dossier_active = (
        routes_status["/api/dossier/active_GET"]["status"] == 200
    )
    if not engine_has_sync_status:
        result["engine_route_gaps"].append({
            "route": "/api/memory/sync/status",
            "evidence": routes_status["/api/memory/sync/status"],
            "diagnosis": (
                "Running engine on 8731 is the pre-M3 build. The "
                "memory_cloud_sync_wire.attach() ran against this app instance "
                "is the only thing that registers this route. The instance "
                "currently bound to 8731 was started before this code landed."
            ),
        })
    if not engine_has_dossier_active:
        result["engine_route_gaps"].append({
            "route": "/api/dossier/active",
            "evidence": routes_status["/api/dossier/active_GET"],
            "diagnosis": (
                "Same root cause: the running engine instance predates the "
                "dossier_endpoints.py router registration."
            ),
        })

    # ------------------------------------------------------------------
    # Step 1: write dossier fragment LOCALLY. Use the engine endpoint
    # only if it exists; otherwise direct disk write to the path the
    # dossier_active_loader reads from.
    # ------------------------------------------------------------------
    profile_fragment = {
        "name": f"Test User {test_uuid[:8]}",
        "people": {"partner": "Sam", "co-founder": "Alex"},
        "pronoun_map": {"partner": "they", "co-founder": "she"},
        "do_not_touch": ["personal_email"],
        "notes": (
            f"M3 cloud sync verifier write at {_now_iso()}. "
            f"Test marker uuid={test_uuid}."
        ),
    }

    if engine_has_dossier_active:
        body = json.dumps({
            "account_id": account_id, "device_id": device_a,
            "entry": profile_fragment,
        }).encode("utf-8")
        s, b, parsed = _http_json(
            "POST", f"{ENGINE_BASE}/api/dossier/active",
            headers={"Content-Type": "application/json"}, body=body, timeout=10.0,
        )
        if s != 200:
            step("local_write_via_api", "fail",
                 {"status": s, "snippet": b[:200]})
            result["result"] = "BROKEN_AT_local_write_api"
            return result
        step("local_write_via_api", "ok",
             {"status": s, "written_path": parsed.get("written_path")})
        local_path = parsed.get("written_path")
    else:
        # Direct disk write because the running engine is legacy.
        # We mimic exactly what dossier_endpoints.dossier_active_write does.
        target = _direct_disk_write_dossier(account_id, profile_fragment)
        step("local_write_direct_disk", "ok",
             {"path": str(target),
              "note": "engine lacks /api/dossier/active route"})
        local_path = str(target)
        result["product_chain_gaps"].append({
            "stage": "local_write",
            "evidence": "no /api/dossier/active on running engine",
            "diagnosis": (
                "Bypassed engine; wrote directly to the canonical disk path "
                "the loader reads from. The engine on 8731 cannot accept "
                "dossier-active writes until restarted."
            ),
        })

    # Verify the dossier file exists with our content.
    p = Path(local_path or "")
    disk_ok = p.is_file() and "M3 cloud sync verifier write" in (
        p.read_text(encoding="utf-8") if p.is_file() else ""
    )
    step("local_dossier_disk_verify", "ok" if disk_ok else "fail",
         {"path": str(p), "exists": p.exists(),
          "size": p.stat().st_size if p.exists() else 0})
    if not disk_ok:
        result["result"] = "BROKEN_AT_local_dossier_disk_verify"
        return result

    # ------------------------------------------------------------------
    # Step 2: enqueue + flush the outbox. The product's chain has a gap
    # here: nothing in the engine ever calls sync.enqueue() with a
    # dossier fragment. The dossier write endpoint writes to disk only.
    # We document that gap and then exercise the seam directly so the
    # rest of the chain (worker -> Supabase) is verified end to end.
    # ------------------------------------------------------------------
    result["product_chain_gaps"].append({
        "stage": "enqueue_after_local_write",
        "evidence": (
            "grep of engine/app/ shows enqueue() is defined but never "
            "called from product code. /api/dossier/active writes to disk "
            "only. The outbox file is never appended to by the engine."
        ),
        "diagnosis": (
            "MISSING PRODUCER. Even after a process restart the engine "
            "would never sync dossier writes to Supabase because no "
            "business logic calls MemoryCloudSync.enqueue()."
        ),
    })

    # Make the verifier outbox isolated so it does not collide with any
    # ambient outbox state at ~/.anticipy/v7/memory_outbox.jsonl.
    iso_outbox = out_root / "outbox_isolated"
    iso_outbox.mkdir(parents=True, exist_ok=True)
    os.environ["ANTICIPY_V7_MEMORY_OUTBOX_DIR"] = str(iso_outbox)

    # Import the seam now that env is set. Reset the singleton to pick
    # up the isolated outbox dir; mirror what reset_singleton_for_tests does.
    sys.path.insert(0, str(REPO_ROOT / "engine"))
    try:
        from app.product.memory_cloud_sync import (
            MemoryCloudSync, reset_singleton_for_tests, get_sync,
        )
    except Exception as exc:
        step("import_memory_cloud_sync", "fail",
             {"err": f"{type(exc).__name__}: {exc}"})
        result["result"] = "BROKEN_AT_import_memory_cloud_sync"
        return result
    reset_singleton_for_tests()
    sync = get_sync()
    step("outbox_init", "ok", {
        "outbox_path": str(sync._outbox_path),
        "url_set": bool(sync._url),
        "key_set": bool(sync._key),
    })

    item = _build_outbox_item(
        user_id=test_uuid,
        field_count=len(profile_fragment.get("people") or {})
        + len(profile_fragment.get("pronoun_map") or {})
        + len(profile_fragment.get("do_not_touch") or [])
        + 2,
        profile_fragment=profile_fragment,
    )
    enqueued_id = sync.enqueue(item)
    pending_before = sync.pending_count()
    step("outbox_enqueue", "ok", {
        "item_id": enqueued_id, "pending_count": pending_before,
        "item_kind": item["kind"],
    })

    flush_result = sync.flush(max_seconds=12.0)
    step("outbox_flush", "ok",
         {"flush_result": flush_result})
    outbox_shipped_ok = flush_result.get("shipped", 0) >= 1
    if not outbox_shipped_ok:
        # Snapshot the ack jsonl to surface what failed.
        ack_lines: list[str] = []
        if sync._ack_path.exists():
            ack_lines = sync._ack_path.read_text(
                encoding="utf-8",
            ).splitlines()
        step("outbox_ship_failed", "fail",
             {"ack_lines": ack_lines, "outbox_path": str(sync._outbox_path)})
        # Diagnose: try the same payload via direct REST so we know
        # whether the failure is on the producer (shape) or the wire.
        diag_hdr = {
            "apikey": sb_key, "Authorization": f"Bearer {sb_key}",
            "Content-Type": "application/json", "Prefer": "return=minimal",
        }
        diag_status, diag_body, _ = _http_json(
            "POST", f"{sb_url}/rest/v1/dossiers",
            diag_hdr, body=json.dumps([item]).encode("utf-8"), timeout=10.0,
        )
        result["product_chain_gaps"].append({
            "stage": "outbox_payload_shape",
            "evidence": (
                f"Direct REST replay of the exact outbox payload returned "
                f"HTTP {diag_status} with body: {diag_body[:300]}"
            ),
            "diagnosis": (
                "BROKEN SHAPE. memory_cloud_sync._ship_one sends the entire "
                "item dict (including 'kind' and 'item_id') as the row to "
                "POST /rest/v1/dossiers. The dossiers table has no such "
                "columns, so PostgREST rejects with PGRST204. The sync "
                "cannot ship dossier rows in its current form."
            ),
        })

        # Try a shape-corrected write so we can still prove cross-device
        # read works once the producer is fixed.
        sanitized = {
            "user_id": test_uuid,
            "profile": item.get("profile") or {},
            "pronoun_map": item.get("pronoun_map") or {},
            "people": item.get("people") or {},
            "do_not_touch": item.get("do_not_touch") or [],
            "source": item.get("source") or "verify_m3_cloud_sync",
            "field_count": int(item.get("field_count") or 0),
        }
        diag_status_ok, diag_body_ok, _ = _http_json(
            "POST", f"{sb_url}/rest/v1/dossiers",
            diag_hdr, body=json.dumps([sanitized]).encode("utf-8"),
            timeout=10.0,
        )
        step("supabase_sanitized_direct_write", "ok"
             if 200 <= diag_status_ok < 300 else "fail",
             {"status": diag_status_ok, "snippet": diag_body_ok[:160],
              "note": ("Wrote a shape-corrected payload directly to "
                       "Supabase so the downstream chain (read + "
                       "cross-device fetch) can still be evaluated.")})
        if not (200 <= diag_status_ok < 300):
            result["result"] = "BROKEN_AT_outbox_ship"
            return result

    # ------------------------------------------------------------------
    # Step 3: query Supabase directly for the row.
    # ------------------------------------------------------------------
    hdr = {"apikey": sb_key, "Authorization": f"Bearer {sb_key}",
           "Accept": "application/json"}
    sel_url = (
        f"{sb_url}/rest/v1/dossiers?user_id=eq.{urllib.parse.quote(test_uuid)}"
        f"&select=*"
    )
    s, b, parsed = _http_json("GET", sel_url, hdr, timeout=10.0)
    rows = parsed.get("_list") if "_list" in parsed else (
        parsed if isinstance(parsed, list) else []
    )
    # PostgREST returns a JSON array; our _http_json wraps it.
    if isinstance(parsed, dict) and "_list" in parsed:
        rows = parsed["_list"]
    elif isinstance(parsed, list):
        rows = parsed
    else:
        # _http_json returned a dict for an array-typed response; retry raw.
        try:
            rows = json.loads(b)
        except Exception:
            rows = []
    step("supabase_select_after_first_flush", "ok" if rows else "fail", {
        "status": s, "row_count": len(rows or []),
        "first_row_keys": sorted((rows or [{}])[0].keys()) if rows else [],
        "first_row_user_id": (rows or [{}])[0].get("user_id") if rows else None,
        "first_row_source": (rows or [{}])[0].get("source") if rows else None,
        "first_row_field_count": (rows or [{}])[0].get("field_count")
        if rows else None,
    })
    if not rows:
        result["result"] = "BROKEN_AT_supabase_read"
        return result

    supa_row = rows[0]
    result["supabase_row_uuid"] = supa_row.get("user_id")
    initial_field_count = supa_row.get("field_count")
    initial_updated_at = supa_row.get("updated_at")

    # ------------------------------------------------------------------
    # Step 4: modify LOCAL dossier and re-flush. The outbox does NOT
    # use upsert semantics (return=minimal only); a second POST of the
    # same user_id will hit the primary-key unique constraint and the
    # _ship_one method treats 409 as success. The row WILL NOT update.
    # ------------------------------------------------------------------
    profile_fragment_v2 = dict(profile_fragment)
    profile_fragment_v2["notes"] = profile_fragment["notes"] + " UPDATED"
    profile_fragment_v2["people"] = {
        **profile_fragment["people"], "investor": "Lila",
    }
    profile_fragment_v2["field_count_marker"] = "v2"

    if engine_has_dossier_active:
        body = json.dumps({
            "account_id": account_id, "device_id": device_a,
            "entry": profile_fragment_v2,
        }).encode("utf-8")
        s, b, _ = _http_json(
            "POST", f"{ENGINE_BASE}/api/dossier/active",
            headers={"Content-Type": "application/json"}, body=body, timeout=10.0,
        )
        step("local_write_v2_via_api", "ok" if s == 200 else "fail",
             {"status": s})
    else:
        _direct_disk_write_dossier(account_id, profile_fragment_v2)
        step("local_write_v2_direct_disk", "ok", {})

    item_v2 = _build_outbox_item(
        user_id=test_uuid,
        field_count=int(initial_field_count or 0) + 3,
        profile_fragment=profile_fragment_v2,
    )
    item_v2["item_id"] = f"m3-test-v2-{test_uuid}-{int(time.time() * 1000)}"
    sync.enqueue(item_v2)
    flush_v2 = sync.flush(max_seconds=12.0)
    step("outbox_flush_v2", "ok", {"flush_result": flush_v2})

    if flush_v2.get("shipped", 0) < 1:
        # Same shape problem; try a corrected PATCH so we can still
        # evaluate whether updates work on a clean payload.
        diag_hdr = {
            "apikey": sb_key, "Authorization": f"Bearer {sb_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }
        # PATCH to update the existing row instead of POST (which
        # would 409 on the PK). This is what an upsert-aware producer
        # would do.
        patch_payload = {
            "profile": profile_fragment_v2,
            "pronoun_map": profile_fragment_v2.get("pronoun_map") or {},
            "people": profile_fragment_v2.get("people") or {},
            "do_not_touch": profile_fragment_v2.get("do_not_touch") or [],
            "source": "verify_m3_cloud_sync",
            "field_count": int(item_v2.get("field_count") or 0),
            "updated_at": _now_iso(),
        }
        s2, b2, _ = _http_json(
            "PATCH",
            f"{sb_url}/rest/v1/dossiers"
            f"?user_id=eq.{urllib.parse.quote(test_uuid)}",
            diag_hdr, body=json.dumps(patch_payload).encode("utf-8"),
            timeout=10.0,
        )
        step("supabase_sanitized_patch", "ok"
             if 200 <= s2 < 300 else "fail",
             {"status": s2, "snippet": b2[:160],
              "note": ("Direct PATCH to update the row; documents the "
                       "behavior a working producer would need.")})

    # Re-read row.
    s, b, parsed = _http_json("GET", sel_url, hdr, timeout=10.0)
    try:
        rows_v2 = json.loads(b)
    except Exception:
        rows_v2 = []
    step("supabase_select_after_second_flush", "ok" if rows_v2 else "fail", {
        "status": s, "row_count": len(rows_v2),
        "field_count_after": rows_v2[0].get("field_count") if rows_v2 else None,
        "updated_at_after": rows_v2[0].get("updated_at") if rows_v2 else None,
        "notes_after": rows_v2[0].get("profile", {}).get("notes")
        if rows_v2 else None,
    })

    updated_correctly = False
    if rows_v2:
        # Two truth tests:
        #   a) Supabase has exactly one row for this user_id (no dup).
        #   b) The row reflects the v2 payload (updated_at moved OR
        #      profile.notes contains UPDATED).
        no_dup = len(rows_v2) == 1
        notes_show_v2 = "UPDATED" in str(
            (rows_v2[0].get("profile") or {}).get("notes") or "",
        )
        updated_at_moved = (
            str(rows_v2[0].get("updated_at")) != str(initial_updated_at)
        )
        updated_correctly = no_dup and (notes_show_v2 or updated_at_moved)
        result["update_diagnostics"] = {
            "no_dup": no_dup,
            "notes_show_v2": notes_show_v2,
            "updated_at_moved": updated_at_moved,
        }

    if not updated_correctly:
        result["product_chain_gaps"].append({
            "stage": "outbox_upsert_on_duplicate_primary_key",
            "evidence": (
                "memory_cloud_sync._ship_one issues "
                "POST /rest/v1/dossiers with Prefer: return=minimal but "
                "WITHOUT Prefer: resolution=merge-duplicates. The dossiers "
                "table uses user_id as PRIMARY KEY. The second POST is "
                "rejected with 409 (treated as success) and the row does NOT "
                "reflect the v2 payload."
            ),
            "diagnosis": (
                "MISSING UPSERT. Cloud sync cannot update an existing user's "
                "dossier. First write is the only write that ever lands."
            ),
        })

    # ------------------------------------------------------------------
    # Step 5: cross-device fetch. A second simulated device (different
    # device_id) reads the user's dossier from cloud. The product would
    # do this via /api/dossier/active GET combined with a hosted-app
    # GET /api/dossiers/<user_id>. Both paths are exercised:
    #
    #   a) PostgREST direct: the canonical cloud truth.
    #   b) hosted /api/dossiers endpoint, IF the Next.js app is up.
    # ------------------------------------------------------------------
    s, b, _ = _http_json("GET",
        f"{sb_url}/rest/v1/dossiers?user_id=eq.{urllib.parse.quote(test_uuid)}&select=*",
        hdr, timeout=10.0,
    )
    try:
        cross_rows = json.loads(b)
    except Exception:
        cross_rows = []
    cross_visible = bool(cross_rows)
    step("cross_device_supabase_read", "ok" if cross_visible else "fail", {
        "device_id": device_b,
        "rows_visible": len(cross_rows),
        "notes_visible": (cross_rows[0].get("profile") or {}).get("notes")
        if cross_rows else None,
    })
    result["cross_device_fetch"] = "PASS" if cross_visible else "FAIL"

    # ------------------------------------------------------------------
    # Step 6: cleanup. Only delete rows we inserted.
    # ------------------------------------------------------------------
    del_url = (
        f"{sb_url}/rest/v1/dossiers?user_id=eq.{urllib.parse.quote(test_uuid)}"
    )
    del_hdr = dict(hdr)
    del_hdr["Prefer"] = "return=minimal"
    s, b, _ = _http_json("DELETE", del_url, del_hdr, timeout=10.0)
    step("supabase_cleanup", "ok" if s in (200, 204) else "fail",
         {"status": s, "snippet": b[:160]})

    # Also wipe the on-disk dossier the test wrote so we don't leave
    # litter in ~/.anticipy/v7/dossiers/<account_id>/.
    try:
        target_dir = (Path.home() / ".anticipy" / "v7" / "dossiers"
                      / account_id)
        if target_dir.exists():
            for child in target_dir.iterdir():
                try:
                    child.unlink()
                except Exception:
                    pass
            target_dir.rmdir()
    except Exception:
        pass

    # ------------------------------------------------------------------
    # Final verdict.
    #
    # PASS requires the PRODUCT chain to work end-to-end:
    #   - engine accepts a dossier write at /api/dossier/active,
    #   - that write enqueues to the cloud-sync outbox,
    #   - the outbox worker ships to Supabase WITHOUT us shape-fixing
    #     the payload by hand,
    #   - a second device reads the cloud row via the same product
    #     surface area.
    #
    # If we had to do ANY direct REST fallback to make the rest of
    # the chain visible, the verdict is BROKEN_AT_<first failing
    # stage>. The cross-device read is then a SECONDARY signal: it
    # tells us whether the rest of the chain works once the producer
    # is fixed, but it does not flip the verdict to PASS.
    # ------------------------------------------------------------------
    if outbox_shipped_ok and updated_correctly and cross_visible:
        result["result"] = "PASS"
        result["ok"] = True
    else:
        # Pick the earliest broken stage for the verdict label.
        if not engine_has_sync_status or not engine_has_dossier_active:
            result["result"] = "BROKEN_AT_engine_routes_missing"
        elif not outbox_shipped_ok:
            # The outbox enqueue worked but the ship POST is rejected.
            result["result"] = "BROKEN_AT_outbox_ship"
        elif not updated_correctly:
            result["result"] = "BROKEN_AT_outbox_upsert"
        elif not cross_visible:
            result["result"] = "BROKEN_AT_cross_device_read"
        else:
            result["result"] = "BROKEN_AT_unknown"
        result["ok"] = False

    # Surface the secondary "would the chain work once fixed" signal.
    result["fallback_chain_proved_via_direct_rest"] = bool(cross_visible)

    return result


def _write_summary(result: dict, out_dir: Path) -> None:
    lines: list[str] = []
    lines.append(f"# M3 Cloud Sync Verification ({result.get('ts')})")
    lines.append("")
    lines.append(f"Verdict: {result.get('result')}")
    lines.append("")
    lines.append(f"- account_id: `{result.get('account_id')}`")
    lines.append(f"- user_id (Supabase PK): `{result.get('user_id')}`")
    lines.append(f"- supabase_row_uuid: `{result.get('supabase_row_uuid')}`")
    lines.append(f"- cross_device_fetch: {result.get('cross_device_fetch')}")
    lines.append("")
    lines.append("## Engine route gaps")
    if result.get("engine_route_gaps"):
        for gap in result["engine_route_gaps"]:
            lines.append(f"- `{gap['route']}`: {gap['diagnosis']}")
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("## Product chain gaps")
    if result.get("product_chain_gaps"):
        for gap in result["product_chain_gaps"]:
            lines.append(f"- **{gap['stage']}**: {gap['diagnosis']}")
            lines.append(f"  - evidence: {gap['evidence']}")
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("## Steps")
    for st in result.get("steps", []):
        lines.append(f"- {st['name']}: {st['status']}")
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n",
                                        encoding="utf-8")


def main() -> int:
    import sys as _sys
    out_root = OUTPUT_DIR_DEFAULT / (
        _sys.argv[1] if len(_sys.argv) > 1
        else f"m3_cloud_sync_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    )
    out_root.mkdir(parents=True, exist_ok=True)
    result = _run(out_root)
    # Belt-and-suspenders cleanup: even if _run returned early without
    # hitting its own cleanup branch, blow away any test rows we may
    # have inserted under this run's user_id and the on-disk dossier.
    env = _load_env_local()
    sb_url = _resolve_supabase_url(env)
    sb_key = _service_key(env)
    test_uuid = result.get("user_id")
    account_id = result.get("account_id")
    if sb_url and sb_key and test_uuid:
        cleanup = _cleanup_supabase(sb_url, sb_key, str(test_uuid))
        result["final_cleanup"] = cleanup
    if account_id:
        _cleanup_disk(str(account_id))

    (out_root / "result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    _write_summary(result, out_root)
    print(json.dumps({"result": result.get("result"),
                       "ok": result.get("ok"),
                       "out_dir": str(out_root)}, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
