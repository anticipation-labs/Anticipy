/**
 * The brain fleet on Cloudflare Containers — replaces brain/supervisor.py.
 *
 *   BrainSupervisor.tick()   discover owners from D1, reconcile the running set
 *   OwnerBrain               one container per owner, memory pulled from R2
 *
 * ╔════════════════════════════════════════════════════════════════════════╗
 * ║ UNTESTED. Written 2026-09-04 from migration/BRAIN-ON-CONTAINERS.md and    ║
 * ║ workers/BRAIN.md, with NO Docker and NO container runtime to run it       ║
 * ║ against. There is no oracle for this — it could not be diffed against a   ║
 * ║ working system the way every route this session was. Its failure modes    ║
 * ║ are duplicate outreach (two supervisors) and lost memory (bad envFor).    ║
 * ║ DO NOT DEPLOY until it has run green against a container runtime per       ║
 * ║ BRAIN-ON-CONTAINERS.md §7. This is faithful scaffolding for that session. ║
 * ╚════════════════════════════════════════════════════════════════════════╝
 *
 * `@cloudflare/containers` must be installed in migration/workers/ before this
 * typechecks (`npm install @cloudflare/containers`). It is deliberately NOT
 * pulled into the main Worker's deps — this is a SEPARATE deploy
 * (config/wrangler.brain.jsonc), so the API Worker's bundle stays lean.
 */
import { planFleet } from "./plan";
import { Container, getContainer } from "@cloudflare/containers";
import { DurableObject } from "cloudflare:workers";

export interface BrainEnv {
  DB: D1Database;
  OWNER_BRAIN: DurableObjectNamespace<OwnerBrain>;
  BRAIN_SUPERVISOR: DurableObjectNamespace<BrainSupervisor>;

  // The cap and the discovery cadence. supervisor.py MAX_OWNER_WORKERS.
  ANTICIPY_MAX_OWNER_WORKERS?: string;
  ANTICIPY_SERVE_OWNERS?: string;   // comma list of owner ids always served, outside the cap (e2e probe)

  // Everything child_environment() reads or forwards. Non-secrets come from
  // wrangler vars; secrets from `wrangler secret put`. A Worker secret is NOT
  // automatically a container env var — envFor() must copy each into envVars.
  [key: string]: unknown;
}

/** The same guard as brain/supervisor.py:35. LOAD-BEARING: the ref is joined
 *  onto a state path and later deleted, so an id that is not this shape is a
 *  path-traversal and a wrong-directory delete waiting to happen. */
const SAFE_ID = /^[A-Za-z0-9_-]{8,64}$/;

// env keys forwarded verbatim from the DO's env into every child. Non-secret
// config plus the secrets the worker needs. Names only; values live in
// this.env. Keep in step with BRAIN-ON-CONTAINERS.md §4.
const FORWARD_KEYS = [
  "ANTICIPY_PB", "ANTICIPY_STATE_ROOT", "ANTICIPY_STATE_VOLUME_ROOT",
  "ANTICIPY_STATE_R2_BUCKET", "ANTICIPY_STATE_R2_PREFIX",
  "ANTICIPY_STATE_SNAPSHOT_SECONDS", "ANTICIPY_STATE_BACKUP_SECONDS",
  "ANTICIPY_STATE_BACKUP_PREFIX", "ANTICIPY_STATE_BACKUP_KEEP",
  "ANTICIPY_BACKUP_REQUIRED", "ANTICIPY_BACKUP_S3_REGION",
  "ANTICIPY_TZ", "ANTICIPY_MODEL", "ANTICIPY_GEMINI_MODEL",
  "ANTICIPY_AUX_MODEL", "ANTICIPY_STRONG_MODEL",
  "ANTICIPY_SEGMENTS", "ANTICIPY_SUPERVISED", "ANTICIPY_WEBHOOK_MANAGER",
  "ANTICIPY_TWILIO_WEBHOOK_URL", "ANTICIPY_LINKS", "ANTICIPY_LLM_LEDGER",
  "ANTICIPY_SEGMENT_TRIAGE", "TWILIO_API_BASE", "TWILIO_MOCK",
  // secrets
  "ANTICIPY_SERVICE_TOKEN", "OPENROUTER_API_KEY", "GEMINI_API_KEY",
  "BRAVE_API_KEY", "TAVILY_API_KEY",
  "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_PHONE_NUMBER", "TWILIO_FROM",
  "TWILIO_API_KEY_SID", "TWILIO_API_KEY_SECRET",
  // Sendblue (iMessage/SMS) — the provider Twilio is being replaced by,
  // 2026-09-05. brain/sendblue_arm.py reads these; the container sees only
  // what this list carries, so a name missing here is a silent "sms=mock".
  "ANTICIPY_SMS_PROVIDER", "ANTICIPY_SMS_MOCK",
  "SENDBLUE_API_KEY_ID", "SENDBLUE_API_SECRET_KEY", "SENDBLUE_FROM_NUMBER",
  "SENDBLUE_API_BASE", "SENDBLUE_STATUS_CALLBACK",
  "ANTICIPY_BACKUP_S3_BUCKET", "ANTICIPY_BACKUP_S3_ENDPOINT",
  "ANTICIPY_BACKUP_S3_ACCESS_KEY", "ANTICIPY_BACKUP_S3_SECRET",
] as const;

interface Owner { id: string; legacy_uuid: string }

/**
 * One container per owner. getContainer(env.OWNER_BRAIN, ownerRef) yields
 * exactly one DO per ref (single-writer — which is what makes whole-file R2
 * state safe), so exactly one container, so exactly one process with that
 * owner's memory.db open.
 */
export class OwnerBrain extends Container<BrainEnv> {
  defaultPort = 8731;          // the control server; without it the container is unobservable (§3.2)
  requiredPorts = [8731];
  sleepAfter = "24h";

  // Deliberately empty. §3.1: a container-backed DO is kept alive by a
  // self-rearming alarm, and onActivityExpired is where an owner-idle policy
  // WOULD go — but the brain is never "done", so it never expires on purpose.
  override async onActivityExpired(): Promise<void> {
    /* intentionally empty — see BRAIN-ON-CONTAINERS.md §3.1 */
  }

  /**
   * Start (or confirm running) this owner's container with the env
   * child_environment() computes. Idempotent: the SDK no-ops start() on an
   * already-running container.
   */
  async ensure(owner: Owner): Promise<void> {
    await this.startAndWaitForPorts({
      startOptions: { envVars: this.envFor(owner) },
    });
  }

  async shutdown(): Promise<void> {
    await this.stop();
  }

  /**
   * brain/supervisor.py:76-115, reproduced. The ANTICIPY_OWNER_PHONE POP on
   * :109 is a scar, not an optimisation: without it a second signup got a
   * worker bound to the founder's phone number and cross-account SMS flowed
   * both ways. The legacy-owner branch keeps the founder's existing durable
   * path; new accounts never inherit it.
   */
  envFor(owner: Owner): Record<string, string> {
    const env: Record<string, string> = {};
    for (const k of FORWARD_KEYS) {
      const v = this.env[k];
      if (v !== undefined && v !== null && v !== "") env[k] = String(v);
    }

    const ref = String(owner.id || "").trim();
    if (!SAFE_ID.test(ref)) throw new Error("invalid owner id");
    const legacy = String(owner.legacy_uuid || "").trim();

    const stateRoot = env.ANTICIPY_STATE_ROOT || "/data/owners";
    const ownerDir = `${stateRoot.replace(/\/$/, "")}/${ref}`;

    const configuredLegacy = String(this.env.ANTICIPY_OWNER_ID || "").trim();
    const isLegacy = !!(legacy && configuredLegacy && legacy === configuredLegacy);
    const oldMemory = String(this.env.ANTICIPY_MEMORY_DB || "").trim();
    const oldClock = String(this.env.ANTICIPY_CLOCK_STATE || "").trim();

    env.ANTICIPY_OWNER_REF = ref;
    env.ANTICIPY_OWNER_ID = legacy || ref;
    env.ANTICIPY_MEMORY_DB = isLegacy && oldMemory ? oldMemory : `${ownerDir}/memory.db`;
    env.ANTICIPY_CLOCK_STATE = isLegacy && oldClock ? oldClock : `${ownerDir}/clock_state.json`;

    // The founder's phone must NOT ride along into someone else's worker.
    if (isLegacy) {
      const phone = String(this.env.ANTICIPY_OWNER_PHONE || "").trim();
      if (phone) env.ANTICIPY_OWNER_PHONE = phone;
    } else {
      delete env.ANTICIPY_OWNER_PHONE;   // the pop()
    }

    env.ANTICIPY_SUPERVISED = "1";
    // The webhook-manager role is the SUPERVISOR's now, not any one child —
    // a role written once at spawn cannot follow it when an owner disappears.
    env.ANTICIPY_WEBHOOK_MANAGER = "0";
    return env;
  }
}

/**
 * The fleet supervisor. One DO (a fixed name), ticked by the cron. It replaces
 * supervisor.py's infinite reconcile loop with one D1 read per tick.
 */
export class BrainSupervisor extends DurableObject<BrainEnv> {
  /**
   * brain/supervisor.py discover_owners() + reconcile_children(), together.
   *
   * The two properties reconcile_children was extracted to protect, preserved:
   *   - the cap TURNS OWNERS AWAY, never evicts. discover returns EVERY owner;
   *     truncating discovery made the cap read "not in this set" as "deleted"
   *     and SIGTERM a live owner whose random id happened to sort low.
   *   - over-capacity PRINTS EVERY PASS, so going over the cap is visible.
   */
  async tick(): Promise<{ served: number; unserved: string[] }> {
    const cap = parseInt(String(this.env.ANTICIPY_MAX_OWNER_WORKERS ?? "100"), 10) || 100;

    // discover: real owners only, ordered by id (stable, like supervisor.py's
    // page walk over /worker/owners which projects exactly {id, legacy_uuid}).
    //
    // FIX 2026-09-05: D1 holds ~33 owner rows but only a handful are real —
    // the rest are probe/test signups (…@example.invalid, …@anticipy-test.invalid,
    // …@*.local) and blank-email rows the old create path let through. Spawning a
    // brain container per junk row wasted the whole fleet and printed "over
    // capacity" against phantoms. Exclude them at the source. This mirrors the
    // runbook's "delete the junk owners" step, but as a non-destructive filter:
    // the rows stay in D1 (nothing is deleted), they just get no worker.
    const rows = await this.env.DB.prepare(
      `SELECT id, legacy_uuid FROM owners
         WHERE email IS NOT NULL AND email != ''
           AND email NOT LIKE '%.invalid'
           AND email NOT LIKE '%.local'
           AND email NOT LIKE '%@example.%'
         ORDER BY id`,
    ).all<Owner>();
    const discovered = (rows.results ?? []).filter((o) => SAFE_ID.test(String(o.id || "")));

    // ALWAYS-SERVED OWNERS. ANTICIPY_SERVE_OWNERS is a comma list of owner ids
    // that get a brain regardless of the cap and regardless of the junk filter
    // above. It exists for ONE reason: the end-to-end proof
    // (proof/e2e_cloudflare.py) drives the whole pendant chain against
    // production with a disposable `…@anticipy-test.invalid` owner, and that
    // owner is — correctly — invisible to discovery and behind four real
    // people in id order. Without this the brain hop of the proof could only
    // run on a real person's account. Allowlisted owners are looked up by id
    // (never trusted from the env alone: a name that is not an owners row is
    // skipped and logged) and do not spend a cap slot, so cap=1 still serves
    // the same first real owner it served before. Empty by default.
    const allow = String(this.env.ANTICIPY_SERVE_OWNERS ?? "")
      .split(",").map((x) => x.trim()).filter((x) => SAFE_ID.test(x));
    let always: Owner[] = [];
    if (allow.length) {
      const marks = allow.map(() => "?").join(",");
      const found = await this.env.DB.prepare(
        `SELECT id, legacy_uuid FROM owners WHERE id IN (${marks})`,
      ).bind(...allow).all<Owner>();
      always = (found.results ?? []).filter((o) => SAFE_ID.test(String(o.id || "")));
      for (const id of allow) if (!always.some((o) => String(o.id) === id)) {
        console.log(`serve-owners: ${id} is not an owners row; skipped`);
      }
    }
    const { serve, unserved } = planFleet(discovered, always, cap);

    let served = 0;
    for (const owner of serve) {
      try {
        const brain = getContainer(this.env.OWNER_BRAIN, String(owner.id));
        await brain.ensure({ id: String(owner.id), legacy_uuid: String(owner.legacy_uuid ?? "") });
        served += 1;
      } catch (err) {
        // One owner failing to start must not stop the fleet. Log and continue,
        // exactly as reconcile_children keeps going past a dead child.
        console.log(`owner worker failed to start · owner=${owner.id} · ${err}`);
      }
    }
    if (unserved.length) {
      // Over capacity — say so EVERY pass. Silent truncation is the bug.
      console.log(`brain fleet over capacity: ${unserved.length} owners unserved (cap ${cap})`);
    }
    return { served, unserved };
  }
}
export default {
  /**
   * The cron drives the supervisor. config/wrangler.brain.jsonc's
   * ANTICIPY_OWNER_DISCOVERY_SECONDS was the loop interval; here it is the cron
   * cadence. One fixed-name supervisor DO owns the reconcile so two ticks never
   * race.
   */
  async scheduled(_event: ScheduledController, env: BrainEnv, ctx: ExecutionContext): Promise<void> {
    const id = env.BRAIN_SUPERVISOR.idFromName("fleet");
    const supervisor = env.BRAIN_SUPERVISOR.get(id);
    ctx.waitUntil(supervisor.tick().then((r) => {
      console.log(`brain fleet tick: ${r.served} served, ${r.unserved.length} unserved`);
    }));
  },

  // A minimal fetch so the Worker is valid even though the fleet is
  // cron-driven. Returns the supervisor's current view for a health probe.
  async fetch(request: Request, env: BrainEnv): Promise<Response> {
    if (new URL(request.url).pathname === "/health") {
      const supervisor = env.BRAIN_SUPERVISOR.get(env.BRAIN_SUPERVISOR.idFromName("fleet"));
      const r = await supervisor.tick();
      return new Response(JSON.stringify({ ok: true, ...r }), {
        headers: { "content-type": "application/json" },
      });
    }
    return new Response("brain fleet — cron-driven; POST nothing here", { status: 404 });
  },
};
