"""After a crash, the retry cites what was found — and the guard reads it.

Audit #90, correction (E). A browser worker reclaimed between a consequential
click and its receipt leaves the row `effect_uncertain`. The DB guard
(`migration/workers/src/policy/workflow_guard.ts`, the effect_uncertain block) refuses
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

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


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


SWIFT = ROOT / "app" / "ios" / "Anticipy" / "Backend" / "RetryReconciliationPolicy.swift"
JS = ROOT / "extension" / "reconcile.js"


SESSION = ROOT / "app" / "ios" / "Anticipy" / "AnticipyApp.swift"


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
