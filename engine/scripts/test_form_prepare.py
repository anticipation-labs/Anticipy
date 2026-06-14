"""Browser WRITE arm (prepare-then-handoff) test.

Proves the FormPrepareAgent + BrowserHand prepare_form mode against a scripted
link that emulates the REAL extension observe/act protocol over the PUBLIC
httpbin pizza order form (https://httpbin.org/forms/post): text/tel/email
fields, a radio group, checkboxes, a textarea, and a 'Submit order' button.

Hard claims pinned here:
  - every requested field is filled (typed text / clicked toggle),
  - the 'Submit order' control is NEVER acted on (no submit, ever),
  - the agent reads the filled values BACK off the re-observed page as proof,
  - BrowserHand.prepare_form hands the staged state to the owner (needs_human),
    carrying the filled-field proof + a pointer to the submit button it left.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_form_prepare.py
NO network: the link is a local script. NO submit, NO login, NO money.
"""
import asyncio

from anticipy_engine.agent.form_prepare import (
    FormPrepareAgent, SUBMIT_GUARD, _is_submit, _is_text_field, _is_toggle,
)
from anticipy_engine.core.envelopes import Job, JobStatus
from anticipy_engine.hands.browser_hand import BrowserHand


# The httpbin /forms/post element shape, as the extension's set-of-marks would
# surface it (idx, role, name, type, state). Text inputs surface placeholder/
# value as `name`; radios/checkboxes surface their option label.
FORM_URL = "https://httpbin.org/forms/post"


def _base_elements():
    return [
        {"idx": 0, "role": "input", "name": "Customer name", "type": "text", "state": ""},
        {"idx": 1, "role": "input", "name": "Telephone", "type": "tel", "state": ""},
        {"idx": 2, "role": "input", "name": "E-mail address", "type": "email", "state": ""},
        {"idx": 3, "role": "radio", "name": "Small", "type": "radio", "state": ""},
        {"idx": 4, "role": "radio", "name": "Medium", "type": "radio", "state": ""},
        {"idx": 5, "role": "radio", "name": "Large", "type": "radio", "state": ""},
        {"idx": 6, "role": "checkbox", "name": "Bacon", "type": "checkbox", "state": ""},
        {"idx": 7, "role": "checkbox", "name": "Extra Cheese", "type": "checkbox", "state": ""},
        {"idx": 8, "role": "checkbox", "name": "Onion", "type": "checkbox", "state": ""},
        {"idx": 9, "role": "checkbox", "name": "Mushroom", "type": "checkbox", "state": ""},
        {"idx": 10, "role": "input", "name": "Preferred delivery time", "type": "text", "state": ""},
        {"idx": 11, "role": "textarea", "name": "Delivery instructions", "type": "", "state": ""},
        {"idx": 12, "role": "button", "name": "Submit order", "type": "submit", "state": ""},
    ]


class FormScriptLink:
    """Emulates the extension WS link for the pizza form. `type` writes the
    typed text into the element's `name` (mirrors how the real extension surfaces
    an input's .value); `click` on a toggle flips its `checked` state. It REFUSES
    to act on the submit control — and records every act so the test can assert
    the submit button was never touched."""

    def __init__(self, connected=True):
        self.connected = connected
        self.elements = _base_elements()
        self.acts = []
        self.submit_acts = []

    def _by_idx(self, idx):
        return next((e for e in self.elements if e.get("idx") == idx), None)

    async def send_browse(self, job_id, intent, args, timeout):
        if intent == "observe":
            return {
                "type": "result", "job_id": job_id, "status": "success",
                "proof": {"screenshot": "data:image/png;base64,shot", "url": FORM_URL},
                "output": {"url": FORM_URL, "title": "Pizza form",
                           "text": "Customer name Telephone Submit order",
                           "elements": [dict(e) for e in self.elements]},
            }
        if intent == "act":
            self.acts.append(args)
            el = self._by_idx(args.get("index"))
            if el and _is_submit(el):
                # the script itself records a forbidden act; the agent must never get here
                self.submit_acts.append(args)
                return {"type": "result", "job_id": job_id, "status": "success",
                        "output": {"ok": True}}
            if args.get("action") == "type" and el is not None:
                el["name"] = args.get("text") or ""
            if args.get("action") == "click" and el is not None and _is_toggle(el):
                el["state"] = "" if "checked" in (el.get("state") or "") else "checked"
            return {"type": "result", "job_id": job_id, "status": "success",
                    "output": {"ok": True}}
        return {"type": "result", "job_id": job_id, "status": "failed", "output": {}}


WANT = {
    "Customer name": "Omar Ebrahim",
    "Telephone": "5551234567",
    "E-mail address": "omar@example.com",
    "Pizza Size": "Large",
    "Pizza Toppings": "Mushroom",
    "Preferred delivery time": "18:30",
    "Delivery instructions": "Leave at the front desk [Anticipy test]",
}


def _assert_helpers():
    # the submit guard is the hard stop, and it is precise: real submit-y labels
    # match; ordinary field labels do not.
    for label in ("Submit order", "Place your order", "Pay now", "Continue", "Send"):
        assert SUBMIT_GUARD.search(label), label
    for label in ("Customer name", "E-mail address", "Delivery instructions",
                  "Preferred delivery time", "Mushroom", "Large"):
        assert not SUBMIT_GUARD.search(label), label
    # field classification
    els = {e["idx"]: e for e in _base_elements()}
    assert _is_text_field(els[0]) and _is_text_field(els[11])  # text + textarea
    assert not _is_text_field(els[3]) and not _is_text_field(els[6])  # radio/checkbox
    assert _is_toggle(els[3]) and _is_toggle(els[6])
    assert _is_submit(els[12]) and not _is_submit(els[0])
    print("PASS helpers: submit guard precise; text/toggle/submit classified")


async def test_agent_prepares_and_stops():
    link = FormScriptLink()
    agent = FormPrepareAgent(link)
    result = await agent.run(FORM_URL, WANT)

    # NEVER submitted — the cardinal claim of this arm
    assert result["submitted"] is False, result
    assert link.submit_acts == [], ("the agent acted on the submit control!", link.submit_acts)
    # the submit button index (12) appears in NO act of any kind
    assert all(a.get("index") != 12 for a in link.acts), link.acts

    # every requested field was prepared and read back as filled
    assert result["prepared"] is True, result
    assert result["confirmed_fields"] is True, result
    filled_labels = {f["label"] for f in result["filled_fields"]}
    assert filled_labels == set(WANT), (filled_labels, set(WANT))
    assert not result["pending_fields"], result["pending_fields"]

    # read-back proof: text fields show the typed value; toggles are checked
    by_label = {f["label"]: f for f in result["filled_fields"]}
    assert "omar" in by_label["Customer name"]["observed"].lower()
    assert "18 30" in by_label["Preferred delivery time"]["observed"] or \
           "18:30" in by_label["Preferred delivery time"]["observed"]
    assert by_label["Pizza Size"]["kind"] == "toggle"
    assert by_label["Pizza Toppings"]["kind"] == "toggle"

    # the right toggle options were chosen (Large radio idx=5, Mushroom checkbox idx=9)
    assert by_label["Pizza Size"]["index"] == 5, by_label["Pizza Size"]
    assert by_label["Pizza Toppings"]["index"] == 9, by_label["Pizza Toppings"]
    # the OTHER radio/checkbox options were left untouched
    assert link._by_idx(3)["state"] == "" and link._by_idx(4)["state"] == ""  # Small/Medium off
    assert link._by_idx(6)["state"] == ""  # Bacon off

    # the submit control is reported for the owner to click — not clicked here
    assert result["submit_control"]["index"] == 12, result["submit_control"]
    assert "Submit order" in result["submit_control"]["name"]
    assert "did NOT submit" in result["answer"], result["answer"]
    print("PASS agent: 7/7 fields prepared + read back; submit untouched; handoff staged")


async def test_already_checked_box_is_left():
    link = FormScriptLink()
    link._by_idx(9)["state"] = "checked"  # Mushroom already checked
    agent = FormPrepareAgent(link)
    result = await agent.run(FORM_URL, {"Pizza Toppings": "Mushroom"})
    # no click was issued on idx 9 (it was already in the wanted state)
    assert all(not (a.get("action") == "click" and a.get("index") == 9) for a in link.acts), link.acts
    assert link._by_idx(9)["state"] == "checked"
    assert result["confirmed_fields"] is True, result
    print("PASS idempotent: an already-checked box is left as-is, not toggled off")


async def test_unmatched_field_is_reported_not_faked():
    link = FormScriptLink()
    agent = FormPrepareAgent(link)
    result = await agent.run(FORM_URL, {
        "Customer name": "Omar",
        "Loyalty card number": "NO-SUCH-FIELD",  # not on the form
    })
    pending = {p["label"] for p in result["pending_fields"]}
    assert "Loyalty card number" in pending, result["pending_fields"]
    assert any(f["label"] == "Customer name" for f in result["filled_fields"])
    # an unmatched field means we are NOT fully confirmed (honest, not faked)
    assert result["confirmed_fields"] is False, result
    print("PASS honest: a field with no matching input is reported pending, never faked")


async def test_submit_word_in_field_label_is_still_filled():
    """A text field whose LABEL contains a submit-y word ('Send message to')
    must still be filled — the submit guard only forbids clicking BUTTONS, never
    typing into inputs. And a bare <button> named 'Place your order' (no
    type=submit) must still be guarded from any click."""
    link = FormScriptLink()
    link.elements = [
        {"idx": 0, "role": "input", "name": "Send message to", "type": "text", "state": ""},
        {"idx": 1, "role": "textarea", "name": "Order notes", "type": "", "state": ""},
        {"idx": 2, "role": "button", "name": "Place your order", "type": "", "state": ""},
    ]
    assert _is_submit(link.elements[2]) and not _is_submit(link.elements[0])
    agent = FormPrepareAgent(link)
    result = await agent.run(FORM_URL, {
        "Send message to": "Coordinator",
        "Order notes": "Two boxes",
    })
    filled = {f["label"] for f in result["filled_fields"]}
    assert filled == {"Send message to", "Order notes"}, result
    # the bare submit-named button (idx 2) was never clicked
    assert all(a.get("index") != 2 for a in link.acts), link.acts
    assert result["submit_control"]["index"] == 2, result["submit_control"]
    print("PASS edge: submit-word field label is filled; bare submit-named button guarded")


async def test_browser_hand_prepare_form_hands_off():
    link = FormScriptLink()
    hand = BrowserHand(link)
    assert "prepare_form" in hand.handles()

    r = await hand.handle(Job(intent="prepare_form", args={"url": FORM_URL, "fields": WANT}))
    # prepared but NOT submitted -> needs_human (owner confirms + submits)
    assert r.status == JobStatus.needs_human, r
    assert r.proof and r.proof["form_prepare"] is True and r.proof["submitted"] is False, r.proof
    assert r.proof["screenshot"], r.proof
    assert len(r.proof["filled_fields"]) == len(WANT), r.proof["filled_fields"]
    assert r.proof["submit_control"]["index"] == 12, r.proof["submit_control"]
    assert link.submit_acts == [], "hand path must never submit either"

    # guard rails: no url / no fields -> honest failure, the link untouched
    bad = FormScriptLink()
    r = await BrowserHand(bad).handle(Job(intent="prepare_form", args={"fields": WANT}))
    assert r.status == JobStatus.failed and "url" in r.error, r
    assert bad.acts == [], bad.acts
    r = await BrowserHand(FormScriptLink()).handle(
        Job(intent="prepare_form", args={"url": FORM_URL}))
    assert r.status == JobStatus.failed and "fields" in r.error, r

    # not connected -> handed back, never a fake prepare
    r = await BrowserHand(FormScriptLink(connected=False)).handle(
        Job(intent="prepare_form", args={"url": FORM_URL, "fields": WANT}))
    assert r.status == JobStatus.needs_human and "isn't connected" in r.output["reason"], r
    print("PASS hand: prepare_form hands the staged form to the owner; no submit; guard rails honest")


async def main():
    _assert_helpers()
    await test_agent_prepares_and_stops()
    await test_already_checked_box_is_left()
    await test_unmatched_field_is_reported_not_faked()
    await test_submit_word_in_field_label_is_still_filled()
    await test_browser_hand_prepare_form_hands_off()
    print("\nALL FORM-PREPARE TESTS PASSED — browser write arm prepares to the submit "
          "screen and hands off; NO submit, NO login, NO money")


if __name__ == "__main__":
    asyncio.run(main())
