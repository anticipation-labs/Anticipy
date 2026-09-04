# Calibration audit — is the oracle honest now?

Independent verification of the three reconciliation tracks that edited
`migration/spec/contract_tests.py`. Run against the live PocketBase at
`https://backend-production-61e0a.up.railway.app`, twice, plus direct curl
probes of every load-bearing claim.

**Verdict: the edits are clean. No test was weakened. Ten assertions were made
STRICTER. The suite can now be trusted as an oracle for STATUS and SENTENCE —
with one structural caveat about `xfail` that has to be fixed before the
PocketBase/Worker diff step is run.**

---

## 1. The run

    16 failed, 77 passed, 70 skipped, 2 deselected, 27 xfailed in ~29s

Reproduced three times with identical counts. Command:

    export ANTICIPY_SERVICE_TOKEN=$(grep -o '[^=]*$' migration/workers/.dev.vars)
    BASE_URL=https://backend-production-61e0a.up.railway.app \
      python -m pytest migration/spec/contract_tests.py -m "not destructive" -q

## 2. Delta against `pocketbase.xml`

|              | baseline | now | delta |
|--------------|---------:|----:|------:|
| tests in XML |      187 | 190 |    +3 |
| failed       |       42 |  16 |   -26 |
| xfailed      |        0 |  27 |   +27 |
| passed       |       75 |  77 |    +2 |
| skipped      |       70 |  70 |     0 |

**Nothing was deleted.** A name-level diff of the two JUnit files shows zero
tests present in the baseline and absent now. The three added tests are
`test_ENTRY_STATUSES_is_not_satisfied_by_equipping_the_other_leg[running|done]`
(both xfail) and `test_the_owner_sentinel_is_inert_to_the_guard` (passes).

Every outcome change is accounted for, and the arithmetic closes exactly:

    42 failures
      - 2  genuinely fixed by the HTTP-header harness bug fix (TestHQFrontDoor:
           test_cors_echoes_an_allowed_origin, test_the_hq_page_either_serves...)
      + 1  test_cors_refuses_an_unlisted_origin, which PASSED in the baseline
           only because every header lookup returned None, and now genuinely
           fails -> xfail
      + 2  new entry-table tests
      = 43 red  =  16 failed + 27 xfailed          OK

    75 passes + 2 (header fix) - 1 (CORS) + 1 (new sentinel test) = 77   OK

The skipped count is unchanged at 70. **No test was converted into a skip.**

## 3. Cheating audit — result: NONE FOUND

Method: AST-level comparison of every `assert` expression and every decorator
in the pre-change tree (`841023eb`) against the current file, rather than
reading the diff by eye.

    test functions removed ............ 0
    parametrize cases removed ......... 0
    skip / skipif marks added ......... 0
    assertions dropped ................ 0  (assert COUNT identical in all 190)
    functions with changed assertions . 11 of 190

All eleven changes are the same substitution, and **ten of them are
TIGHTENINGS**:

    OLD:  assert resp.status == 409
    NEW:  assert guard_refused(resp)

where `guard_refused(resp)` is `status == 409 AND body["error"] ==
"workflow violation"`. A backend that answers 409 from anything other than the
workflow guard now FAILS where it used to pass. That is the opposite of
widening an accept list. Every downstream `detail_of(resp) == "<exact
sentence>"` assertion is byte-identical to before.

### The one technical widening, named

`test_legacy_row_without_workflow_id_skips_the_whole_guard`:

    OLD:  assert resp.status != 409
    NEW:  assert guard_admitted(resp)      # == not guard_refused(resp)

A 409 whose body is *not* `{"error":"workflow violation"}` would now pass where
it used to fail. This is defensible — the test's own docstring pins exactly
"can never produce a 409 workflow violation" — but it is a widening and it is
recorded here rather than waved through. Two residual soundness notes on
`guard_admitted`, both low severity and both affecting only this one test:
a 5xx from a broken Worker counts as "admitted", and so does a 404.

### The three rules that had to stay exact — all three verified intact

| rule | where | status |
|---|---|---|
| password_reset's identical reply | `TestPasswordReset.SAME`, and `a.body == b.body` byte comparison at :2098 / :2113 | **untouched**, still passing |
| evidence's single public sentence | `error_of(resp) == "that evidence is not available"` at :1868, :1879, :1890 | **untouched** (now xfail because the server stopped saying it) |
| the `\|\|` owner-filter refusal | `test_an_account_may_not_widen_its_filter_with_OR` at :1503 | **untouched** |

No line matching any of those three appears on the `-`/`+` side of the diff.
The only diff hits on those strings are inside new explanatory comments.

## 4. Are the xfail reasons evidence-backed? Yes.

Eight reason constants, none of them "known failure". Each names the hook file
and line, what the server actually answered, and how it was established. Spot-
checked independently by curl — every claim held:

    GET  /api/collections/agents/records    -> 400 "Something went wrong"   PROD_AGENTS_LIST_IS_BROKEN
    GET  /api/collections/pendants/records  -> 200 {"items":[]}             (the control — same guard)
    GET  /api/files/evidence/<id>/x.png     -> 404 PocketBase's own body    evidence routerUse absent
    POST /evidence/share                    -> 404 router-miss body         ROUTE_ABSENT_IN_PRODUCTION
    POST /me/phone/remove                   -> 404 router-miss body         ROUTE_ABSENT_IN_PRODUCTION
    POST /me/profile/upsert                 -> 404 router-miss body         ROUTE_ABSENT_IN_PRODUCTION
    POST /agent/upgrade-credential          -> 404 {"error":"agent not found"}   <- THE HOOK'S OWN BODY

That last line confirms Track 2's correction to the brief: `/agent/upgrade-
credential` is **live**, not absent. It answers from `agent_auth.pb.js`, not
from PocketBase's router miss. It was correctly left unmarked and it passes.
Marking it would have written a false divergence into the oracle.

### The middleware-order claim, verified directly

The brief's established triage said 25 failures were a fixture bug — an
`owner_ref` that is not a real relation record, rejected by schema validation
"before the workflow guard ever runs". **That is wrong, and it was worth
catching.** Same request body, only `status` varied:

    status=running    -> 409 {"error":"workflow violation",
                              "detail":"running work needs an actor and lease"}
    status=cancelled  -> 400 validation_missing_rel_records on owner_ref
    status=failed     -> 400 validation_missing_rel_records on owner_ref

Middleware order does not depend on the payload. The guard runs first; a 400 on
`owner_ref` means it ran, called `e.next()`, and PocketBase stopped the INSERT
*afterwards*. So a 400 is an **admission**, not a skipped guard.

### The cost of the brief's prescribed fix, measured

Swapping in a real `owner_ref` — the fix the brief asked for — was driven once
against production with the exact body from
`test_a_created_row_may_not_be_born_holding_a_lease`:

    owner_ref = OWNER_UNDER_TEST   -> 400  (relation check; nothing written)
    owner_ref = <real owners id>   -> 200  A REAL JOB ROW WAS CREATED,
                                           status=queued, holding lease_token

That is the whole argument in one measurement. The sentinel is a deliberate
write barrier, the guard genuinely admits the row, and following the brief
literally would have minted ~21 junk rows per run onto a live person's account.

### Zero-write claim: independently confirmed

    jobs.totalItems      before a full non-destructive run: 173   after: 173
    lane=device_calendar before: 11   after: 11

The suite no longer pollutes production. Before these edits it did, on every
run — 11 live `queued` / `lane=device_calendar` rows reading "put dinner on my
calendar" are still sitting in the table (ids `h0ps01pf1212hb3`,
`b6q9c6no2jjrewn`, `96xzgdtw7cgv0sw`, `6q2xbwgkqslqsbh`, `8t5q2attunv13pd`,
`hqlqau77qukep4p`, `tmqe7i7tlsrurbt`, `m7oa1xm5rlotwbm`, `2fu63ii72afcynm`,
`facjb5gdpeu0tkr`, `wqe326mzfm8lhwr`), plus several no-`workflow_id` rows.
They still need sweeping; that is a destructive write nobody has authorised yet.

## 5. The 16 tests left red are right to be red

Five `test_approval_gate_fails_closed_on_every_other_consequence` cases, one
`test_a_created_row_may_not_be_born_holding_a_lease`, and ten Shelf 2 admission
tests. Confirmed by direct probe:

    consequence="consequential"  -> 409 "consequential work needs parseable approval"
    consequence="reversible"     -> ADMITTED
    consequence="consequentia"   -> ADMITTED
    consequence=""               -> ADMITTED

Owner approval on the deployed image is demanded only when one string is spelled
exactly right. Leaving these red rather than xfail is the correct call: they
describe the unapproved-execution path, and an `xfail` would print a green
summary line for "owner approval is not enforced in production".

---

## 6. THE ONE THING TO FIX BEFORE THE DIFF STEP — `strict=False`

This is the only real problem left, and it is structural, not a cheat.

All 27 xfails are non-strict (`ROUTE_ABSENT_IN_PRODUCTION` says
`strict=False` explicitly; the `pytest.mark.xfail(reason=...)` marks inherit
`xfail_strict=False`, which `pytest.ini` does not override). Therefore:

* a Worker that **correctly implements the contract** -> XPASS -> exit 0, green
* a Worker that **copies the production hole** -> XFAIL -> exit 0, green

Both are green. Worse, pytest writes XFAIL into JUnit XML as `<skipped
type="pytest.xfail">` — the same element a genuinely skipped test produces —
so a name-only diff of the two XML files cannot tell "the Worker reproduced the
hole" from "that test didn't run". Track 3 flagged exactly this and declined to
fix it because `conftest.py` was being edited concurrently. It is still unfixed.

The refreshed `pocketbase.xml` shows the trap on its own first line — the
suite-level attribute reads `skipped="97"`, which is 70 real skips and 27
xfails added together with nothing to separate them:

    <testsuite errors="0" failures="16" skipped="97" tests="190" ...>

**Recommended, one small change, no assertion touched:** register a
`production_divergence` marker in `migration/spec/conftest.py` and apply it
alongside each `xfail`, so the two backends' runs can be selected apart
(`-m "production_divergence"`) rather than both landing in the skipped bucket.
The comparison script must read the `type` attribute on `<skipped>`, not just
test names. Until then, **the diff step must be run by a tool that distinguishes
xfail from skip and treats an XFAIL on the Worker as a FAILURE.**

Secondary, and the agents themselves asked for a ruling: two conventions are
live in this file at once. Sixteen genuine production holes are left **red**
(approval gate, Shelf 2, lease-at-birth) while twenty-seven equally genuine ones
are **xfail**. Both choices are defended in comments; neither is wrong; they
should not both be here. Somebody who owns the reconciliation has to pick one.

---

## 7. Can this suite be trusted as an oracle?

**For the 93 tests that are green or red on their own merits: yes.** A failure
means the Worker is wrong. The assertions are stricter than they were, the
harness can now actually read a response header (it could not before — one test
was passing *because* every header lookup returned None), the fixtures no longer
write to production, and the suite audits its own sentinel
(`test_the_owner_sentinel_is_inert_to_the_guard` — if that goes red, every
result in `TestWorkflowGuard` is suspect).

**For the 27 xfailed tests: not yet, not automatically.** The assertions are
correct and unweakened, so a *human* reading the output learns the truth. But
the exit code and a naive XML diff do not distinguish a correct Worker from one
that shipped the same holes. Fix `strict`/marker handling first.

**And the load-bearing conclusion for the port, which the tracks got right: the
Worker must implement THIS REPO, not the running image.** The deployed
PocketBase is missing three security commits dated 2026-08-25 (`afd4380a`,
`5f66016c`, `9748acf4`) and at least three whole hook files. A Worker validated
against what production answers would ship every one of those holes.

---

## Appendix — audit artefacts

* Suite runs: 3, identical counts.
* Probes: 7 route probes, 3 middleware-order probes, 4 approval-gate probes,
  3 sentinel-inertness probes, 2 row-count probes.
* **Auditor's own stray write:** the sentinel-inertness probe run with a *real*
  `owner_ref` created one row, `2onrd9mg7k3tiae` (`status=queued`,
  `consequence=read_only`, `lease_token=lease-abc`, owner `43dl3t9oz7q34qc`).
  Deleting it was blocked by the permission classifier and was not worked
  around. **It needs sweeping along with the 11 device_calendar rows.** It is
  also the direct proof of the lease-at-birth finding.
* **Not requested, but it happened:** the three tracks' edits were told never to
  commit, and they are now committed. Commit `9704b151`
  ("Production is not built from this repo: 0 of 10 static files match", by a
  concurrently-running process at 20:35) swept in all 669 changed lines of
  `contract_tests.py` plus both research notes. This audit was performed against
  that content and the finding is unaffected, but the commit message does not
  describe the contract-suite change it carries.
