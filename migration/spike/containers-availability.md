# SPIKE: Cloudflare Containers, after the Workers Paid upgrade

Checked 2026-09-04, account `114587b715e702461766369b01d42fc7`.

## Containers is now available

    $ wrangler containers list
    No containers found.

Before the upgrade this was *"Unauthorized: You do not have access to
Cloudflare Containers. Deploying containers requires the Workers Paid plan."*
So the plan change landed and `brain/` has somewhere to run.

## R2 is NOT yet enabled — it is a separate opt-in

    $ wrangler r2 bucket list
    Please enable R2 through the Cloudflare Dashboard. [code: 10042]

Workers Paid does not turn R2 on. It is its own product subscription:
Dashboard -> R2 Object Storage -> Enable. Still outstanding.

## Building an image needs Docker, and this machine has none

    $ wrangler containers build .
    The Docker CLI is needed to build the image but could not be launched.

Wrangler shells out to a Docker-compatible CLI to build and push the image;
`WRANGLER_DOCKER_BIN` + `DOCKER_HOST` can point it at Podman instead.

**Treat this as a finding about WHERE the brain image should be built, not as a
missing laptop dependency.** A production image built by hand on one person's
Mac is not reproducible, is not attested, and is exactly the shape that let a
stale image serve production twice before (see CLAUDE.md's live-deploy rule and
`research/2026-08-26-hq-deploy-clobber.md`). The image should be built and
pushed by GitHub Actions, whose runners already have Docker, and the deploy
verified afterwards by an `is_it_live.py`-style fingerprint check.

Installing Docker Desktop locally is still worth doing for iteration, but it
should not be the path production ships through.

## The real design question, unchanged by any of this

Cloudflare Containers are started on demand by a Durable Object and sleep when
idle. `brain/supervisor.py` is a loop that ticks on its own and keeps state in
memory between ticks. Those two models do not meet by themselves.

The mapping that does work: the Durable Object owns an **alarm**, the alarm
wakes on a schedule, and each wake ensures the container is up and drives one
tick. That turns "a process that runs forever" into "a tick somebody is
responsible for firing" — which is a truer description of a worker that polls
PocketBase anyway, and it has the side benefit that a missed tick becomes
visible instead of silent. The 30-hour deaf-ears incident that
`overnight/are_the_ears_live.py` exists to catch was precisely a silent
non-tick.

What must NOT be assumed: that in-memory state survives between ticks. It does
not, once the container sleeps. Every piece of state `brain/` currently keeps in
process has to move to D1, Durable Object storage, or R2 — and that includes the
per-owner `memory.db`, which today lives on a second Railway volume and is the
assistant's long-term memory.

## Not proven here

No container was deployed. Availability, the Docker requirement, and the R2 gap
are measured facts; the alarm-driven design above is a design, not a result.
