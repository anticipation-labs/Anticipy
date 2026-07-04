# browser_eval task bundles

The un-gameable browser scoreboard (PLAN §7). Each `<id>/` directory is one
real-world FORM+ACTION task the browser agent must complete end-to-end, graded by
an **independent functional checker** — never the agent's own "done."

Driver: `engine/scripts/browser_eval.py`
- live lane:  `engine/.venv/bin/python engine/scripts/browser_eval.py` (engine on
  :8787, extension connected) → drives `POST /agent/run`, then runs each checker.
- dry lane:   `... browser_eval.py --selftest` (no engine, no Chrome) → proves the
  harness + every checker + the scorecard math, and that each checker PASSES a
  good result and FAILS a faked one.

## Bundle contract
```
<id>/
  spec.yaml     # id, kind, start_url, max_steps, task (may contain {NONCE} /
                # {LOCAL_FORM_URL}, substituted at run time), commit_boundary, needs
  checker.py    # the functional gate (below)
  server.py     # (optional) a grader-owned backend the checker re-reads
```
`checker.py` exposes:
- `check(result, ctx) -> (ok: bool, detail: str)` — **independently** re-reads the
  world (server echo / backend `/last` / a fresh page fetch via `ctx["http_get"]`);
  must not trust `result["answer"]`.
- `synth_pass(ctx) -> result` / `synth_fail(ctx) -> result` — fixtures the
  `--selftest` lane feeds the checker; the good one must pass, the faked one
  (agent claims done but the world never changed) must fail.
- optional `setup(ctx)` / `teardown(ctx)` / `start_url(ctx)`.

`ctx` carries a fresh `nonce` (unforgeable per-run marker), `http_get` (the
re-read primitive; a checker may swap in an offline stub for selftest), and any
handle `setup()` stashes (e.g. the local form server).

## The three tasks
| id | independent postcondition |
|----|---------------------------|
| `httpbin_form` | the planted `ANTICIPY-<nonce>` appears in httpbin's echoed JSON (round-trips only through a real submit) — read from the browser's page read-back, not the model prose |
| `local_form`   | the grader-owned backend's `GET /last` record matches the exact submitted fields (gold-standard: verifies what the server actually received) |
| `wiki_search`  | the checker fetches the canonical article itself, confirms the ground-truth token is really there, then requires the agent's answer to contain it AND the agent to have reached the article |

## Scorecard
`pass-rate · $/task (+ $/successful task) · steps · tier-mix (frontier% / vision%
/ region% / replay%)`.

## Live-lane note (SSRF)
`/agent/run` refuses loopback/private start URLs, so `local_form` in a live run is
pointed at a public tunnel via `ANTICIPY_LOCALFORM_URL`; the checker still reads
`/last` on the same backend.
