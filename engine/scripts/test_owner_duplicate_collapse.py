"""F-012: ONE real-world obligation = ONE card.

Deterministic unit test (no model) of the semantic consolidation that collapses moat-expanded
duplicate obligations — a relayed request ("Mom: call Amazon about the plant") + the speaker's
confirmation ("Yeah, I'll handle it" -> "handle the Amazon plant order") + reworded variants — into a
single line, WITHOUT merging genuinely different obligations. This is the engine-side fix for the
duplicate spam seen in the real app UI; the live end-to-end proof is the UI receipt (RECEIPTS.md).
"""
import os

os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")
os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")
os.environ.setdefault("ANTICIPY_NATIVE_BRIDGE_FALLBACK", "0")

from anticipy_engine.core.control_core import (  # noqa: E402
    ControlCore, _obligation_sig, _same_obligation,
)
from anticipy_engine.owner_mode import OwnerObservedLine  # noqa: E402


def L(text, force_ask=False, moat_task=False):
    return OwnerObservedLine(line_no=0, text=text, force_ask=force_ask, moat_task=moat_task)


def texts(lines):
    return [l.text for l in lines]


def main():
    # 1) the exact live-UI duplicate trio collapses to ONE, keeping the earliest/original wording.
    amazon = [
        L("call Amazon about the plant I ordered"),
        L("handle the Amazon plant order"),
        L("call Amazon about that plant"),
    ]
    out = ControlCore._consolidate_obligations(amazon)
    assert len(out) == 1, texts(out)
    assert out[0].text == "call Amazon about the plant I ordered", texts(out)

    # 2) boss request + speaker confirmation about the same deck -> ONE.
    sam = [L("get Sam the deck by Friday"), L("Can you get Sam the deck by Friday?")]
    assert len(ControlCore._consolidate_obligations(sam)) == 1, "Sam deck must collapse"

    # 3) genuinely different obligations are NEVER merged (incl. same person, different object).
    distinct = [
        L("call Amazon about the plant I ordered"),
        L("get Sam the deck by Friday"),
        L("pickup moved to 3 today"),
        L("make sure the retainer note is in the CRM before the call"),
        L("email Sarah the budget"),
        L("email Sarah the deck"),
    ]
    out = ControlCore._consolidate_obligations(distinct)
    assert len(out) == 6, ("distinct obligations must not merge", texts(out))

    # 4) the full messy transcript's moat-expanded form collapses to exactly the real obligations.
    expanded = [
        L("call Amazon about the plant I ordered"),
        L("handle the Amazon plant order"),
        L("get Sam the deck by Friday"),
        L("get him the deck by Friday"),
        L("pickup moved to 3 today"),
        L("make sure the retainer note is in the CRM before the call"),
    ]
    out = ControlCore._consolidate_obligations(expanded)
    assert len(out) == 4, ("one obligation = one card", texts(out))

    # 5) SAFETY: if any clustered duplicate is vent-adjacent, the kept line stays force_ask
    #    (the vent guard can only get stricter, never lost).
    vent = [L("call Amazon about the plant order"), L("handle the Amazon plant order", force_ask=True)]
    out = ControlCore._consolidate_obligations(vent)
    assert len(out) == 1 and out[0].force_ask is True, "force_ask must propagate on merge"

    # 6) thin / empty-signature lines are never auto-merged.
    thin = [L("ok"), L("yeah"), L("sure")]
    assert len(ControlCore._consolidate_obligations(thin)) == 3, "empty-sig lines kept as-is"

    # 7) signature helper sanity.
    assert _same_obligation(_obligation_sig("call Amazon about the plant I ordered"),
                            _obligation_sig("handle the Amazon plant order"))
    assert not _same_obligation(_obligation_sig("email Sarah the budget"),
                                _obligation_sig("email Sarah the deck"))
    assert not _same_obligation(_obligation_sig("ok"), _obligation_sig("yeah"))

    # 8) REGRESSION (2026-06-17): the moat rewords a confirmation into a SYNONYM of the original
    #    where the obligations differ only by an interchangeable comm verb / filler problem-noun:
    #    "call Amazon about the monitor" {amazon,call,monitor} vs "handle the Amazon monitor issue"
    #    {amazon,issue,monitor}. Neither contains the other (call vs issue), so the old containment-
    #    only merge missed them -> 2 cards = duplicate spam (the lone critical in the 14-type 10k cert).
    #    The identity-core merge ({amazon,monitor} == {amazon,monitor}) collapses them to ONE.
    synonym = [L("call Amazon about the monitor"), L("handle the Amazon monitor issue")]
    assert len(ControlCore._consolidate_obligations(synonym)) == 1, "synonym-reworded dup must collapse"
    assert _same_obligation(_obligation_sig("call Amazon about the monitor"),
                            _obligation_sig("handle the Amazon monitor issue"))
    # but a DIFFERENT object (verb-only-different is fine to merge; object-different is NOT) stays split.
    assert not _same_obligation(_obligation_sig("call Amazon about the monitor"),
                                _obligation_sig("call Amazon about the desk"))
    diff_obj = [L("call Amazon about the monitor"), L("handle the Amazon desk issue")]
    assert len(ControlCore._consolidate_obligations(diff_obj)) == 2, "different objects must not merge"

    print("PASS owner_duplicate_collapse: one real obligation = one card; distinct stay separate; "
          "synonym-reworded dups collapse; vent guard propagates on merge")


if __name__ == "__main__":
    main()
