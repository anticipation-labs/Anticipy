/**
 * src/do/PairCodeCounter.ts — the pair-code brute-force ceiling.
 * Replaces `e.app.store()` at backend/pb_hooks/guard.pb.js:116-195.
 *
 * WHY A DURABLE OBJECT AND NOT KV, AND NOT A MODULE-LEVEL Map
 * -----------------------------------------------------------
 * The thing being defended is stated at guard.pb.js:56-73: six digits is a
 * million codes, a script walking them ten a second walks all of them in a
 * day, and a hit on a live code is somebody else's browser claimed against the
 * guesser's account. The defence is "count the FAILED attempts in a bounded
 * window and refuse once the ceiling is hit".
 *
 * On PocketBase the counter lived in `e.app.store()` — one process, one shared
 * map, measured to work across the isolated hook runtimes (:93-99).
 *
 * A Worker has no such process. Requests land in whichever isolate the edge
 * picks, anywhere on the network, and a module-level `Map` is per-isolate: an
 * attacker distributing across colos would get an effectively unlimited number
 * of independent counters. A counter that can be reset by opening a new
 * connection is not a counter.
 *
 * Workers KV is also wrong: it is eventually consistent, with reads served
 * from a cache. Two concurrent guesses can both read `fails: 9` and both
 * proceed. Read-modify-write on a rate limiter needs SERIALISATION, which is
 * exactly what a Durable Object provides — one instance, one thread, requests
 * queued.
 *
 * The instance is named "global" so there is exactly ONE, everywhere. That
 * concentrates the all-callers ceiling in one place, which is what
 * guard.pb.js:105-108 wanted and could only approximate.
 *
 * WHAT IMPROVES OVER THE ORIGINAL, and it is not nothing:
 *   guard.pb.js:101-104 admits that behind Railway's edge `e.realIP()` gives
 *   every caller the same bucket, so the per-IP ceiling was doing no work at
 *   all and only the all-callers one bounded the walk. On Cloudflare,
 *   `CF-Connecting-IP` is stamped by the edge and is not caller-controllable,
 *   so the per-IP bucket becomes real for the first time.
 *
 * WHAT DOES NOT IMPROVE, and must not be claimed to:
 *   guard.pb.js:110-115. This makes the walk slow and loud; it does not end
 *   it. The code is permanent once minted (agent_auth.pb.js:19-25) and the
 *   popup shows it until the install re-registers, so a patient attacker still
 *   has a rate-limited walk against however many codes are live. The cure is a
 *   code that EXPIRES with a popup that refreshes it — a change to the pairing
 *   ceremony, not to this file.
 */

const WINDOW_MS = 10 * 60 * 1000;   // guard.pb.js:117
const MAX_PER_IP = 10;              // guard.pb.js:118
const MAX_ALL = 60;                 // guard.pb.js:119
const ALL_KEY = "all";
const PREFIX = "ip:";

interface Bucket { startedAt: number; fails: number; }

export class PairCodeCounter {
  private state: DurableObjectState;

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const { ip } = (await request.json().catch(() => ({}))) as { ip?: string };
    const key = PREFIX + (ip || "unknown");

    if (url.pathname === "/check") {
      const [mine, all] = await Promise.all([this.read(key), this.read(ALL_KEY)]);
      const allowed = mine.fails < MAX_PER_IP && all.fails < MAX_ALL;
      return Response.json({ allowed, mine: mine.fails, all: all.fails });
    }

    if (url.pathname === "/spend") {
      // Serialised by the Durable Object runtime, so unlike the original
      // (guard.pb.js:170-172, "two concurrent failures can read the same count
      // and one increment is lost") no guess is free.
      const now = Date.now();
      const mine = await this.read(key, now);
      const all = await this.read(ALL_KEY, now);
      await this.state.storage.put(key, { startedAt: mine.startedAt, fails: mine.fails + 1 });
      await this.state.storage.put(ALL_KEY, { startedAt: all.startedAt, fails: all.fails + 1 });

      // guard.pb.js:178-189 — sweep stale per-IP buckets only when the
      // all-callers window has just rolled, so this walk happens at most once
      // every ten minutes and never on the path somebody pairing takes.
      if (all.rolled) await this.sweep(now);

      return Response.json({ ok: true });
    }

    // Read-only, for the operator. Never mutates and never names a code.
    if (url.pathname === "/stats") {
      const all = await this.read(ALL_KEY);
      const keys = await this.state.storage.list<Bucket>({ prefix: PREFIX });
      return Response.json({ allCallers: all.fails, ipBuckets: keys.size });
    }

    return new Response("not found", { status: 404 });
  }

  /**
   * A bucket that is missing, unparseable or older than the window starts
   * again from now. FIXED window, not sliding: one read and one write per
   * failed attempt, and a guesser cannot spend less by pacing himself.
   * guard.pb.js:143-149.
   */
  private async read(key: string, now = Date.now()): Promise<Bucket & { rolled: boolean }> {
    const raw = await this.state.storage.get<Bucket>(key);
    if (!raw || !raw.startedAt || Number.isNaN(raw.startedAt)
        || Number.isNaN(raw.fails) || now - raw.startedAt >= WINDOW_MS) {
      return { startedAt: now, fails: 0, rolled: true };
    }
    return { ...raw, rolled: false };
  }

  private async sweep(now: number): Promise<void> {
    const all = await this.state.storage.list<Bucket>({ prefix: PREFIX });
    const dead: string[] = [];
    for (const [k, v] of all) {
      if (!v?.startedAt || now - v.startedAt >= WINDOW_MS) dead.push(k);
    }
    // storage.delete accepts a list; 128 keys per call is the documented cap.
    for (let i = 0; i < dead.length; i += 128) {
      await this.state.storage.delete(dead.slice(i, i + 128));
    }
  }
}
