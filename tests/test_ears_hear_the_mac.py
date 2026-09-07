"""The deaf-ears gate says which EAR spoke, and the Mac is one of them.

Issue #37. The Mac meeting recorder shipped as build 119 with the Railway
PocketBase URL baked in, after the phone had moved to the Worker at
api.anticipy.ai. Every meeting it recorded was posted to a backend nothing
read. `are_the_ears_live.py` could not have said so: it counted one total,
and the phone alone kept that total green.

The gate now prints a count per ear — phone, pendant, Mac — over the same
window, with the same probe exclusion. The verdict is unchanged: one line
from any ear still proves the ears. What changes is that a Mac delivering
nothing is a visible zero beside a phone delivering plenty.

These tests drive the gate's main() against a backend addressed by filter
string, the way tests/test_ears_ignore_the_probe.py does, and pin the source
value the gate asks for to the one the Mac's own wire stamps.
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from overnight import are_the_ears_live as M  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIRE = os.path.join(ROOT, "app/macos/Anticipy/Capture/TranscriptWire.swift")


class _Response:
    def __init__(self, payload, status=200):
        self._payload, self.status_code = payload, status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class Backend:
    """Rows addressed the way the gate addresses them. `by_source` holds
    the real (non-probe) transcript count per `source`; the unqualified
    real count is their sum, which is what production would answer."""

    def __init__(self, by_source, server=0, newest_real=None):
        self.by_source = dict(by_source)
        self.server = server
        self.newest_real = newest_real
        self.filters = []

    def get(self, url, headers=None, timeout=None, params=None):
        if url.endswith("/api/health"):
            return _Response({"code": 200})
        params = params or {}
        filt = params.get("filter", "")
        self.filters.append(filt)
        if params.get("sort"):
            row = self.newest_real if 'device_id !~ "e2e-"' in filt else None
            return _Response({"items": [row] if row else []})
        if f'device_id="{M.SERVER_DEVICE}"' in filt:
            return _Response({"totalItems": self.server})
        if 'device_id ~ "e2e-"' in filt:
            return _Response({"totalItems": 0})
        assert 'device_id !~ "e2e-"' in filt, (
            f"a speech question that cannot tell a probe from an ear: {filt!r}")
        m = re.search(r'source="([^"]*)"', filt)
        if m:
            return _Response({"totalItems": self.by_source.get(m.group(1), 0)})
        return _Response({"totalItems": sum(self.by_source.values())})


def _drive(monkeypatch, backend):
    monkeypatch.setattr(M.requests, "get", backend.get)
    monkeypatch.setattr(sys, "argv", ["are_the_ears_live.py"])


def _line(out: str, label: str) -> str:
    for line in out.splitlines():
        if label in line:
            return line
    raise AssertionError(f"no {label!r} line in:\n{out}")


def test_the_gate_asks_for_the_source_the_mac_stamps():
    """Cross-language pin. The Swift wire and the Python gate each hold the
    string; if either moves, the Mac's rows fall out of the Mac's own count
    and the line reads 0 on a Mac that is delivering."""
    src = open(WIRE, encoding="utf-8").read()
    m = re.search(r'public static let source = "([^"]+)"', src)
    assert m, "TranscriptWire.swift no longer declares its source"
    assert m.group(1) == M.MAC_SOURCE
    assert dict(M.EARS)["Mac"] == M.MAC_SOURCE


def test_each_ear_is_counted_with_the_probe_excluded(monkeypatch, capsys):
    backend = Backend({"phone_mic": 40, "pendant": 0, "mac": 7}, server=9,
                      newest_real={"created": "2026-09-06 18:00:00.000Z",
                                   "device_id": "mac-b151",
                                   "owner_ref": "o", "source": "mac"})
    _drive(monkeypatch, backend)

    assert M.main() == 0
    out = capsys.readouterr().out
    assert _line(out, "heard by the Mac").rstrip().endswith(" 7")
    assert _line(out, "heard by the phone").rstrip().endswith(" 40")
    assert _line(out, "heard by the pendant").rstrip().endswith(" 0")
    ear_questions = [f for f in backend.filters if 'source="' in f]
    assert len(ear_questions) == len(M.EARS)
    assert all(M.NOT_A_PROBE in f for f in ear_questions), (
        "an ear count that includes the probe would credit the Mac with "
        "speech proof/e2e_cloudflare.py typed")
    assert all('kind="transcript"' in f for f in ear_questions)


def test_a_mute_mac_is_a_visible_zero_beside_a_live_phone(monkeypatch, capsys):
    """Build 119's exact shape: the phone delivers, the Mac delivers nothing,
    the verdict is green — and the screen now says which ear is silent."""
    backend = Backend({"phone_mic": 25, "pendant": 0, "mac": 0}, server=12)
    _drive(monkeypatch, backend)

    assert M.main() == 0, "a live phone still proves the ears"
    out = capsys.readouterr().out
    assert _line(out, "heard by the Mac").rstrip().endswith(" 0")
    assert _line(out, "heard by the phone").rstrip().endswith(" 25")


def test_a_mac_alone_proves_the_ears(monkeypatch, capsys):
    """The direction pin: the Mac is an ear, not a footnote. A day on which
    only the Mac delivered is a day speech arrived."""
    backend = Backend({"phone_mic": 0, "pendant": 0, "mac": 3}, server=12,
                      newest_real={"created": "2026-09-06 18:00:00.000Z",
                                   "device_id": "mac-b151",
                                   "owner_ref": "o", "source": "mac"})
    _drive(monkeypatch, backend)

    assert M.main() == 0
    out = capsys.readouterr().out
    assert "SPEECH IS REACHING THE SERVER" in out
    assert "mac-b151" in out, "the newest device named is the Mac build"


def test_nothing_from_any_ear_is_still_deaf(monkeypatch, capsys):
    """The per-ear lines must not soften the verdict: three zeros beside a
    working server are the outage this gate exists for."""
    backend = Backend({"phone_mic": 0, "pendant": 0, "mac": 0}, server=30)
    _drive(monkeypatch, backend)

    assert M.main() == 1
    assert "THE EARS ARE DEAF" in capsys.readouterr().out


def test_the_ear_counts_never_request_the_words(monkeypatch):
    """The header's promise, kept by the new requests too."""
    seen = []

    def get(url, headers=None, timeout=None, params=None):
        seen.append(params or {})
        if url.endswith("/api/health"):
            return _Response({"code": 200})
        return _Response({"totalItems": 1, "items": []})

    monkeypatch.setattr(M.requests, "get", get)
    monkeypatch.setattr(sys, "argv", ["are_the_ears_live.py"])
    M.main()
    for params in seen:
        if "fields" in params:
            assert "text" not in params["fields"].split(",")


def test_the_self_test_still_holds():
    assert M.self_test() == 0
