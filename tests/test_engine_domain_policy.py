from __future__ import annotations

import pytest

from brain.anticipy_core import is_consequential


WORLD_CHANGING_GOALS = [
    "Book a table at Harbour & Pine for four",
    "Submit an urgent maintenance request for unit 18B",
    "Dispute the NorthGrid bill on account NG-20491",
    "Request a replacement for order PK-77104",
    "Open a mail-in warranty repair for serial SN-A4421",
    "Schedule vehicle recall R24-118 for August 18",
    "Reduce the Anticipy workspace from 24 seats to 17",
    "Submit Agents That Earn Trust to the Applied AI track",
    "Register Jordan Lee's vehicle for guest parking",
    "Give permission for Maya to attend the Science Centre trip",
    "Book Luna for a rabies vaccination",
    "Open a windshield claim on policy AUTO-441208",
    "Submit the client-meal expense",
    "Request front-row seating and live captions",
    "Move electricity and water to the new address",
    "Renew professional license ARCH-48217",
    "Dispute invoice INV-8842 and request a corrected invoice",
    "Cancel membership MBR-20491 at the end of the period",
    "Schedule Priya for a dental cleaning",
    "Send Jordan this exact message",
]


@pytest.mark.parametrize("goal", WORLD_CHANGING_GOALS)
def test_all_twenty_day_zero_domains_cross_the_confirmation_boundary(goal):
    assert is_consequential(goal, explicit=True), goal


@pytest.mark.parametrize("goal", [
    "Research invoice dispute rules",
    "Compare mail-in warranty options",
    "Open Chrome",
    "Tell me which clinics have weekend appointments",
])
def test_read_only_work_stays_outside_the_confirmation_boundary(goal):
    assert not is_consequential(goal, explicit=True), goal
