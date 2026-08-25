"""The final authority must not depend on a word being spelled correctly.

`backend/pb_hooks/workflow_guard.pb.js` calls itself "the final authority for
workflow transitions" in its own first line, and it is the layer this
architecture puts the seatbelt in — in code, not in the model. It demanded
owner approval before consequential work could reach `queued` like this:

    if (nextStatus === "queued" && consequence === "consequential") { ... }

Approval was demanded only when `consequence` was that ONE exact string. A
typo, an empty value, a truncated write, a `consequence` the brain never set,
or any third enum value added later skipped the whole block and reached
`queued` UNAPPROVED. Deny-by-default inverted into allow-by-default by a
string comparison.

Every other layer in the system already fails the other way:

  brain/workflow.py:64-68   `_consequence_or_safe` — unreadable becomes
                            CONSEQUENTIAL, and its comment says why in so many
                            words: "work whose consequence cannot be read is
                            treated as world-changing (it gets every gate)".
  extension/background.js:1062, 1300-1301
                            `job.consequence !== "read_only"` — an allowlist,
                            so anything unrecognised is treated as world-
                            changing.
  app/ios/…/AnticipyApp.swift:1352
                            `as? String ?? "consequential"` — a missing key
                            defaults to the careful side.

So the database guard was the ONLY layer that failed open, and it is the one
that is supposed to still be right when every other layer is stale or lying.
Fixed by enumerating the safe set instead: `read_only` is exempt, everything
else — including anything unrecognised — needs owner approval bound to this
exact plan version.

There was no test driving this hook at all before this file. That is why it
survived: `tests/test_approved_card_is_closed_to_edits.py` and
`tests/test_goal_spelling_matches_the_plan.py` both cite workflow_guard by
line number and neither has ever executed a byte of it.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "backend" / "pb_hooks"


HARNESS = r"""
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const args = process.argv.slice(-2);
const scenario = JSON.parse(args[0]);
const HOOKS = args[1];

let useSource = null;
const loader = { routerUse: (fn) => { useSource = String(fn); },
                 console: { log: () => {} } };
vm.createContext(loader);
vm.runInContext(fs.readFileSync(path.join(HOOKS, 'workflow_guard.pb.js'), 'utf8'), loader);

// A FRESH context, holding only what the PocketBase JSVM gives a handler.
// A `const` at the top of a hook file is not in scope inside the callback
// (account_delete.pb.js:42-56 measured it against a local 0.30.4), and a
// harness that reuses the loader context would never notice.
const isolated = { console: { log: () => {} } };
vm.createContext(isolated);
const handler = vm.runInContext('(' + useSource + ')', isolated);

const old = scenario.old;
const record = old ? {
  id: old.id,
  get: (k) => old[k],
  getString: (k) => (old[k] === undefined || old[k] === null) ? "" : String(old[k]),
  getBool: (k) => !!old[k],
} : null;

let outcome = 'none';
let status = 0;
let body = null;
const e = {
  next: () => { outcome = 'next'; return 'NEXT'; },
  json: (s, b) => { outcome = 'json'; status = s; body = b; return 'JSON'; },
  app: {
    findRecordById: (collection, id) => {
      if (!record || collection !== 'jobs' || id !== record.id) throw new Error('no rows');
      return record;
    },
  },
  requestInfo: () => ({ body: scenario.body || {} }),
  request: {
    method: scenario.method || 'PATCH',
    url: { path: scenario.path, query: () => ({ get: () => '' }) },
    header: { get: (k) => (scenario.headers || {})[k] || '' },
  },
};

let threw = null;
try { handler(e); } catch (err) { threw = String(err) + '\n' + (err && err.stack || ''); }
process.stdout.write(JSON.stringify({ outcome, status, body, threw }));
"""


JOB_ID = "job0000000000001"
OWNER = "own0000000000001"
PLAN = "wf-0001"
SCOPE = "scope-digest-abc"
EFFECT = "effect-key-abc"
GOAL = "book a table at Earls for four at 7"


def attempt(consequence: str, *, approval=None, status="queued", state="queued"):
    """Drive one PATCH that moves an awaiting_confirm job to `queued`.

    Everything except `consequence` and `approval` is a well-formed, ordinary
    request: the same shape the extension and the phone send.
    """
    embedded = {
        "plan_id": PLAN, "version": 2, "state": state, "goal": GOAL,
        "consequence": consequence, "lineage_key": "lin-1", "owner_ref": OWNER,
        "scope_digest": SCOPE, "effect_key": EFFECT, "attempts": 0,
        "approval": approval, "receipt": None, "lease": None,
        "required": [], "facts": {},
    }
    body = {
        "workflow_id": PLAN, "workflow_version": 2, "workflow_state": state,
        "status": status, "consequence": consequence, "goal": GOAL,
        "lineage_key": "lin-1", "owner_ref": OWNER, "scope_digest": SCOPE,
        "effect_key": EFFECT, "attempts": 0, "lease_token": "",
        "approval": json.dumps(approval) if approval else "",
        "params": json.dumps({"_workflow": embedded}),
    }
    scenario = {
        "path": f"/api/collections/jobs/records/{JOB_ID}",
        "method": "PATCH",
        "body": body,
        "old": {
            "id": JOB_ID, "workflow_id": PLAN, "workflow_version": 2,
            "workflow_state": "awaiting_approval", "status": "awaiting_confirm",
            "consequence": consequence, "goal": GOAL, "lineage_key": "lin-1",
            "owner_ref": OWNER, "scope_digest": SCOPE, "effect_key": EFFECT,
            "attempts": 0, "lease_token": "", "lease_until": "",
            "approval": "", "receipt": "", "effect_uncertain": False,
            "params": json.dumps({"_workflow": dict(embedded, state="awaiting_approval")}),
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


def good_approval():
    return {"plan_id": PLAN, "plan_version": 2, "scope_digest": SCOPE,
            "owner_words": "yes go ahead"}


# ------------------------------------------------------ the shape that worked

def test_read_only_work_still_reaches_queued_without_approval():
    """The research lane depends on this: a read of the public web is not
    something he has to say yes to, and making it one would put a card in
    front of him for every question the brain answers on its own."""
    out = attempt("read_only")
    assert out["outcome"] == "next", out


def test_approved_consequential_work_still_reaches_queued():
    out = attempt("consequential", approval=good_approval())
    assert out["outcome"] == "next", out


def test_unapproved_consequential_work_is_still_refused():
    out = attempt("consequential")
    assert out["outcome"] == "json" and out["status"] == 409, out


# -------------------------------------------------------- the fail-open itself

def test_a_misspelled_consequence_does_not_skip_the_approval_gate():
    """One character. `"consequentia"` matched neither the equality check nor
    anything else, so the whole approval block was skipped and the job went to
    queued with no owner words at all — free to act on the world."""
    out = attempt("consequentia")
    assert out["outcome"] == "json", (
        "a job whose consequence is one letter wrong reached queued "
        f"unapproved: {out}")
    assert out["status"] == 409, out


def test_an_empty_consequence_does_not_skip_the_approval_gate():
    """A truncated write, an older client, a row the brain never stamped.
    brain/workflow.py:64-68 treats exactly this as CONSEQUENTIAL."""
    out = attempt("")
    assert out["outcome"] == "json", (
        f"a job with no consequence at all reached queued unapproved: {out}")


def test_a_future_consequence_value_is_safe_by_default():
    """The point of enumerating the SAFE set rather than the dangerous one: a
    third enum member added next month is gated until somebody deliberately
    exempts it here, instead of shipping ungated and nobody noticing."""
    out = attempt("reversible")
    assert out["outcome"] == "json", (
        f"an unrecognised consequence reached queued unapproved: {out}")


def test_an_inherited_property_name_is_not_an_exemption_keyword():
    """The obvious way to write the safe set is `{ read_only: 1 }[consequence]`,
    and that is truthy for "constructor", "toString", "valueOf" and every other
    name on Object.prototype — so the exemption list would ship with half a
    dozen undocumented members an attacker can simply type."""
    for word in ("constructor", "toString", "valueOf", "hasOwnProperty",
                 "__proto__"):
        out = attempt(word)
        assert out["outcome"] == "json", (
            f"consequence={word!r} was treated as exempt from approval: {out}")


def test_the_unrecognised_consequence_is_refused_with_approval_missing_too():
    """And the exemption is not a way IN either: presenting good approval
    words for an unrecognised consequence still has to satisfy the same
    version-bound check, which is the whole point of demanding it."""
    out = attempt("reversible", approval=good_approval())
    assert out["outcome"] == "next", (
        "properly approved work must still be able to proceed whatever its "
        f"consequence is called: {out}")
    stale = dict(good_approval(), plan_version=1)
    out = attempt("reversible", approval=stale)
    assert out["outcome"] == "json", (
        f"approval bound to a different version must not unlock it: {out}")


def test_the_two_layers_now_agree_on_polarity():
    """A source check, deliberately: the reason this bug survived is that the
    Python and the JavaScript disagreed and nothing anywhere compared them."""
    raw = (HOOKS / "workflow_guard.pb.js").read_text()
    # CODE ONLY. The comment above the fix quotes the broken line verbatim so
    # the next reader knows what was wrong; a check that cannot tell prose
    # from a branch would fail on its own explanation.
    js = "\n".join(line.split("//", 1)[0] for line in raw.splitlines())
    py = (ROOT / "brain" / "workflow.py").read_text()
    assert "_consequence_or_safe" in py and "Consequence.CONSEQUENTIAL" in py
    assert 'consequence === "consequential"' not in js, (
        "the guard is back to demanding approval only for one exact spelling; "
        "anything else — a typo, an empty value, a future enum member — walks "
        "straight to queued unapproved")
    assert '"read_only"' in js, (
        "the guard must name the SAFE set explicitly, so that everything it "
        "does not recognise is gated rather than exempt")
