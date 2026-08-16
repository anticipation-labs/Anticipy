"""Hunt round 1 (2026-08-15), pinned: five P0s the finders reported and I
re-verified by hand against the code before fixing.

1. authority_text shadowed approved_scope, so resumed answers never reached
   the browser hands' authority.
2. "Cancel reservation" prefix-matched the reversible list and dispatched
   with every safety gate skipped.
3. "it's all good" (a chat with a group word) mass-released every job she
   had ever offered in a numbered question.
4. A just-released queued job was invisible to SMS cancel, and the decline
   lane replied "Okay — scrapping it" having scrapped nothing.
5. Darwin's numeric-aware key sort diverges from Python's at
   owner_answer_v10, silently breaking every digest on long-lived plans.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent
BACKGROUND = (ROOT / "extension/background.js").read_text()
CONV = (ROOT / "brain/conversation.py").read_text()
APP = (ROOT / "app/ios/Anticipy/AnticipyApp.swift").read_text()


def test_answers_and_corrections_reach_the_hands_scope():
    assert "You stopped and asked:" in BACKGROUND
    assert "They changed:" in BACKGROUND
    # the plain shadowing expression is gone
    assert ("scope: params._workflow?.authority_text\n"
            "          || params.approved_scope") not in BACKGROUND


def test_cancel_with_an_object_is_a_commit_not_a_dismissal():
    out = subprocess.run(
        ["node", "--input-type=module", "-e", """
import { externalControlSemantics } from '%s/extension/agent_loop.js';
const cases = [
  ['Cancel reservation', true],
  ['Cancel subscription', true],
  ['Cancel', false],
  ['Close', false],
  ['Search', false],
  ['Complete Reservation', true],
];
for (const [label, want] of cases) {
  const got = externalControlSemantics({ label });
  if (got !== want) throw new Error(`${label}: got ${got}, want ${want}`);
}
console.log('ok');
""" % ROOT], capture_output=True, text=True)
    assert "ok" in out.stdout, out.stderr


def test_chat_can_never_trigger_a_group_release():
    gate = CONV.split("elif (group and intent in")[1][:200]
    assert '"chat"' not in gate
    assert "_just_asked" in gate


def test_queued_jobs_are_cancellable_and_declines_stay_honest():
    assert "def _queued" in CONV
    assert "self._pending() + self._blocked() + self._queued()" in CONV
    assert "I couldn't stop anything just now" in CONV


def test_answer_keys_sort_identically_on_both_sides():
    assert 'String(format: "owner_answer_v%03d", approvedVersion)' in APP
    # zero-padded keys sort the same code-point-wise and numerically
    keys = ["owner_answer_v002", "owner_answer_v010", "owner_answer_v100"]
    assert sorted(keys) == keys
