// src/plan.ts — who gets a brain this tick. Pure, so it can be pinned by
// test/plan-fleet.test.ts without D1 or the containers SDK (index.ts imports
// @cloudflare/containers, which plain node cannot resolve).
export type FleetOwner = { id: string; legacy_uuid?: string };

/**
 * Who gets a brain this tick, as a pure function so it can be pinned without
 * D1 or a container: allowlisted owners first and outside the cap, then the
 * discovered owners in id order until the cap is spent; an owner in both
 * lists is served once. The cap still TURNS OWNERS AWAY, never evicts.
 */
export function planFleet(discovered: FleetOwner[], always: FleetOwner[], cap: number): { serve: FleetOwner[]; unserved: string[] } {
  const serve: FleetOwner[] = [];
  const seen = new Set<string>();
  for (const o of always) {
    const id = String(o.id);
    if (seen.has(id)) continue;
    seen.add(id); serve.push(o);
  }
  let room = cap;
  const unserved: string[] = [];
  for (const o of discovered) {
    const id = String(o.id);
    if (seen.has(id)) continue;
    if (room <= 0) { unserved.push(id); continue; }
    seen.add(id); serve.push(o); room -= 1;
  }
  return { serve, unserved };
}
