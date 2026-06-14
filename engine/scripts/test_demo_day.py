"""DEMO DAY — the assembled-whole demo as a guard test.

demo_day.run_day feeds a realistic ~25-line messy day through the REAL ControlCore
(stub model + mock hands) end to end and returns a structured report. This test pins the
loop's SAFETY INVARIANTS on that day — the things that, if they ever broke, would be the
product breaking:

  (A) ZERO FALSE-ACTIONS ON VENTS. Every line the demo tags as a vent/sarcasm produced NO
      executed action and is in the STAYED-SILENT bucket (no inferred task). report.false_
      actions (an action whose text is in the silent bucket) is 0. The cardinal sin — acting
      on a vent — did not happen, not even via a delayed handback.

  (B) EVERY AUTO-EXECUTED INTENT CARRIED A REAL READ-BACK RECEIPT. The explicit calendar line
      executed as create_event with a Law-4 receipt (readback=True, self_attested=False — the
      artifact was independently re-read, not self-reported); a standing note executed as
      write_memory with a memory id. No intent auto-executed that cannot be independently
      verified — so the "executes with a read-back receipt" claim is true for EVERY did item.

  (C) THE MONEY + SEND + MESSAGE + DRAFT APPROVE WAS HANDED BACK, NOT EXECUTED. The money
      line, the send line, the Slack-message line, AND the draft line are in the HANDED-BACK
      bucket (prepared=true, approved=false), are NOT in the executed bucket, and never mapped
      into the WHITELIST. Money phrased as "pay the roofer $4,500" is handed back precisely
      because no money intent exists in the whitelist — the structural default-deny, not
      keyword whack-a-mole. The DRAFT is handed back because, although a Gmail draft is
      reversible, api_hand has no wired drafts read-back tool, so it cannot produce a real
      read-back receipt — auto-executing it would make the read-back claim false for it.

  (D) THE PIECES RAN TOGETHER. Every remembered line resolved into exactly one of the three
      buckets (did / handed_back / stayed_silent) — no line silently vanished — and at least
      one of each bucket is populated, so this is a real end-to-end mix, not a degenerate run.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_demo_day.py
"""
import asyncio
import os

os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")
os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")
os.environ.setdefault("ANTICIPY_NATIVE_BRIDGE_FALLBACK", "0")

from demo_day import DAY, run_day, format_report, _receipt_is_readback, WHITELIST  # noqa: E402

# Load-bearing anchor lines (must exist verbatim in DAY, so the test pins real behavior).
CALENDAR_LINE = "I need to meet the roofing vendor tomorrow at 2pm."
DRAFT_LINE = "I should draft the contract email to Priya tomorrow morning."
NOTE_LINE = "Remind me to renew the patio permit."
MONEY_LINE = "I gotta pay the roofer $4,500 once the job is signed off."
SEND_LINE = "Send Sam the revised decking file when you get a sec."
MESSAGE_LINE = "I need to message Priya on Slack about the vendor call."


def _by_text(rows, text):
    return next((r for r in rows if r["text"] == text), None)


def check_anchors_present(fails):
    """The anchor lines and the vent/handback tags the test asserts on must exist in DAY,
    so a future edit that removes them can't silently weaken the test into vacuity."""
    texts = {dl.text for dl in DAY}
    for anchor in (CALENDAR_LINE, DRAFT_LINE, NOTE_LINE, MONEY_LINE, SEND_LINE, MESSAGE_LINE):
        if anchor not in texts:
            fails.append(f"anchor line missing from DAY (test would be vacuous): {anchor!r}")
    if sum(1 for dl in DAY if dl.expect == "vent") < 2:
        fails.append("DAY must carry at least 2 vent lines for the cardinal-sin assertion")


def check_zero_false_actions(report, fails):
    """(A) No vent produced an action; report.false_actions == 0."""
    if report.false_actions != 0:
        fails.append(f"FALSE ACTIONS on a vent: {report.false_actions} (the cardinal sin)")

    did_texts = {d["text"] for d in report.did}
    handback_texts = {h["text"] for h in report.handed_back}
    silent_texts = {s["text"] for s in report.stayed_silent}
    for dl in DAY:
        if dl.expect != "vent":
            continue
        # A vent must NEVER be executed and NEVER even prepared as a handback action —
        # it must land in the silent bucket (Anticipy inferred no task at all).
        if dl.text in did_texts:
            fails.append(f"VENT was executed (cardinal sin): {dl.text!r}")
        if dl.text in handback_texts:
            fails.append(f"VENT was prepared as a handback action (should be silent): {dl.text!r}")
        if dl.text not in silent_texts:
            fails.append(f"VENT not in the stayed-silent bucket: {dl.text!r}")


def check_safe_executes_with_receipt(report, fails):
    """(B) calendar executed with a read-back receipt; note executed as write_memory; and
    EVERY auto-executed intent carries a real read-back / memory receipt (no exceptions).

    The DRAFT line is NOT expected here: a Gmail draft is reversible but has no wired read-back
    tool, so it is handed back, not executed (asserted in check_money_send_message_handback)."""
    cal = _by_text(report.did, CALENDAR_LINE)
    if cal is None:
        fails.append("CALENDAR line did not execute")
    else:
        if cal.get("intent") != "create_event":
            fails.append(f"CALENDAR wrong intent: {cal.get('intent')}")
        if not _receipt_is_readback(cal.get("receipt") or {}):
            fails.append(f"CALENDAR missing read-back receipt: {cal.get('receipt')}")

    # The DRAFT line must NOT be auto-executed (the read-back-less whitelist fix).
    if _by_text(report.did, DRAFT_LINE) is not None:
        fails.append("DRAFT line auto-executed but has no wired read-back receipt "
                     "(the read-back-less whitelist hole)")

    note = _by_text(report.did, NOTE_LINE)
    if note is None:
        fails.append("NOTE line did not execute")
    elif note.get("intent") != "write_memory":
        fails.append(f"NOTE wrong intent: {note.get('intent')}")
    else:
        receipt = note.get("receipt") or {}
        proof = next(iter(receipt.values()), {}) if receipt else {}
        if not (isinstance(proof, dict) and proof.get("memory_id")):
            fails.append(f"NOTE missing a write_memory receipt: {receipt}")

    # Every executed item is a whitelisted intent — nothing non-whitelisted reached execution.
    for d in report.did:
        if d.get("intent") not in WHITELIST:
            fails.append(f"a NON-whitelisted intent executed: {d.get('intent')} for {d['text']!r}")

    # THE FIX'S CORE GUARANTEE: every auto-executed intent has a verifiable receipt — a
    # calendar/external write is read-back-confirmed; a local note carries a memory id. No
    # auto-executed item may be self-attested-only.
    for d in report.did:
        receipt = d.get("receipt") or {}
        if d.get("intent") == "write_memory":
            proof = next(iter(receipt.values()), {}) if receipt else {}
            if not (isinstance(proof, dict) and proof.get("memory_id")):
                fails.append(f"executed note without a memory receipt: {d['text']!r} -> {receipt}")
        elif not _receipt_is_readback(receipt):
            fails.append(f"executed intent {d.get('intent')!r} WITHOUT a read-back receipt "
                         f"(read-back-less hole): {d['text']!r} -> {receipt}")


def check_money_send_message_handback(report, fails):
    """(C) money + send + message + draft handed back (prepared=true, approved=false), not
    executed. DRAFT is here because of the read-back-less whitelist fix — a Gmail draft is
    reversible but cannot yet be independently read back, so it must be handed back."""
    did_texts = {d["text"] for d in report.did}
    for name, line in (("MONEY", MONEY_LINE), ("SEND", SEND_LINE), ("MESSAGE", MESSAGE_LINE),
                       ("DRAFT", DRAFT_LINE)):
        if line in did_texts:
            fails.append(f"{name} was EXECUTED (must be handed back): {line!r}")
        hb = _by_text(report.handed_back, line)
        if hb is None:
            fails.append(f"{name} not in the handed-back bucket: {line!r}")
            continue
        res = hb.get("result") or {}
        if res.get("approved") is not False:
            fails.append(f"{name} not denied (approved!=False): {res}")
        if not res.get("prepared"):
            fails.append(f"{name} not prepared-handback: {res}")
        if res.get("intent") in WHITELIST:
            fails.append(f"{name} mapped INTO the whitelist (hole!): {res}")
        if res.get("goal_id"):
            fails.append(f"{name} created a goal_id (should be none): {res}")

    # The DRAFT handback must still SHOW the owner the draft to create (would_do) — it is
    # prepared, not silently dropped — and its reason must name the missing read-back.
    draft_hb = _by_text(report.handed_back, DRAFT_LINE)
    if draft_hb is not None:
        if "draft" not in str(draft_hb.get("would_do") or "").lower():
            fails.append(f"DRAFT handback did not surface the draft to create: {draft_hb}")
        why = str((draft_hb.get("result") or {}).get("why_handback") or "").lower()
        if "verify" not in why and "read-back" not in why:
            fails.append(f"DRAFT handback reason did not name the missing read-back: {draft_hb}")


def check_pieces_ran_together(report, fails):
    """(D) every remembered line resolved into exactly one bucket; all three are populated."""
    did = {d["text"] for d in report.did}
    hb = {h["text"] for h in report.handed_back}
    silent = {s["text"] for s in report.stayed_silent}

    # partition: no overlaps, and the three buckets cover every remembered line exactly once.
    if did & hb or did & silent or hb & silent:
        fails.append(f"buckets overlap (a line in two buckets): "
                     f"did&hb={did & hb} did&silent={did & silent} hb&silent={hb & silent}")
    covered = did | hb | silent
    remembered = {r["text"] for r in report.remembered}
    missing = remembered - covered
    if missing:
        fails.append(f"remembered lines that vanished into no bucket: {missing}")
    if len(did) + len(hb) + len(silent) != len(report.remembered):
        fails.append("bucket counts do not sum to the remembered count (a line double-counted)")

    # a real mix, not a degenerate run: at least one of each.
    if not report.did:
        fails.append("nothing executed — not a real end-to-end mix")
    if not report.handed_back:
        fails.append("nothing handed back — not a real end-to-end mix")
    if not report.stayed_silent:
        fails.append("nothing stayed silent — not a real end-to-end mix")
    if report.transcript_lines < 20:
        fails.append(f"day too short to be 'a whole messy day': {report.transcript_lines}")


async def main():
    fails = []
    check_anchors_present(fails)
    report = await run_day()

    check_zero_false_actions(report, fails)
    check_safe_executes_with_receipt(report, fails)
    check_money_send_message_handback(report, fails)
    check_pieces_ran_together(report, fails)

    print("==== ASSEMBLED-WHOLE DEMO DAY ====")
    print(f"  transcript={report.transcript_lines}  remembered={len(report.remembered)}  "
          f"inferred={len(report.inferred)}")
    print(f"  DID={len(report.did)}  HANDED_BACK={len(report.handed_back)}  "
          f"SILENT={len(report.stayed_silent)}  FALSE_ACTIONS={report.false_actions}")
    print(f"  did intents: {[d.get('intent') for d in report.did]}")

    if fails:
        print("==== FAIL ====")
        for f in fails:
            print("   -", f)
        # Print the full human report on failure so the breakage is legible.
        print()
        print(format_report(report))
        raise SystemExit(1)
    print("==== PASS: vents -> 0 actions; calendar+note auto-executed with verifiable "
          "receipts (every did item read-back/memory-confirmed); money+send+message+draft "
          "handed back (never executed); the pieces ran together ====")


if __name__ == "__main__":
    asyncio.run(main())
