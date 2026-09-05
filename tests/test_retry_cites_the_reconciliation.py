"""After a crash, the retry cites what was found — and the guard reads it.

Audit #90, correction (E). A browser worker reclaimed between a consequential
click and its receipt leaves the row `effect_uncertain`. The DB guard
(`backend/pb_hooks/workflow_guard.pb.js`, the effect_uncertain block) refuses
to let that row back to `queued` unless the PATCH carries a `reconciliation`
with `conclusion: "not_applied"`, a matching `effect_key`, `verified: true`,
non-empty `owner_words` and a non-empty `evidence` list.

Until 2026-09-05 the phone satisfied every one of those with a literal:
`app/ios/Anticipy/AnticipyApp.swift` `approvalFields` wrote conclusion
"not_applied", evidence ["owner explicitly checked the destination before
retry"] and owner_words "I checked the site; the action did not happen. Try
again." for every uncertain row the owner tapped — whether or not anyone had
checked anything. The guard cannot tell a literal from a finding, so a crash
plus a tap re-sent the submission.

The extension now looks (`extension/reconcile.js`) and writes
`params._reconciliation = {verdict, evidence, at}` in four states; the phone
(`RetryReconciliationPolicy.swift`) reads that row and lets a retry carry a
reconciliation only on a positive `not_applied`, citing the row's evidence
plus the one line that is genuinely his — the tap.

Three things are driven here, and none of them is a grep standing in for a
behaviour:

  1. THE GUARD'S LEG, with the shape the phone now sends: a not_applied row
     is admitted; every other conclusion, an absent reconciliation, an empty
     evidence list, a foreign effect key, and a body that keeps the effect
     uncertain are each refused with the guard's own sentence.
  2. THE SPELLINGS, across the language boundary: the four verdict tokens the
     Swift enum reads are byte-for-byte the four `reconcile.js` exports, and
     the params key is the one `reconciliationParams` writes. If either side
     renames one the phone reads every row as unreadable — closed, but
     silently un-retryable — and this is what says so.
  3. THE SWIFT FLOOR, run: `app/ios/Tests/run_retry_reconciliation_tests.sh`
     compiles the real policy and drives it, and this leg runs that runner so
     the Python suite shows it running. Skipped, and said so, where there is no
     swiftc — never green by absence.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.test_workflow_guard_fails_closed import HARNESS, HOOKS, ROOT


JOB_ID = "job0000000000090"
OWNER = "own0000000000090"
PLAN = "wf-0090"
SCOPE = "scope-digest-090"
EFFECT = "effect-key-090"
GOAL = "book a table at Earls for four at 7"
NOW = "2026-09-05T18:10:00Z"

# The row exactly as extension/reconcile.js `reconciliationParams` writes it.
def found(verdict: str, evidence=None):
    if evidence is None:
        evidence = ["host:fixture.test",
                    "control:Clicking Book table on fixture.test",
                    "page:https://fixture.test/book", "title:Book a table",
                    "fingerprint:abc123", f"verdict:{verdict}"]
    return {"verdict": verdict, "evidence": evidence, "at": "2026-09-05T18:02:11.000Z"}


def phone_reconciliation(verdict: str, evidence=None, effect_key: str = EFFECT):
    """What RetryReconciliationPolicy lets `approvalFields` cite: the row's
    conclusion spelled as the row spells it, its evidence verbatim, and the
    tap as one more line."""
    row = found(verdict, evidence)
    return {
        "effect_key": effect_key,
        "conclusion": row["verdict"],
        "verified": True,
        "owner_words": "Tapped “I checked, try again”.",
        "evidence": list(row["evidence"]) + [
            f"owner tapped \"I checked, try again\" on the phone at {NOW}"],
        "checked_at": row["at"],
        "recorded_at": NOW,
    }


def retry(reconciliation, *, row_verdict="not_applied", effect_uncertain=False):
    """Drive the phone's PATCH for an uncertain needs_user row back to queued.

    Everything but `reconciliation` and `effect_uncertain` is the ordinary,
    well-formed shape `approvalFields` sends: a fresh version-bound approval,
    the embedded plan re-queued, no lease, no receipt.
    """
    approval = {"plan_id": PLAN, "plan_version": 2, "scope_digest": SCOPE,
                "owner_words": "Tapped “I checked, try again”.",
                "approved_at": NOW}
    base = {
        "plan_id": PLAN, "version": 2, "goal": GOAL,
        "consequence": "consequential", "lineage_key": "lin-90",
        "owner_ref": OWNER, "scope_digest": SCOPE, "effect_key": EFFECT,
        "attempts": 1, "receipt": None, "lease": None, "required": [],
        "facts": {},
    }
    old_embedded = dict(base, state="needs_user", approval=approval)
    old_params = {"_workflow": old_embedded,
                  "_effect_intent": {"doing": "Clicking Book table on fixture.test",
                                     "url": "https://fixture.test/book",
                                     "sig": "s1g", "digest": "d1gest", "step": 4},
                  "_reconciliation": found(row_verdict)}
    new_embedded = dict(base, state="queued", approval=approval, attempts=0,
                        reason="approved by owner", updated_at=NOW)
    new_params = dict(old_params, _workflow=new_embedded, authorized=True,
                      approved_scope=f"Task: {GOAL}")
    body = {
        "status": "queued", "workflow_state": "queued", "workflow_version": 2,
        "attempts": 0, "scope_digest": SCOPE, "effect_key": EFFECT,
        "approval": json.dumps(approval), "params": json.dumps(new_params),
        "lease_token": "", "lease_until": "", "receipt": "",
        "effect_uncertain": effect_uncertain,
        "reconciliation": json.dumps(reconciliation) if reconciliation is not None else "",
    }
    scenario = {
        "path": f"/api/collections/jobs/records/{JOB_ID}",
        "method": "PATCH",
        "body": body,
        "old": {
            "id": JOB_ID, "workflow_id": PLAN, "workflow_version": 2,
            "workflow_state": "needs_user", "status": "needs_user",
            "consequence": "consequential", "goal": GOAL, "lineage_key": "lin-90",
            "owner_ref": OWNER, "scope_digest": SCOPE, "effect_key": EFFECT,
            "attempts": 1, "lease_token": "", "lease_until": "",
            "approval": json.dumps(approval), "receipt": "",
            "effect_uncertain": True, "reconciliation": "",
            "params": json.dumps(old_params),
        },
    }
    proc = subprocess.run(
        ["node", "-e", HARNESS, "--", json.dumps(scenario), str(HOOKS)],
        capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise AssertionError(f"harness failed: {proc.stderr[-3000:]}")
    out = json.loads(proc.stdout)
    assert out["threw"] is None, out["threw"]
    return out


def detail(out):
    return (out.get("body") or {}).get("detail")


# ----------------------------------------------------------- 1. the guard's leg

def test_a_retry_that_cites_a_not_applied_row_is_admitted():
    """The shape the phone sends now: conclusion read off the row, the row's
    evidence first, the tap last. This is the one write that may move an
    uncertain row back to queued, and it has to keep working."""
    out = retry(phone_reconciliation("not_applied"))
    assert out["outcome"] == "next", out


@pytest.mark.parametrize("verdict", ["applied", "unclear", "no_verdict"])
def test_every_other_verdict_is_refused_even_when_cited_honestly(verdict):
    """The phone never sends these — `mayRetry` refuses first — but the guard
    is the layer that has to be right when the phone is stale or lying, so
    the same honest citation of any other verdict must be a 409."""
    out = retry(phone_reconciliation(verdict), row_verdict=verdict)
    assert out["outcome"] == "json" and out["status"] == 409, out
    assert detail(out) == "uncertain effect was not proven safe to retry", out


def test_a_retry_with_no_reconciliation_is_refused():
    out = retry(None)
    assert out["outcome"] == "json" and out["status"] == 409, out
    assert detail(out) == "uncertain effect needs reconciliation before retry", out


def test_a_retry_that_keeps_the_effect_uncertain_is_refused():
    """Citing not_applied while leaving the flag up is a write that says two
    things at once; the guard takes the flag."""
    out = retry(phone_reconciliation("not_applied"), effect_uncertain=True)
    assert out["outcome"] == "json" and out["status"] == 409, out
    assert detail(out) == "uncertain effect was not proven safe to retry", out


def test_an_empty_evidence_list_is_refused():
    """The reason RetryReconciliationPolicy refuses a not_applied row with
    nothing behind it: the tap line is appended, never substituted, and a
    citation with no lines is not a citation."""
    bare = dict(phone_reconciliation("not_applied"), evidence=[])
    out = retry(bare)
    assert out["outcome"] == "json" and out["status"] == 409, out


def test_a_reconciliation_for_another_effect_is_refused():
    out = retry(phone_reconciliation("not_applied", effect_key="effect-key-other"))
    assert out["outcome"] == "json" and out["status"] == 409, out
    assert detail(out) == "uncertain effect was not proven safe to retry", out


def test_the_old_constant_would_still_satisfy_the_guard():
    """Stated rather than hidden: the guard reads shape, not provenance. The
    literal the phone used to write passes it today exactly as it did on
    2026-09-04. That is WHY the phone's floor exists and why the Swift leg
    below is not optional — the guard cannot see a made-up finding, only a
    missing one."""
    constant = {
        "effect_key": EFFECT, "conclusion": "not_applied", "verified": True,
        "owner_words": "I checked the site; the action did not happen. Try again.",
        "evidence": ["owner explicitly checked the destination before retry"],
        "recorded_at": NOW,
    }
    out = retry(constant, row_verdict="applied")
    assert out["outcome"] == "next", (
        "if the guard has learned to tell a literal from a finding, update "
        f"this pin and RetryReconciliationPolicy's header together: {out}")


# ------------------------------------------------------------ 2. the spellings

SWIFT = ROOT / "app" / "ios" / "Anticipy" / "Backend" / "RetryReconciliationPolicy.swift"
SESSION = ROOT / "app" / "ios" / "Anticipy" / "AnticipyApp.swift"
JS = ROOT / "extension" / "reconcile.js"


def _code(text: str) -> str:
    return "\n".join(line.split("//", 1)[0] for line in text.splitlines())


def test_the_phone_reads_exactly_the_verdicts_the_extension_writes():
    js = _code(JS.read_text())
    wire = dict(re.findall(r'export const (APPLIED|NOT_APPLIED|UNCLEAR|NO_VERDICT) = "([^"]+)"', js))
    assert set(wire) == {"APPLIED", "NOT_APPLIED", "UNCLEAR", "NO_VERDICT"}, wire
    swift = _code(SWIFT.read_text())
    enum = re.search(r"enum Verdict: String[^{]*\{(.*?)\n    \}", swift, re.S)
    assert enum, "RetryReconciliationPolicy.Verdict is gone"
    cases = {}
    for line in enum.group(1).splitlines():
        m = re.match(r"\s*case (\w+)(?: = \"([^\"]+)\")?", line)
        if m:
            cases[m.group(1)] = m.group(2) or m.group(1)
    assert set(cases.values()) == set(wire.values()), (
        "the Swift verdicts and the JS verdicts have drifted; the phone would "
        f"read every row with the renamed token as unreadable: {cases} vs {wire}")
    assert 'static let key = "_reconciliation"' in swift
    assert "_reconciliation: { verdict, evidence, at:" in js, (
        "reconciliationParams no longer writes _reconciliation as {verdict, evidence, at}")


def test_the_phone_no_longer_cites_a_constant():
    """Comment-stripped, because approvalFields now quotes the old literals in
    the comment that explains their removal."""
    swift = _code(SESSION.read_text())
    for literal in ("owner explicitly checked the destination before retry",
                    "I checked the site; the action did not happen",
                    '"conclusion": "not_applied"'):
        assert literal not in swift, f"the phone is citing a constant again: {literal}"
    start = swift.find("private func approvalFields(")
    assert start > 0
    body = swift[start:swift.find("\n    private func cancellationFields", start)]
    assert "RetryReconciliationPolicy.mayRetry(" in body
    assert "RetryReconciliationPolicy.retryEvidence(" in body
    assert '"conclusion": row.verdict.rawValue' in body
    assert body.index("RetryReconciliationPolicy.mayRetry(") \
        < body.index('fields["reconciliation"] = '), (
        "the floor must be asked before the reconciliation is assembled")


# ---------------------------------------------------------- 3. the Swift floor

def test_the_swift_floor_runs():
    if shutil.which("swiftc") is None:
        pytest.skip("no swiftc on this machine; the Swift floor was not driven here")
    runner = ROOT / "app" / "ios" / "Tests" / "run_retry_reconciliation_tests.sh"
    proc = subprocess.run(["sh", str(runner)], capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-3000:]
    assert "RetryReconciliationPolicyTests: all passed" in proc.stdout, proc.stdout[-2000:]
    assert "FAIL:" not in proc.stdout, proc.stdout
