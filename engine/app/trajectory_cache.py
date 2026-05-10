"""
Trajectory cache — semantic recall over past browser-agent runs, plus
the writer that lands new rows with their embedding attached.

Given a new task, find the wearer's most-similar past trajectories and
expose them so the planner / system prompt can re-use the steps as
few-shot examples (or, for very-high-similarity hits, short-circuit
straight to a known plan).

Storage layout:
  * Table  : public.engine_trajectories
  * Vector : task_embedding vector(768)
  * RPC    : engine_trajectories_topk(p_user_id text, p_query vector,
              p_k int, p_only_success bool)
              returns rows ordered by cosine distance with a `similarity`
              field (1 - cosine_distance).

The RPC is created in Supabase. It accepts a vector literal (PostgREST
will JSON-decode the string into a vector). We embed the query with
Gemini text-embedding-004 (see app.embeddings) and pass the formatted
literal through.

Thresholds (tuned empirically against the 120-row corpus we have today;
revisit when the corpus grows past 1000):
  * 0.92 = effectively the same task — safe to use as a known plan.
  * 0.78 = same goal-shape, different surface form — useful as primary
           retrieval for the planner.
  * 0.65 = loose neighbourhood — useful as varied few-shot examples,
           even if exact reuse would be wrong.
"""

from __future__ import annotations

import logging
from typing import Optional

from app import embeddings
from app import supabase_client


logger = logging.getLogger("engine.trajectory_cache")


# Tunable thresholds — single source of truth so callers don't drift.
SIMILARITY_NEAR_DUPLICATE: float = 0.92
SIMILARITY_USEFUL: float = 0.78
SIMILARITY_FEW_SHOT: float = 0.65


async def find_similar_trajectories(
    user_id: str,
    task: str,
    k: int = 5,
    similarity_threshold: float = SIMILARITY_USEFUL,
    only_success: bool = True,
) -> list[dict]:
    """Find past trajectories semantically similar to `task` for `user_id`.

    Returns a list of dicts shaped like:
      {
        "id": str,
        "task_summary": str,
        "domain": str,
        "steps": list,
        "outcome": str,
        "outcome_message": str | None,
        "total_steps": int,
        "similarity": float,    # 0..1, higher = more similar
      }
    Sorted descending by similarity. Filters to only rows where similarity
    is at least `similarity_threshold`.

    On any failure (no embeddings provider, RPC error, no rows) returns [].
    Never raises.
    """
    if not user_id or not task or not task.strip():
        return []
    if k <= 0:
        return []

    qvec = await embeddings.embed_query(task)
    if qvec is None:
        # No embeddings — degrade silently. The agent still runs; it just
        # doesn't get RAG context for this turn.
        logger.debug(
            "find_similar_trajectories: no embedding (provider missing or quota); "
            "returning []"
        )
        return []

    try:
        rows = await supabase_client.call_rpc(
            "engine_trajectories_topk",
            {
                "p_user_id": user_id,
                "p_query": embeddings.vector_to_pg_literal(qvec),
                "p_k": int(k),
                "p_only_success": bool(only_success),
            },
        )
    except Exception:
        logger.exception("trajectories_topk RPC raised")
        return []

    if not rows:
        return []

    out: list[dict] = []
    for row in rows:
        sim = row.get("similarity")
        if sim is None:
            continue
        try:
            sim_f = float(sim)
        except (TypeError, ValueError):
            continue
        if sim_f < similarity_threshold:
            continue
        out.append({
            "id": str(row.get("id") or ""),
            "task_summary": str(row.get("task_summary") or ""),
            "domain": str(row.get("domain") or ""),
            "steps": row.get("steps") or [],
            "outcome": str(row.get("outcome") or ""),
            "outcome_message": row.get("outcome_message"),
            "total_steps": int(row.get("total_steps") or 0),
            "similarity": sim_f,
        })

    # The RPC orders by ascending cosine distance, but our threshold filter
    # may have dropped some rows. Re-sort by similarity desc to be safe.
    out.sort(key=lambda r: r["similarity"], reverse=True)
    return out


async def cache_hit_for(user_id: str, task: str) -> Optional[dict]:
    """Return the single best match if it crosses the near-duplicate
    threshold, otherwise None.

    Use this when the planner wants to short-circuit a brand-new run
    because we've already seen this exact task. Caller is responsible for
    deciding whether to actually replay or just use the steps as a strong
    plan hint.
    """
    matches = await find_similar_trajectories(
        user_id, task, k=1, similarity_threshold=SIMILARITY_NEAR_DUPLICATE,
        only_success=True,
    )
    return matches[0] if matches else None


async def get_few_shot_examples(
    user_id: str,
    task: str,
    k: int = 3,
) -> list[dict]:
    """Looser-threshold retrieval for "show the planner some past tasks".

    Even at 0.65 similarity these are usually structurally relevant:
    e.g. "find the price on Amazon" vs. "find a product on Best Buy"
    both teach the planner about a price-extraction goal-shape.
    """
    return await find_similar_trajectories(
        user_id, task, k=k, similarity_threshold=SIMILARITY_FEW_SHOT,
        only_success=True,
    )


async def record_trajectory(
    *,
    user_id: str,
    task_summary: str,
    domain: str,
    steps: list,
    outcome: str,
    outcome_message: str | None = None,
    total_steps: int | None = None,
    duration_ms: int | None = None,
    cost_usd: float | None = None,
    intent_id: str | None = None,
) -> str | None:
    """Persist one engine_trajectories row and (best-effort) embed its
    task_summary so it joins the RAG corpus immediately.

    Returns the new row's id on success, None on persistence failure.
    Embedding is fire-and-forget via asyncio.create_task — the row
    insert returns the id even if the embedding update fails or is
    deferred.

    Caller is responsible for sanitizing the inputs (length caps live
    in the existing /api/engine/trajectory route; we apply lighter caps
    here as a safety belt, not a substitute).
    """
    if not user_id or not task_summary or not domain or not steps:
        return None
    if outcome not in {"success", "partial", "fail", "aborted"}:
        return None

    # intent_id is a uuid column — drop non-uuid strings (e.g. "smoke-001"
    # from tests) instead of letting Supabase 400 us.
    if intent_id is not None:
        import uuid as _uuid
        try:
            _uuid.UUID(str(intent_id))
        except (ValueError, AttributeError):
            intent_id = None

    # Local import to keep the module load-graph small for callers that
    # only use the read-side find_similar_trajectories.
    from app import supabase_client

    row = {
        "user_id": user_id,
        "domain": domain.strip().lower()[:120] or "unknown",
        "task_summary": task_summary[:2000],
        "steps": steps[:200],
        "outcome": outcome,
        "outcome_message": (outcome_message or "")[:2000] or None,
        "total_steps": int(total_steps if total_steps is not None else len(steps)),
        "duration_ms": int(duration_ms) if isinstance(duration_ms, (int, float)) else None,
        "cost_usd": float(cost_usd) if isinstance(cost_usd, (int, float)) else None,
        "intent_id": intent_id,
    }

    try:
        result = await supabase_client.insert_row(
            "engine_trajectories", row, service_role=True,
        )
    except Exception:
        logger.exception("trajectory insert raised")
        return None
    if not result:
        return None
    row_id = str(result.get("id") or "") or None
    if not row_id:
        return None

    # Only embed successful rows — failed/aborted runs would mislead the
    # planner if surfaced as RAG examples. (Same policy as the Next.js
    # /api/engine/trajectory writer.)
    if outcome == "success":
        try:
            import asyncio
            loop = asyncio.get_running_loop()
            loop.create_task(_embed_and_attach(row_id, task_summary))
        except RuntimeError:
            # No running loop — caller is in a sync context. Skip silently;
            # the nightly backfill script will pick the row up.
            pass

    return row_id


async def _embed_and_attach(row_id: str, task_summary: str) -> None:
    """Embed `task_summary` and write it back to the row's task_embedding.

    Best-effort: any failure (no provider, quota exhausted, network)
    leaves the row without an embedding. The backfill script will catch
    it on the next run.
    """
    try:
        vec = await embeddings.embed_one(task_summary[:2000])
        if vec is None:
            return
        from app import supabase_client
        update = getattr(supabase_client, "update_rows", None)
        if not callable(update):
            return
        await update(
            "engine_trajectories",
            {"id": row_id},
            {"task_embedding": embeddings.vector_to_pg_literal(vec)},
        )
    except Exception:
        logger.debug("trajectory embed background update failed", exc_info=True)
