#!/usr/bin/env python3
"""
Backfill `task_embedding` for engine_trajectories rows that are missing one.

Idempotent — only touches rows where task_embedding IS NULL. Safe to run
repeatedly (e.g. nightly cron) and safe to interrupt at any point: the
next run picks up where it left off.

Usage:
    # source .env.local first so GOOGLE_API_KEY and the supabase keys are set
    cd engine
    python3 backfill_trajectory_embeddings.py
    python3 backfill_trajectory_embeddings.py --batch-size 50 --max-rows 200
    python3 backfill_trajectory_embeddings.py --dry-run

Cost note: 768-dim Gemini embeddings are free up to 1500 reqs/day. Each
trajectory row = 1 request. Backfilling ~120 rows fits comfortably under
the free quota.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from typing import Any

import httpx

import os

from app.config import GOOGLE_API_KEY, SUPABASE_ANON_KEY, SUPABASE_URL
from app import embeddings


logger = logging.getLogger("backfill_trajectory_embeddings")


# Service-role key bypasses RLS so we can read+update every trajectory
# row. Falls back to the anon key for compatibility, but the backfill
# will only see RLS-visible rows in that case (effectively zero in prod).
_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
_AUTH_KEY = _SERVICE_KEY or SUPABASE_ANON_KEY


def _headers(extra: dict | None = None) -> dict:
    h = {
        "apikey": _AUTH_KEY,
        "Authorization": f"Bearer {_AUTH_KEY}",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h


async def _fetch_pending_rows(
    client: httpx.AsyncClient, batch_size: int, last_id: str | None,
) -> list[dict]:
    """Fetch the next batch of unembedded trajectories, ordered by id.

    We page by `id` (UUID lex order) rather than offset because rows
    can drop out of the unembedded set between pages — offset paging
    would skip rows.
    """
    params: dict[str, str] = {
        "select": "id,task_summary",
        "task_embedding": "is.null",
        "order": "id.asc",
        "limit": str(int(batch_size)),
    }
    if last_id:
        params["id"] = f"gt.{last_id}"
    resp = await client.get(
        f"{SUPABASE_URL}/rest/v1/engine_trajectories",
        headers=_headers(),
        params=params,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else []


async def _patch_embedding(
    client: httpx.AsyncClient, row_id: str, vec: list[float],
) -> bool:
    """Update a single row's task_embedding column."""
    literal = embeddings.vector_to_pg_literal(vec)
    resp = await client.patch(
        f"{SUPABASE_URL}/rest/v1/engine_trajectories",
        headers=_headers({"Prefer": "return=minimal"}),
        params={"id": f"eq.{row_id}"},
        json={"task_embedding": literal},
        timeout=15,
    )
    if resp.status_code in (200, 204):
        return True
    body = (resp.text or "")[:240]
    logger.warning(
        "embedding patch failed status=%d id=%s body=%s",
        resp.status_code, row_id, body,
    )
    return False


async def run_backfill(
    *, batch_size: int, max_rows: int, dry_run: bool,
) -> int:
    if not GOOGLE_API_KEY:
        logger.error(
            "GOOGLE_API_KEY is not set — cannot embed. "
            "Source your .env.local first."
        )
        return 2
    if not SUPABASE_URL or not _AUTH_KEY:
        logger.error("SUPABASE_URL or auth key (service-role / anon) not set.")
        return 2
    if not _SERVICE_KEY:
        logger.warning(
            "SUPABASE_SERVICE_ROLE_KEY not set; backfill will only see "
            "RLS-visible rows (likely zero in production)."
        )

    processed = 0
    embedded = 0
    skipped = 0
    failed = 0
    last_id: str | None = None

    async with httpx.AsyncClient() as client:
        while True:
            try:
                rows = await _fetch_pending_rows(client, batch_size, last_id)
            except httpx.HTTPError:
                logger.exception("failed to fetch pending rows")
                return 3
            if not rows:
                break

            texts = [r.get("task_summary") or "" for r in rows]
            vecs = await embeddings.embed_batch(texts)

            for row, vec in zip(rows, vecs):
                processed += 1
                last_id = row["id"]

                if vec is None:
                    skipped += 1
                    logger.info(
                        "[%d] skip id=%s (embedding failed; will retry next run)",
                        processed, row["id"],
                    )
                    continue

                if dry_run:
                    embedded += 1
                    logger.info(
                        "[%d] would-embed id=%s task=%r",
                        processed, row["id"],
                        (row.get("task_summary") or "")[:60],
                    )
                else:
                    ok = await _patch_embedding(client, row["id"], vec)
                    if ok:
                        embedded += 1
                        logger.info(
                            "[%d] embedded id=%s task=%r",
                            processed, row["id"],
                            (row.get("task_summary") or "")[:60],
                        )
                    else:
                        failed += 1

                if max_rows and processed >= max_rows:
                    break

            if max_rows and processed >= max_rows:
                break

    logger.info(
        "done. processed=%d embedded=%d skipped=%d failed=%d",
        processed, embedded, skipped, failed,
    )
    return 0


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Backfill engine_trajectories embeddings")
    p.add_argument("--batch-size", type=int, default=20,
                   help="rows per page (default 20). Gemini batch handles up to 100.")
    p.add_argument("--max-rows", type=int, default=0,
                   help="cap total rows processed (0 = no cap)")
    p.add_argument("--dry-run", action="store_true",
                   help="embed but don't write back to Supabase")
    p.add_argument("--verbose", "-v", action="store_true")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return asyncio.run(run_backfill(
        batch_size=args.batch_size,
        max_rows=args.max_rows,
        dry_run=args.dry_run,
    ))


if __name__ == "__main__":
    sys.exit(main())
