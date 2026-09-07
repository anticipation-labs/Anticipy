/** Returning idle work to its owner removes authority; it never grants a run.
 * Shared by workflow transitions and the narrow incompatible-hand repair.
 */
import type { Ctx } from './chain.ts';

export function object(raw: unknown): Record<string, unknown> | null {
  try {
    const value = typeof raw === 'string' ? JSON.parse(raw) : raw;
    return value && typeof value === 'object' && !Array.isArray(value) ? value : null;
  } catch { return null; }
}

export function heldRevision(ctx: Ctx, old: Record<string, unknown> | null,
                             body: Record<string, unknown>): boolean {
  if (!old || !['account', 'service', 'superuser'].includes(ctx.principal.kind)
      || ctx.request.headers.has('X-Anticipy-Agent-ID')
      || !['needs_user', 'awaiting_confirm'].includes(String(old.status))
      || body.status !== 'awaiting_confirm'
      || !['draft', 'awaiting_approval'].includes(String(body.workflow_state))
      || !Number.isInteger(body.workflow_version)
      || Number(body.workflow_version) !== Number(old.workflow_version) + 1
      || old.lease_token || old.receipt || Number(old.effect_uncertain ?? 0) !== 0
      || body.approval !== '' || body.receipt !== '' || body.lease_token !== '') return false;
  const before = object(object(old.params)?._workflow);
  const after = object(object(body.params)?._workflow);
  return !!before && !!after && !before.lease && !before.receipt
    && after.plan_id === before.plan_id && after.owner_ref === before.owner_ref
    && after.owner_ref === old.owner_ref && after.version === body.workflow_version
    && after.state === body.workflow_state && after.consequence === old.consequence
    && !after.approval && !after.lease && !after.receipt;
}
