"""The certification may only feed the brain what a real phone can send.

The phone's voice tagger emits "owner", "other", or nothing — never a name,
and nothing at all until the owner has enrolled a voiceprint (enrollment is
dormant in the shipped build). The generator once labeled someone-else's-
errand stories "other:Jordan": ground truth flowing from the exam straight
into the examinee. Caught by the owner on 2026-08-14. These asserts keep the
exam honest.
"""
import json
import random
import tempfile
from pathlib import Path

from proof.engine_certification.generator import generate


def _cohort(count=120, seed=0xDECAF):
    with tempfile.TemporaryDirectory() as tmp:
        cases_path = Path(tmp) / "cases.json"
        oracle_path = Path(tmp) / "oracle.json"
        generate(count, cases_path, oracle_path, seed)
        return json.loads(cases_path.read_text())


def test_speaker_labels_are_only_what_the_phone_can_produce():
    doc = _cohort()
    cases = doc["cases"] if isinstance(doc, dict) else doc
    allowed = {"owner", "other", None}
    for case in cases:
        for utterance in case["utterances"]:
            assert utterance.get("speaker") in allowed, (
                f"case {case['id']} leaks an impossible speaker label: "
                f"{utterance.get('speaker')!r}")


def test_cohort_mixes_day_one_and_enrolled_reality():
    doc = _cohort()
    cases = doc["cases"] if isinstance(doc, dict) else doc
    enrolled = [c for c in cases if c.get("voice_enrolled")]
    day_one = [c for c in cases if not c.get("voice_enrolled")]
    assert len(enrolled) >= len(cases) // 4, "post-enrollment world underrepresented"
    assert len(day_one) >= len(cases) // 4, "day-one (no-verdict) world underrepresented"
    for case in day_one:
        for utterance in case["utterances"]:
            assert "speaker" not in utterance, (
                f"day-one case {case['id']} still carries a voice verdict")
