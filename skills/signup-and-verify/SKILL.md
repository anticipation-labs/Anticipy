---
name: signup-and-verify
version: 0.1.0
class: workflow            # a workflow-CLASS skill, not a per-site recipe
params:
  service_url: {type: string, required: true, desc: "signup/home URL of the service"}
  email:       {type: string, required: true, desc: "inbox that receives the verification code"}
  password:    {type: string, required: false}
  username:    {type: string, required: false}
  first_name:  {type: string, required: false}
  last_name:   {type: string, required: false}
core: engine/anticipy_engine/agent/signup_verify.py
uses:
  - engine/anticipy_engine/hands/captcha_solver.py
  - engine/anticipy_engine/hands/email_verifier.py
---

# signup-and-verify

Create an account on an **arbitrary** web service and clear the "we emailed you a code"
step — end to end. This is a **workflow-class** skill: it describes *what* to do in
semantic terms and lets the actor resolve each step against the live page. It has **zero
hardcoded selectors** and is **not Railway-specific** (or specific to any service). The same
skill signs up for Railway, Notion, a newsletter, or a SaaS trial.

## When to use
The task is "make me an account on X" / "sign up for X" and X sends an email verification
code. If the service needs a human decision (payment, ToS the user must accept, a personal
2FA on the *user's* own identity), the skill pauses and hands off — it does not guess.

## Params (typed)
- `service_url` **(required)** — the service's signup or home URL.
- `email` **(required)** — the inbox that will receive the code (must be readable by the
  `email_verifier` tool: fixtures in tests, a Gmail token in production).
- `password`, `username`, `first_name`, `last_name` *(optional)* — filled by meaning when a
  field for them exists.

## Precondition (`check_precondition`)
Runnable only when: params validate, a browser **actor is connected** (the extension is
driving the real Chrome), and the **inbox is reachable**. A captcha **solver is recommended
but optional** — without one, a captcha wall degrades to a handoff (a paused task, not a
failure), never a fake success.

## Steps (abstract, selector-free — `SIGNUP_STEPS`)
1. **navigate** to `service_url` (or its discovered `/signup`).
2. **find the signup form** by semantics (a form with an email + password/register control).
3. **fill identity** — match `email`/`password`/name fields by their visible label/role, not
   by any recorded selector.
4. **submit**.
5. **solve captcha** — if a captcha wall appears, `captcha_solver` auto-solves it
   (reCAPTCHA v2/v3, hCaptcha, Turnstile, image), the extension injects the token, and the
   step re-verifies the wall cleared. On solve-fail → handoff.
6. **await verification** — the "check your email" screen.
7. **read the email code** — `email_verifier.read_verification_code(service_url)` returns the
   latest code the service emailed (regex-first, optional LLM fallback).
8. **enter the code** + submit.
9. **verify signed up** — the contract below.

## Verify contract (un-gameable — this is "done", nothing else is)
"Submitted the form" is **not** done. Done is a **deterministic signed-in read-back**:
`verify_signed_up(observation)` passes only when a signed-in signal is present, no gated
signal ("enter your password", "verification code", "check your email") remains, and — when
supplied — an account-specific `expected_token` (the account email or a dashboard URL) also
appears. For the completed account it is confirmed with `confirm_signed_up`, the **repeated**
delayed read-back (the same seam that gates skill admission), so a post-submit success flash
that reverts to a login wall never counts. The verdict is read from the page, never the model.

## Anti-cheat invariants
- **No hardcoded selectors / no per-site branches.** Steps are semantic; the actor grounds
  them on the live DOM at run time. The captcha response fields (`g-recaptcha-response`,
  `h-captcha-response`, `cf-turnstile-response`) are the *providers'* standard receivers,
  not site selectors.
- **Verification is external.** Success = a signed-in read-back + the emailed code was really
  read, never a self-report.
- **Safety.** During the build this skill performs **no real signup** — all outside I/O is
  injected and exercised with fixtures. Live execution (a real actor + a real inbox token) is
  the final phase. Money / ToS / the user's personal identity always pause → handoff.

## Wiring status
Built in S6. Loop registration (acquire-before-task) lands with the S8 skills pipeline; the
S9 product wire binds an actor to the connected Chrome. Captcha auto-solve is already wired
into the S5 recovery ladder (`agent/guarded_step.py` → the L0 `solve_captcha` remedy).
