"""§8.5 — the middle shelf must not disable the gate by existing.

Spec: `docs/superpowers/specs/2026-08-24-shelf-2-redesign.md` (commit 2f5bdd64),
which calls this "the single highest-risk line item in this card".

THE TRAP, in the spec's own words.  `workflow_guard.pb.js` was fixed in
`afd4380a` to enumerate the SAFE set — `NO_APPROVAL_NEEDED = ["read_only"]` —
so anything it does not recognise is gated.  That means a third `Consequence`
value now fails **closed**: every Shelf 2 row is rejected at `queued` for
having no approval, and not having one is the entire point of the shelf.

    The implementer will hit that rejection, open the file, find §8.5's first
    prescription already implemented, read `NO_APPROVAL_NEEDED` as *the list
    of lanes that run without a tap*, observe that Shelf 2 is by definition a
    lane that runs without a tap, and write:

        const NO_APPROVAL_NEEDED = ["read_only", "reversible"];   // <- DO NOT

    One edit.  It reads as compliance with this very section.

It turns off database-level approval for the new lane and puts NOTHING in its
place.  `read_only`'s exemption is EARNED by a backstop Shelf 2 does not have:
`extension/background.js: runSupervisedReadJob` fails any job whose
`consequence !== "read_only"` outright, and nothing in that lane acts on the
world.  Shelf 2 would inherit the exemption and none of the backstop.

So the positive law is the requirement and the exemption is admissible only as
its consequence.  This file drives the real hook and holds it to a-f:

    a. an undo plan is present and parses
    b. its inputs are a typed, closed list of provenance-tagged references,
       and the guard RESOLVES every one of them — it resolves them, it does
       not read their names
    c. the plan's act_type is a member of the persisted admitted set
    d. the plan's PERSISTED DECLARED REACH equals the reach the admitted set
       records for that act_type
    e. the announcement obligation is recorded on the row
    f. no later act in the same lineage_key invalidates it, for a
       compensating plan

Any of a-f missing, unparseable, or unresolvable is a REJECTION, never a
default.

The bodies below are built by `brain/workflow.py` itself — `job_fields()` for
the row and `as_dict()` for the embedded plan — so this suite fails if the two
layers ever stop agreeing about the shape they both read.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

import pytest

from brain.workflow import (
    ActDeclaration,
    Consequence,
    Gesture,
    Obligation,
    Provenance,
    Refusal,
    UndoInput,
    UndoOf,
    UndoPlan,
    approve,
    approve_by_gesture,
    new_plan,
)


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "backend" / "pb_hooks"

NOW = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
OWNER = "own0000000000001"
JOB_ID = "job0000000000001"
DRAFT_ID = "d4f0c2ee-0000-4000-8000-000000000001"
GOAL = "draft the email to the landlord about the boiler"


# The PocketBase JSVM handed to a hook, plus a `jobs` table the lineage leg
# can read.  A `const` at the top of a hook file is not in scope inside the
# callback on a real PocketBase, so the handler is re-evaluated in a FRESH
# context exactly as tests/test_workflow_guard_fails_closed.py does.
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

const isolated = { console: { log: () => {} } };
vm.createContext(isolated);
const handler = vm.runInContext('(' + useSource + ')', isolated);

const wrap = (row) => row ? {
  id: row.id,
  get: (k) => row[k],
  getString: (k) => (row[k] === undefined || row[k] === null) ? "" : String(row[k]),
  getBool: (k) => !!row[k],
} : null;

const old = wrap(scenario.old);
const lineage = (scenario.lineage || []).map(wrap);

let outcome = 'none';
let status = 0;
let body = null;
let queried = 0;
const e = {
  next: () => { outcome = 'next'; return 'NEXT'; },
  json: (s, b) => { outcome = 'json'; status = s; body = b; return 'JSON'; },
  app: {
    findRecordById: (collection, id) => {
      if (!old || collection !== 'jobs' || id !== old.id) throw new Error('no rows');
      return old;
    },
    findRecordsByFilter: (collection, filter, sort, limit, offset, params) => {
      queried += 1;
      if (scenario.lineageThrows) throw new Error('database unreachable');
      if (scenario.lineageNonsense) return { notAnArray: true };
      if (collection !== 'jobs') throw new Error('unexpected collection');
      // The stub honours the filter it is actually given, so a hook that
      // queries the wrong field gets an empty answer rather than a free pass.
      const key = (params && params.k) !== undefined ? params.k : null;
      const cons = (params && params.c) !== undefined ? params.c : null;
      return lineage.filter((r) =>
        (key === null || r.getString('lineage_key') === String(key))
        && (cons === null || r.getString('consequence') === String(cons)));
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
process.stdout.write(JSON.stringify({ outcome, status, body, threw, queried }));
"""


# --------------------------------------------------------------- plan builders

def act(act_type="local_draft", reach="local_store", executor="anticipy_store"):
    return ActDeclaration(act_type=act_type, reach=reach, executor=executor)


def undo_plan(*, act_type="local_draft", inputs=None, held=None, steps=None):
    return UndoPlan(
        act_type=act_type,
        steps=tuple(steps if steps is not None
                    else ("delete the draft row whose id we minted",)),
        inputs=tuple(inputs if inputs is not None else (
            UndoInput(name="draft_id", provenance=Provenance.MINTED_BY_US.value,
                      ref="draft_id"),
        )),
        held=dict(held if held is not None else {
            Provenance.MINTED_BY_US.value: {"draft_id": DRAFT_ID},
        }),
    )


def shelf2_plan(**kwargs):
    fields = dict(
        owner_ref=OWNER, lineage_key="lin-1", goal=GOAL,
        consequence=Consequence.REVERSIBLE_LOCAL, source_event_id="event-1",
        act=act(), undo=undo_plan(),
        announce=Obligation(channel="sms", owner_ref=OWNER, recorded_at=NOW),
        lineage_seq=1, plan_id="wf-0001", now=NOW,
    )
    fields.update(kwargs)
    return new_plan(**fields)


def row_for(plan, *, status=None, row_id=JOB_ID, embedded_patch=None,
            force_queued=False):
    """The row exactly as production writes it: job_fields() + the embedded
    plan in `params`, with goal and owner_ref which the row carries too.

    `force_queued` is the point of the whole suite.  Python parks work that
    fails `admissible()`, so a plan built here would often never ASK for
    queued and the guard leg would never be reached.  The guard exists for the
    caller that asks anyway — a stale client, a truncated write, a lying
    executor — so these tests send the request Python would have refused to
    make.  This file's own first line calls that layer the final authority.

    The `approval` and `receipt` COLUMNS are recomputed from the (possibly
    patched) embedded plan, because the guard refuses a write that updates
    only the convenient half and that redundancy check runs before any of the
    legs under test.
    """
    embedded = plan.as_dict()
    if embedded_patch:
        embedded = embedded_patch(embedded)
    if force_queued:
        embedded = dict(embedded, state="queued")
    row = dict(plan.job_fields())
    row.update({
        "id": row_id, "goal": plan.goal, "owner_ref": plan.owner_ref,
        "reconciliation": "", "effect_uncertain": False, "claimed_by": "",
        "approval": (json.dumps(embedded["approval"])
                     if embedded.get("approval") else ""),
        "receipt": (json.dumps(embedded["receipt"])
                    if embedded.get("receipt") else ""),
        "params": json.dumps({"_workflow": embedded}),
    })
    if force_queued:
        row["status"] = "queued"
        row["workflow_state"] = "queued"
    if status is not None:
        row["status"] = status
    return row


def drive(plan, *, lineage=(), lineage_throws=False, lineage_nonsense=False,
          embedded_patch=None, headers=None):
    """PATCH one job from awaiting_confirm to queued."""
    row = row_for(plan, embedded_patch=embedded_patch, force_queued=True)
    body = {k: v for k, v in row.items() if k not in ("id",)}
    before = dict(row)
    before["status"] = "awaiting_confirm"
    before["workflow_state"] = "awaiting_approval"
    stale = json.loads(before["params"])
    stale["_workflow"]["state"] = "awaiting_approval"
    before["params"] = json.dumps(stale)
    before["approval"] = ""
    before["receipt"] = ""
    scenario = {
        "path": f"/api/collections/jobs/records/{JOB_ID}",
        "method": "PATCH", "body": body, "old": before,
        "lineage": list(lineage), "lineageThrows": lineage_throws,
        "lineageNonsense": lineage_nonsense,
        "headers": headers or {},
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
    return (out.get("body") or {}).get("detail", "")


def refused(out, cause):
    assert out["outcome"] == "json" and out["status"] == 409, out
    assert detail(out) == cause.value, (
        f"expected {cause.value}, got {detail(out)!r}")


# ------------------------------------------------- the lane exists at all (a-e)

def test_an_admissible_shelf2_act_reaches_queued_with_no_approval():
    """The whole point of a middle shelf: it runs without waiting for a tap.
    If this rejects, there is no Shelf 2 — and if it passes for the WRONG
    reason (a two-element allowlist) every test below is worthless, which is
    why they are all here."""
    out = drive(shelf2_plan())
    assert out["outcome"] == "next", out


def test_the_shelf2_value_is_not_in_a_bare_allowlist():
    """§8.5's forbidden edit, checked as source.  `["read_only", <shelf2>]`
    exempts the new lane and puts nothing in its place.  The exemption here
    must be reachable ONLY through the leg, so that deleting the leg deletes
    the exemption with it rather than leaving a naked allowlist behind."""
    raw = (HOOKS / "workflow_guard.pb.js").read_text()
    js = "\n".join(line.split("//", 1)[0] for line in raw.splitlines())
    assert 'NO_APPROVAL_NEEDED = ["read_only"]' in js, (
        "the earned-exemption shape is gone; if the shelf 2 value is now a "
        "second element of this array it is exempt from approval with no "
        "positive law in its place (§8.5)")
    for line in js.splitlines():
        if "NO_APPROVAL_NEEDED" in line and "=" in line and "[" in line:
            assert Consequence.REVERSIBLE_LOCAL.value not in line, line


def test_read_only_and_consequential_are_untouched_by_the_new_leg():
    """§2: no change to Shelf 3, and no change to the research lane."""
    ro = shelf2_plan(consequence=Consequence.READ_ONLY, act=None, undo=None,
                     announce=None, lineage_seq=0)
    assert drive(ro)["outcome"] == "next", "the research lane must still run"

    bare = shelf2_plan(consequence=Consequence.CONSEQUENTIAL, act=None,
                       undo=None, announce=None, lineage_seq=0)
    out = drive(bare)
    assert out["outcome"] == "json", "unapproved consequential work must wait"
    assert detail(out).startswith("consequential work needs") \
        or detail(out).startswith("approval is not bound"), out

    approved = approve(bare, expected_version=bare.version,
                       owner_words="yes, send it", now=NOW)
    assert drive(approved)["outcome"] == "next", "Shelf 3 still works"


# ------------------------------------------------------------- leg a: the undo

def test_a_shelf2_row_with_no_undo_plan_is_rejected():
    refused(drive(shelf2_plan(undo=None)), Refusal.NO_UNDO_PLAN)


def test_a_shelf2_row_whose_undo_plan_is_not_an_object_is_rejected():
    """"Unparseable is a rejection, never a default."  The guard reads a blob
    a stale client wrote; it may be anything at all."""
    for junk in ("a sentence", 7, [1, 2, 3], True):
        out = drive(shelf2_plan(),
                    embedded_patch=lambda w, j=junk: dict(w, undo=j))
        refused(out, Refusal.NO_UNDO_PLAN)


def test_an_undo_plan_with_no_steps_is_rejected():
    out = drive(shelf2_plan(),
                embedded_patch=lambda w: dict(w, undo=dict(w["undo"], steps=[])))
    refused(out, Refusal.NO_UNDO_PLAN)


def test_an_undo_plan_for_a_different_act_type_is_rejected():
    refused(drive(shelf2_plan(undo=undo_plan(act_type="local_note"))),
            Refusal.UNDO_ADDRESSES_ANOTHER_ACT)


# ---------------------------------------- leg b: RESOLVE, never read the name

def test_the_guard_resolves_references_and_refuses_the_ones_that_do_not():
    """§4's entry condition at the database.  The undo needs a confirmation
    reference the counterparty has not handed back yet, so it does not resolve
    at the moment the row tries to reach queued — which is BEFORE the act
    runs, which is the whole mechanical content of "known-good before
    acting"."""
    out = drive(shelf2_plan(undo=undo_plan(
        inputs=(UndoInput(name="reference", provenance="minted_by_us",
                          ref="confirmation_reference"),),
        held={"minted_by_us": {"draft_id": DRAFT_ID}})))
    refused(out, Refusal.UNRESOLVED_REFERENCE)


def test_the_guard_does_not_read_field_names_in_either_direction():
    """The pair that separates a seatbelt from a word list (§5.2).

    A flattering name that does not resolve is REFUSED; an alarming name that
    does resolve is ADMITTED.  Any implementation that scanned for `{{...}}`,
    for `${`, or for the word "confirmation" fails one of these two, and an
    implementation that reads names fails both."""
    flattering = drive(shelf2_plan(undo=undo_plan(
        inputs=(UndoInput(name="owner_supplied_reference",
                          provenance="owner_supplied",
                          ref="owner_supplied_reference"),),
        held={"owner_supplied": {}})))
    refused(flattering, Refusal.UNRESOLVED_REFERENCE)

    alarming = drive(shelf2_plan(undo=undo_plan(
        inputs=(UndoInput(name="{{confirmation_number}}",
                          provenance="minted_by_us",
                          ref="{{confirmation_number}}"),),
        held={"minted_by_us": {"{{confirmation_number}}": DRAFT_ID}})))
    assert alarming["outcome"] == "next", (
        "a reference the guard already holds was refused because of what it "
        f"is called: {alarming}")


def test_an_undo_plan_that_binds_nothing_is_rejected():
    """The vacuous pass: with no inputs there is nothing to resolve, so
    resolution succeeds and an act whose undo cannot execute runs unattended.
    The admitted set records what each act type's undo must bind."""
    refused(drive(shelf2_plan(undo=undo_plan(inputs=(), held={}))),
            Refusal.UNDO_BINDS_NOTHING)


def test_an_undo_binding_only_the_wrong_provenance_is_rejected():
    out = drive(shelf2_plan(undo=undo_plan(
        inputs=(UndoInput(name="table", provenance="constant", ref="table"),),
        held={"constant": {"table": "drafts"}})))
    refused(out, Refusal.UNDO_BINDS_NOTHING)


def test_an_unrecognised_provenance_tag_is_rejected():
    out = drive(shelf2_plan(undo=undo_plan(
        inputs=(UndoInput(name="draft_id", provenance="returned_by_provider",
                          ref="draft_id"),),
        held={"returned_by_provider": {"draft_id": DRAFT_ID}})))
    refused(out, Refusal.UNKNOWN_PROVENANCE)


def test_an_inherited_property_name_is_not_a_provenance_tag():
    """The same JSVM hazard the file already documents for `consequence`:
    `{ minted_by_us: 1 }[tag]` is truthy for "constructor", "toString" and
    every other name on Object.prototype, so the obvious lookup would ship a
    provenance vocabulary with half a dozen undocumented members."""
    for word in ("constructor", "toString", "valueOf", "hasOwnProperty",
                 "__proto__"):
        out = drive(shelf2_plan(undo=undo_plan(
            inputs=(UndoInput(name="draft_id", provenance=word, ref="draft_id"),),
            held={word: {"draft_id": DRAFT_ID}})))
        assert out["outcome"] == "json", (
            f"provenance={word!r} was accepted as a tag: {out}")
        # The CAUSE, not merely the rejection.  Another leg downstream will
        # also refuse this row, and a test that accepts any refusal cannot
        # tell a closed vocabulary from a lookup that happens to be saved by
        # the next check along.  §11 counts by cause; so does this.
        assert detail(out) == Refusal.UNKNOWN_PROVENANCE.value, (
            f"provenance={word!r} was refused, but not for being unrecognised:"
            f" {detail(out)!r} — the vocabulary is reading a prototype")


def test_an_inherited_property_name_does_not_resolve_a_reference():
    """And the same hazard one level down, on the bucket itself: a reference
    named `constructor` must not resolve against a bucket that never held
    it."""
    out = drive(shelf2_plan(undo=undo_plan(
        inputs=(UndoInput(name="x", provenance="minted_by_us",
                          ref="constructor"),),
        held={"minted_by_us": {"draft_id": DRAFT_ID}})))
    refused(out, Refusal.UNRESOLVED_REFERENCE)


def test_a_reference_resolving_to_an_empty_value_does_not_resolve():
    out = drive(shelf2_plan(undo=undo_plan(
        held={"minted_by_us": {"draft_id": ""}})))
    refused(out, Refusal.UNRESOLVED_REFERENCE)


# ------------------------------------ legs c and d: the act side, and its order

def test_the_label_attack_is_rejected_at_the_database():
    """§5.4, at the layer that calls itself the final authority.

    The plan declares `local_draft`, mints its own uuid, writes an undo plan
    that is provenance-clean and fully resolvable, and declares a reach of
    `read` while its steps open Gmail.  Every check the first revision of the
    spec specified is a check on the UNDO, and the undo is impeccable.  The
    act is simply not the act it said it was."""
    out = drive(shelf2_plan(act=act(reach="read")))
    refused(out, Refusal.REACH_DISAGREES)


def test_the_act_side_is_checked_before_the_undo_side():
    """"...whatever its undo plan says, and before its undo plan is even
    examined."  A row with BOTH a wrong reach and a broken undo must name the
    reach, or the ordering the spec requires is not the ordering shipped."""
    out = drive(shelf2_plan(act=act(reach="world"), undo=None))
    refused(out, Refusal.REACH_DISAGREES)


def test_an_act_type_outside_the_admitted_set_is_rejected():
    out = drive(shelf2_plan(act=act(act_type="gmail_draft"),
                            undo=undo_plan(act_type="gmail_draft")))
    refused(out, Refusal.ACT_TYPE_NOT_ADMITTED)


def test_a_row_with_no_act_declaration_is_rejected():
    refused(drive(shelf2_plan(act=None)), Refusal.ACT_TYPE_NOT_ADMITTED)


def test_an_inherited_property_name_is_not_an_admitted_act_type():
    """The same JSVM hazard the file documents for `consequence`, one level
    up.  The REASON matters as much as the rejection: `{ local_draft: 0 }[w]`
    hands back `Object`'s constructor rather than `undefined`, so a membership
    test written that way rejects for some downstream reason that has nothing
    to do with membership — and §11 counts refusals by cause."""
    for word in ("constructor", "toString", "__proto__"):
        out = drive(shelf2_plan(act=act(act_type=word),
                                undo=undo_plan(act_type=word)))
        assert out["outcome"] == "json", (
            f"act_type={word!r} was treated as admitted: {out}")
        assert detail(out) == Refusal.ACT_TYPE_NOT_ADMITTED.value, (
            f"act_type={word!r} was refused, but not for not being admitted: "
            f"{detail(out)!r} — the membership test is reading a prototype")


def test_the_browser_executor_may_not_run_an_admitted_act():
    """§8.7: "a step list handed to a browser session is bounded by what the
    session can do, not by what the plan said."  The admitted set names the
    executor, and this is the only mechanical containment available."""
    refused(drive(shelf2_plan(act=act(executor="browser_agent"))),
            Refusal.EXECUTOR_DISAGREES)


def test_an_unordered_shelf2_act_is_rejected():
    """Without a lineage position there is no LIFO law to apply later, so the
    act cannot be admitted now (§7.4, floor polarity)."""
    refused(drive(shelf2_plan(lineage_seq=0)), Refusal.UNORDERED_LINEAGE)


# ------------------------------------------------------- leg e: the durable tell

def test_a_row_with_no_announcement_obligation_is_rejected():
    """§8.3.  An act that ran and was not announced is an open obligation, not
    a completed job — moment 49, the failure silence is indistinguishable
    from."""
    refused(drive(shelf2_plan(announce=None)), Refusal.NO_ANNOUNCE_OBLIGATION)


def test_an_announcement_aimed_at_anyone_but_the_owner_is_rejected():
    """§10.1 condition 4, absolute: an act whose TELL would reach anyone but
    the owner is Shelf 3."""
    out = drive(shelf2_plan(announce=Obligation(
        channel="sms", owner_ref="somebody-else", recorded_at=NOW)))
    refused(out, Refusal.ANNOUNCE_LEAVES_THE_OWNER)


def test_an_announcement_with_no_channel_is_rejected():
    out = drive(shelf2_plan(), embedded_patch=lambda w: dict(
        w, announce=dict(w["announce"], channel="")))
    refused(out, Refusal.NO_ANNOUNCE_OBLIGATION)


# ------------------------------------------------- leg f: LIFO within a lineage

def compensating(act_seq=1, *, owner_words=None, gesture=True):
    """A compensating plan is Shelf 3 work carrying the owner's own authority
    (§8.6): the tap IS the approval.  So it is `consequential` and approved —
    the LIFO leg is keyed on `undo_of` being present, not on the consequence,
    or it would never fire on the row it exists for."""
    p = new_plan(
        owner_ref=OWNER, lineage_key="lin-1",
        goal="delete the draft we made about the boiler",
        consequence=Consequence.CONSEQUENTIAL, source_event_id="event-2",
        undo_of=UndoOf(plan_id=f"wf-000{act_seq}", version=1,
                       effect_key="eff", act_seq=act_seq),
        plan_id="wf-undo-1", now=NOW)
    if gesture:
        return approve_by_gesture(p, expected_version=p.version, gesture=Gesture(
            kind="tap", actor=OWNER, plan_id=p.plan_id,
            plan_version=p.version, scope_digest=p.scope_digest, made_at=NOW),
            now=NOW)
    return approve(p, expected_version=p.version,
                   owner_words=owner_words or "undo that", now=NOW)


def lineage_act(seq, status, *, plan_id=None):
    p = shelf2_plan(plan_id=plan_id or f"wf-000{seq}", lineage_seq=seq)
    return row_for(p, status=status, row_id=f"job000000000000{seq}",
                   force_queued=True)


def test_undoing_the_most_recent_act_is_allowed():
    out = drive(compensating(act_seq=2),
                lineage=[lineage_act(1, "done"), lineage_act(2, "done")])
    assert out["outcome"] == "next", out
    assert out["queried"] >= 1, "the ordering leg never looked at the lineage"


def test_undoing_an_act_a_later_act_has_already_overwritten_is_rejected():
    """§7.4's worked example, at the database.

    Act A drafts the boiler email (seq 1).  Act B revises it in place (seq 2).
    He taps undo on A and the row is gone.  He then taps undo on B, still on
    screen, and the row is RESTORED.  A draft he was told forty seconds ago
    was gone is back, and both receipts are honest.  Every check in §5 passes
    at every step; the COMPOSITION is what fails."""
    out = drive(compensating(act_seq=1),
                lineage=[lineage_act(1, "done"), lineage_act(2, "done")])
    refused(out, Refusal.SUPERSEDED_BY_LATER_ACT)


def test_a_later_act_that_never_ran_does_not_block_the_undo():
    """The law is about acts that have RUN.  A queued successor has changed
    nothing yet, and refusing on it would make undo unusable."""
    out = drive(compensating(act_seq=1),
                lineage=[lineage_act(1, "done"), lineage_act(2, "queued")])
    assert out["outcome"] == "next", out


def test_a_later_act_that_failed_still_blocks_the_undo():
    """It was claimed and it ran.  What it left behind is exactly what nobody
    can be sure of, and floor polarity says an undo whose outcome we cannot
    determine is an undo that failed (§10.5)."""
    out = drive(compensating(act_seq=1),
                lineage=[lineage_act(1, "done"), lineage_act(2, "failed")])
    refused(out, Refusal.SUPERSEDED_BY_LATER_ACT)


def test_an_unreachable_lineage_refuses_the_undo():
    """"Polarity is the floor again: if we cannot determine the ordering, we
    refuse the undo and ask."  A database that will not answer is not a
    database that said no."""
    out = drive(compensating(act_seq=1), lineage=[lineage_act(1, "done")],
                lineage_throws=True)
    refused(out, Refusal.LINEAGE_UNREADABLE)


def test_a_lineage_query_that_answers_with_nonsense_refuses_the_undo():
    """Not every wrong answer is an exception.  A PocketBase build that hands
    back something other than a list would send `for (const row of rows)`
    straight into a TypeError, and a hook that THROWS is not a hook that
    refused — the request's fate is then whatever the router does with a
    panicking handler.  So the shape is checked, and an answer we cannot read
    is the same as no answer."""
    out = drive(compensating(act_seq=1), lineage=[lineage_act(1, "done")],
                lineage_nonsense=True)
    refused(out, Refusal.LINEAGE_UNREADABLE)


def test_an_undo_of_an_act_that_is_not_in_the_lineage_is_refused():
    """An undo that names nothing findable cannot be ordered against anything,
    so it is not the head of its lineage; it is not anywhere."""
    out = drive(compensating(act_seq=1),
                lineage=[lineage_act(2, "queued", plan_id="wf-9999")])
    refused(out, Refusal.UNORDERED_LINEAGE)


def test_an_undo_whose_named_act_sits_at_a_different_position_is_refused():
    """The compensating plan asserts the act's position; the row is what it
    actually was.  Two stored values disagreeing is a refusal, and it is the
    one shape a tap replayed against a changed row would take."""
    out = drive(compensating(act_seq=1),
                lineage=[lineage_act(2, "done", plan_id="wf-0001")])
    refused(out, Refusal.UNORDERED_LINEAGE)


def test_a_lineage_row_whose_plan_is_unreadable_refuses_the_undo():
    """The act being undone is right there and readable; ANOTHER row in the
    lineage is not.  Skipping the unreadable one would answer "nothing later
    has run" from a lineage we only partly read — and the row we could not
    read is exactly where a later act would be hiding.  A lineage we cannot
    read whole is a lineage we cannot order against."""
    broken = lineage_act(2, "done")
    broken["params"] = "{not json at all"
    out = drive(compensating(act_seq=1),
                lineage=[lineage_act(1, "done"), broken])
    refused(out, Refusal.LINEAGE_UNREADABLE)


# ---------------------------------------------------- §7.3, the tap has no words

def test_a_tap_is_accepted_as_authority_without_inventing_words():
    """§7.3's seam at layer 2 of 3.  The guard refuses an empty
    `approval.owner_words`, which is correct for speech and is exactly the
    check that tempts somebody to write `"owner_words": "tapped undo"` in
    Swift.  A gesture is admitted as a gesture instead — bound to the same
    plan id, version and scope digest that words would have been bound to."""
    out = drive(compensating(act_seq=1), lineage=[lineage_act(1, "done")])
    assert out["outcome"] == "next", out
    body = json.loads(json.dumps(out))  # sanity: the harness round-trips
    assert body is not None


def test_an_approval_with_neither_words_nor_a_gesture_is_still_refused():
    """The protection the seam must not spend.  An empty `owner_words` with no
    gesture behind it is the original hole and stays closed."""
    p = compensating(act_seq=1)
    out = drive(p, lineage=[lineage_act(1, "done")],
                embedded_patch=lambda w: dict(w, approval=dict(
                    w["approval"], owner_words="", gesture=None)))
    assert out["outcome"] == "json", out
    assert detail(out) == "approval is not bound to this exact plan version", out


@pytest.mark.parametrize("break_it,label", [
    (lambda g: dict(g, plan_version=99), "bound to another version"),
    (lambda g: dict(g, scope_digest="something-else"), "bound to another scope"),
    (lambda g: dict(g, plan_id="wf-9999"), "bound to another plan"),
    (lambda g: dict(g, actor=""), "unauthenticated"),
    (lambda g: dict(g, kind="shrug"), "an unrecognised kind"),
    (lambda g: "a string", "not an object"),
])
def test_a_gesture_that_is_not_bound_to_this_exact_plan_is_refused(break_it, label):
    """Every way the widening could become a hole.  A gesture buys the same
    thing words buy and nothing more: it must be bound to THIS plan, THIS
    version and THIS scope, and it must say who made it."""
    out = drive(compensating(act_seq=1), lineage=[lineage_act(1, "done")],
                embedded_patch=lambda w: dict(w, approval=dict(
                    w["approval"], owner_words="",
                    gesture=break_it(w["approval"]["gesture"]))))
    assert out["outcome"] == "json", f"a gesture {label} was accepted: {out}"
    assert detail(out) == "approval is not bound to this exact plan version", out


def test_an_executor_cannot_mint_its_own_gesture():
    """§7.2.1: "an executor that could mint its own undo could mint its own
    anything."  The existing refusal must still cover the new field."""
    out = drive(compensating(act_seq=1), lineage=[lineage_act(1, "done")],
                headers={"X-Anticipy-Agent-ID": "agent-7"})
    assert out["outcome"] == "json", out
    assert detail(out) == "an executor cannot rewrite or approve its plan", out


# ------------------------------------------- the two layers must not drift apart

def test_python_and_the_guard_share_one_refusal_vocabulary():
    """A source check, deliberately, and for the reason the file next door
    gives: the approval fail-open survived because Python and JavaScript
    disagreed and nothing anywhere compared them.  §11 counts refusals by
    cause; two vocabularies means two counts of the same thing."""
    raw = (HOOKS / "workflow_guard.pb.js").read_text()
    for cause in Refusal:
        assert f'"{cause.value}"' in raw, (
            f"{cause.value} is a refusal Python can produce and the database "
            "cannot name; §11's reason distribution would be missing it")


def test_the_admitted_set_agrees_across_the_two_layers():
    """§10.3's set is a constant in two files while it has one member, which
    §6.4 licenses and which only stays safe while a test compares them.  The
    repo-data form is required before the SECOND admission."""
    from brain.workflow import ADMITTED_ACT_TYPES
    raw = (HOOKS / "workflow_guard.pb.js").read_text()
    js = "\n".join(line.split("//", 1)[0] for line in raw.splitlines())
    for name, entry in ADMITTED_ACT_TYPES.items():
        assert f'"{name}"' in js, f"{name} is admitted in Python only"
        assert f'"{entry.reach}"' in js, f"{name}'s reach is not in the guard"
        assert f'"{entry.executor}"' in js, f"{name}'s executor is not in the guard"
    for word in ("gmail_draft", "booking", "calendar_event"):
        assert f'"{word}"' not in js, f"the guard admits {word}"


def test_the_provenance_vocabulary_agrees_across_the_two_layers():
    from brain.workflow import PROVENANCE_TAGS
    raw = (HOOKS / "workflow_guard.pb.js").read_text()
    js = "\n".join(line.split("//", 1)[0] for line in raw.splitlines())
    for tag in PROVENANCE_TAGS:
        assert f'"{tag}"' in js, f"{tag} is a provenance Python knows and the " \
                                 "database does not"
