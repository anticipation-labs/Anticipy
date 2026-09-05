"""The deaf-ears gate must not hear its own proof script.  Audit F11 / F19.

WHAT WAS MEASURED, 2026-09-05 against production:

    speech heard in the last 24h            13
    newest speech of all time               2026-09-05 16:10:30Z (0.6h ago)
                                            from e2e-phone-2026-09-05
    [PASS] THE EARS ARE HEARD FROM          13 line(s) of speech arrived
    exit 0

Every one of those 13 rows came from proof/e2e_cloudflare.py. The newest real
phone on this backend had spoken on 2026-09-01. done_gate leg 1 turns this
gate's exit 0 into the sentence "and a real phone reached the server", so the
scoreboard was stating something false about production — the precise shape
(the alarm exists, the alarm says fine, the ears are deaf) that this gate was
written after two undetected outages to prevent.

These tests drive the gate's own main() against a backend holding that day's
row counts, and require the honest verdict.
"""
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from overnight import are_the_ears_live as M  # noqa: E402


class _Response:
    def __init__(self, payload, status=200):
        self._payload, self.status_code = payload, status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class Backend:
    """A backend whose rows are addressed the way the gate addresses them:
    by filter string. Records every filter it was asked, so the test can
    assert on the QUESTION as well as on the answer."""

    def __init__(self, real=0, probe=0, server=0,
                 newest_real=None, newest_probe=None, newest_server=None):
        self.counts = {"real": real, "probe": probe, "server": server}
        self.newest = {"real": newest_real, "probe": newest_probe,
                       "server": newest_server}
        self.filters = []

    def _which(self, filt):
        if f'device_id="{M.SERVER_DEVICE}"' in filt:
            return "server"
        if 'device_id ~ "e2e-"' in filt:
            return "probe"
        if 'device_id !~ "e2e-"' in filt:
            return "real"
        return "unfiltered"

    def get(self, url, headers=None, timeout=None, params=None):
        if url.endswith("/api/health"):
            return _Response({"code": 200})
        params = params or {}
        filt = params.get("filter", "")
        self.filters.append(filt)
        which = self._which(filt)
        if which == "unfiltered":
            raise AssertionError(
                f"the gate asked a question that cannot tell a probe from a "
                f"phone: {filt!r}")
        if params.get("sort"):
            row = self.newest[which]
            return _Response({"items": [row] if row else []})
        return _Response({"totalItems": self.counts[which], "items": []})


def _row(created, device):
    return {"created": created, "device_id": device, "owner_ref": "o",
            "source": "phone_mic"}


@pytest.fixture
def live_day(monkeypatch):
    """2026-09-05 exactly as production held it."""
    backend = Backend(
        real=0, probe=13, server=0,
        newest_real=_row("2026-09-01 05:02:45.099Z", "iphone-b113"),
        newest_probe=_row("2026-09-05 16:10:30.373Z", "e2e-phone-2026-09-05"),
        newest_server=_row("2026-09-02 04:58:52.716Z", "anticipy-brain"))
    monkeypatch.setattr(M.requests, "get", backend.get)
    monkeypatch.setattr(sys, "argv", ["are_the_ears_live.py"])
    return backend


def test_thirteen_probe_lines_are_not_a_phone(live_day, capsys):
    """The finding. Same day, same rows, and the verdict is DEAF."""
    code = M.main()

    assert code == 1, "a proof run must never prove the ears"
    out = capsys.readouterr().out
    assert "THE EARS ARE DEAF" in out


def test_the_screen_says_what_it_threw_away(live_day, capsys):
    """An exclusion nobody can see is one nobody can check."""
    M.main()

    out = capsys.readouterr().out
    assert "probe lines IGNORED" in out
    assert "13" in out


def test_a_probe_cannot_reset_the_silence_clock(live_day, capsys):
    """`newest speech` drives the two-cycle rule. Reading the probe's
    timestamp there made a four-day silence look 0.6 hours old, which is how
    the gate stayed quiet with no phone on the backend at all.

    The age is DERIVED from the fixture's own timestamp, never written as a
    literal. It was `"108" in out or "109" in out` for one afternoon and went
    red the same day, because the fixture pins the speech and the gate measures
    against the real clock: every hour that passes moves the answer. A test
    whose expectation expires teaches whoever hits it to widen the numbers
    until it stops complaining, and by then it is asserting nothing.
    """
    expected = (datetime.now(timezone.utc)
                - datetime(2026, 9, 1, 5, 2, 45, tzinfo=timezone.utc))
    hours = int(expected.total_seconds() // 3600)

    M.main()

    out = capsys.readouterr().out
    assert "iphone-b113" in out, "the newest REAL device must be the one named"
    assert "e2e-phone-2026-09-05" not in out
    # The gate rounds; accept the hour it lands in or either neighbour, and
    # nothing else. Reading the probe instead would print well under an hour.
    assert any(str(h) in out for h in (hours - 1, hours, hours + 1)), (
        f"the silence is {hours}h since 2026-09-01, not an hour: {out}")
    assert "0.6" not in out, "that is the probe's age, which is the whole bug"


def test_a_real_phone_still_proves_the_ears(monkeypatch, capsys):
    """The direction pin: the exclusion must not make the gate unfalsifiable.
    One line from a build stamps it alive, probes or no probes."""
    backend = Backend(
        real=1, probe=13, server=0,
        newest_real=_row("2026-09-05 15:00:00.000Z", "iphone-b124"),
        newest_probe=_row("2026-09-05 16:10:30.373Z", "e2e-phone-2026-09-05"),
        newest_server=None)
    monkeypatch.setattr(M.requests, "get", backend.get)
    monkeypatch.setattr(sys, "argv", ["are_the_ears_live.py"])

    assert M.main() == 0
    assert "SPEECH IS REACHING THE SERVER" in capsys.readouterr().out


def test_both_halves_quiet_is_still_unproven_not_deaf(monkeypatch, capsys):
    """The design the file rests on: a silent night is silent on both sides.
    Excluding probes must not turn an idle day into an incident."""
    backend = Backend(
        real=0, probe=0, server=0,
        newest_real=_row("2026-09-05 09:00:00.000Z", "iphone-b124"),
        newest_server=None)
    monkeypatch.setattr(M.requests, "get", backend.get)
    monkeypatch.setattr(sys, "argv", ["are_the_ears_live.py"])

    assert M.main() == 2
    assert "UNPROVEN" in capsys.readouterr().out


def test_the_control_half_is_untouched(live_day):
    """The server-write count is the control, and it must go on counting the
    brain's own rows — the exclusion belongs to the speech half only."""
    M.main()

    server_questions = [f for f in live_day.filters
                        if f'device_id="{M.SERVER_DEVICE}"' in f]
    assert server_questions, "the control half must still be asked"
    assert all("e2e-" not in f for f in server_questions), (
        "the brain is not a probe; its rows are the control")


def test_todays_shape_is_pinned_in_the_self_test():
    """A live incident that is not in the self-test is one the next agent can
    delete by accident."""
    assert M.verdict(0, 0, silence_hours=107.0)[0] == 1
    assert M.self_test() == 0
