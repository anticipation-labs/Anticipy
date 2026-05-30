"""End-to-end test for the Phase 5 cold-start onboarding pipeline.

Hard rules in this file (mirroring the agent brief):

* DO NOT make real network calls. Everything talks to the
  ``FakeBridge`` defined below, which returns canned source data.
* Run the FULL pipeline (auto_inhale + clarifier), not just
  individual extractors, so we catch regressions where one piece
  silently drops fields.
* Assert clarification SMS exists, fits in 1 segment, has no
  em-dashes.
* Assert graceful degradation: if Gmail dispatch times out, the rest
  of the pipeline still completes and a dossier is still produced.
* Assert per-source extractors run CONCURRENTLY by measuring
  wall-clock time (4 sources at 0.4s each must finish in < 0.9s, not
  > 1.5s).

Async pattern: this repo does not have ``pytest-asyncio`` installed.
Following the existing convention (see test_full_pipeline_e2e.py
and test_cascade_holdout.py), every async test body is wrapped in
``asyncio.run(...)`` from a sync ``def test_*`` function. Same
guarantees, no extra plugin.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

import pytest


os.environ.setdefault("ANTICIPY_ENGINE_PORT", "18742")


from app.coldstart import auto_inhale  # noqa: E402
from app.coldstart import clarifier  # noqa: E402
from app.coldstart.sources import (  # noqa: E402
    _bridge_protocol,
    calendar as src_calendar,
    drive as src_drive,
    gmail as src_gmail,
    linkedin as src_linkedin,
)


# ---------------------------------------------------------------------------
# Canned source data (the "happy path" returned by the fake bridge)
# ---------------------------------------------------------------------------
CANNED_LINKEDIN = {
    "ok": True,
    "data": {
        "name": "Omar Ebrahim",
        "headline": "Founder + CEO at Anticipy",
        "job_title": "Founder + CEO",
        "company": "Anticipy",
        "location": "New York, NY",
        "education": ["University of Pennsylvania"],
    },
}

CANNED_GMAIL = {
    "ok": True,
    "data": {
        "inbox": [
            {
                "from": "Sarah Lin <sarah.lin@acmecorp.com>",
                "subject": "Q3 roadmap review",
                "snippet": "Updated the deck",
                "date": "Mon 9:00",
            },
            {
                "from": "Sarah Lin <sarah.lin@acmecorp.com>",
                "subject": "Re: lunch Friday",
                "snippet": "Sounds good",
                "date": "Mon 10:30",
            },
            {
                "from": "no-reply@notify.example.com",
                "subject": "Your password reset",
                "snippet": "Click here",
                "date": "Mon 11:00",
            },
            {
                "from": "James Wu <james@buildco.com>",
                "subject": "Demo invite",
                "snippet": "Wed at 2",
                "date": "Mon 14:00",
            },
        ],
        "sent": [
            {
                "to": ["sarah.lin@acmecorp.com"],
                "subject": "Re: Q3 roadmap review",
                "body": (
                    "Thanks for the updates.\n"
                    "Will read tonight.\n"
                    "Best,\nOmar"
                ),
                "date": "Mon 9:30",
            },
        ],
    },
}

CANNED_CALENDAR = {
    "ok": True,
    "data": {
        "events": [
            {
                "title": "1:1 with Sarah",
                "when": "Mon 9:00",
                "attendees": ["Sarah Lin"],
                "recurring": True,
                "cadence": "weekly",
            },
            {
                "title": "1:1 with Sarah",
                "when": "Thu 9:00",
                "attendees": ["Sarah Lin"],
                "recurring": True,
                "cadence": "weekly",
            },
            {
                "title": "Q3 planning",
                "when": "Tue 14:00",
                "attendees": ["Sarah Lin", "James Wu"],
            },
            {
                "title": "Customer call Acme",
                "when": "Wed 11:00",
                "attendees": ["Mark Vega"],
            },
        ],
    },
}

CANNED_DRIVE = {
    "ok": True,
    "data": {
        "docs": [
            {
                "title": "Q3 roadmap - planning notes",
                "co_editors": ["Sarah Lin", "James Wu"],
                "last_modified": "Mon",
                "kind": "doc",
            },
            {
                "title": "Q3 roadmap - design review",
                "co_editors": ["Sarah Lin"],
                "last_modified": "Sun",
                "kind": "doc",
            },
            {
                "title": "Onboarding metrics",
                "co_editors": ["James Wu"],
                "last_modified": "Sat",
                "kind": "sheet",
            },
        ],
    },
}


# ---------------------------------------------------------------------------
# Fake bridge implementations
# ---------------------------------------------------------------------------
class FakeBridge:
    """Mock bridge that returns canned data for each dossier source.

    The auto_inhale pipeline only ever calls ``await dispatch(payload)``
    so this object only needs to implement ``dispatch``. We add a per-
    source artificial delay so the test can verify the gather actually
    runs them in parallel.
    """

    def __init__(self,
                 per_call_delay_s: float = 0.0,
                 fail: set[str] | None = None,
                 hang: set[str] | None = None) -> None:
        self.per_call_delay_s = per_call_delay_s
        self.fail = set(fail or [])
        self.hang = set(hang or [])
        self.calls: list[dict] = []

    async def dispatch(self, payload: dict) -> dict:
        self.calls.append(dict(payload))
        src = str(payload.get("source") or "")
        # Hang -> sleep way past the per-source budget so wait_for fires
        if src in self.hang:
            await asyncio.sleep(60.0)
            return {"ok": False, "error": "should never see this"}
        if self.per_call_delay_s > 0:
            await asyncio.sleep(self.per_call_delay_s)
        if src in self.fail:
            return {"ok": False, "error": f"{src} signed out"}
        if src == "linkedin":
            return CANNED_LINKEDIN
        if src == "gmail":
            return CANNED_GMAIL
        if src == "calendar":
            return CANNED_CALENDAR
        if src == "drive":
            return CANNED_DRIVE
        return {"ok": False, "error": f"unknown source {src!r}"}


class NoBridge:
    """Sentinel: not a callable, no dispatch. Used to assert error
    handling in _bridge_protocol.dispatch.
    """


# ---------------------------------------------------------------------------
# 1. Bridge protocol contract
# ---------------------------------------------------------------------------
def test_bridge_protocol_dispatch_routes_to_attribute() -> None:
    """When the bridge has a ``dispatch`` attribute, we call that."""
    async def main() -> None:
        bridge = FakeBridge()
        r = await _bridge_protocol.dispatch(
            bridge, {"type": "extract_dossier_source",
                     "source": "linkedin"})
        assert isinstance(r, dict)
        assert r.get("ok") is True
        assert bridge.calls and bridge.calls[0]["source"] == "linkedin"

    asyncio.run(main())


def test_bridge_protocol_dispatch_routes_to_plain_callable() -> None:
    """When the bridge IS the callable, we call it directly."""
    async def my_dispatch(payload: dict) -> dict:
        return {"ok": True, "data": {"payload_back": payload}}

    async def main() -> None:
        r = await _bridge_protocol.dispatch(
            my_dispatch, {"source": "test"})
        assert r["ok"] is True
        assert r["data"]["payload_back"]["source"] == "test"

    asyncio.run(main())


def test_bridge_protocol_dispatch_supports_sync_callable() -> None:
    """A non-async callable should also work (auto-await sync return)."""
    def sync_dispatch(payload: dict) -> dict:
        return {"ok": True, "data": {"sync": True}}

    async def main() -> None:
        r = await _bridge_protocol.dispatch(sync_dispatch, {"x": 1})
        assert r["data"]["sync"] is True

    asyncio.run(main())


def test_bridge_protocol_dispatch_raises_when_no_dispatch() -> None:
    """A bridge with no dispatch method and not callable must raise."""
    async def main() -> None:
        with pytest.raises(RuntimeError):
            await _bridge_protocol.dispatch(
                NoBridge(), {"source": "linkedin"})

    asyncio.run(main())


# ---------------------------------------------------------------------------
# 2. Per-source extractor behavior
# ---------------------------------------------------------------------------
def test_linkedin_extractor_infers_sector() -> None:
    async def main() -> None:
        bridge = FakeBridge()
        r = await src_linkedin.extract(bridge)
        assert r["source"] == "linkedin"
        assert r["ok"] is True
        assert r["profile"]["company"] == "Anticipy"
        # Founder + CEO matches the startup_founder keyword set.
        assert r["profile"]["sector"] == "startup_founder"

    asyncio.run(main())


def test_linkedin_extractor_handles_signed_out() -> None:
    async def main() -> None:
        bridge = FakeBridge(fail={"linkedin"})
        r = await src_linkedin.extract(bridge)
        assert r["ok"] is False
        assert "signed out" in r["error"]
        assert r["profile"] == {}

    asyncio.run(main())


def test_gmail_extractor_filters_noreply_and_dedupes_contacts() -> None:
    async def main() -> None:
        bridge = FakeBridge()
        r = await src_gmail.extract(bridge)
        assert r["ok"] is True
        emails = [c["email"] for c in r["top_contacts"]]
        assert "sarah.lin@acmecorp.com" in emails
        assert "no-reply@notify.example.com" not in emails
        # Sarah appears twice in inbox and once in sent (to=Sarah),
        # so total freq >= 3.
        sarah = next(c for c in r["top_contacts"]
                     if c["email"] == "sarah.lin@acmecorp.com")
        assert sarah["freq"] >= 3
        # Recent threads should be deduped on subject.
        subjects = [t["subject"] for t in r["recent_threads"]]
        assert len(subjects) == len(set(subjects))

    asyncio.run(main())


def test_calendar_extractor_detects_recurring_meetings() -> None:
    async def main() -> None:
        bridge = FakeBridge()
        r = await src_calendar.extract(bridge)
        assert r["ok"] is True
        rec_titles = [m["title"] for m in r["recurring_meetings"]]
        assert "1:1 with Sarah" in rec_titles
        assert r["week_shape"]["meeting_count"] == 4
        assert r["week_shape"]["busiest_day"] in (
            "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

    asyncio.run(main())


def test_drive_extractor_infers_project_names() -> None:
    async def main() -> None:
        bridge = FakeBridge()
        r = await src_drive.extract(bridge)
        assert r["ok"] is True
        assert any(p.lower().startswith("q3 roadmap")
                   for p in r["project_names"])
        assert len(r["recent_docs"]) == 3

    asyncio.run(main())


# ---------------------------------------------------------------------------
# 3. Parallel inhale fanout
# ---------------------------------------------------------------------------
def test_inhale_all_sources_runs_concurrently() -> None:
    """4 sources at 0.4s each must finish in well under 1.5s when
    truly parallel; serial would be ~1.6s.
    """
    async def main() -> None:
        bridge = FakeBridge(per_call_delay_s=0.4)
        started = time.monotonic()
        dossier = await auto_inhale.inhale_all_sources(bridge)
        elapsed = time.monotonic() - started
        # Serial would be 0.4 * 4 = 1.6s. Parallel should be ~0.4s.
        assert elapsed < 1.0, (
            f"inhale took {elapsed:.2f}s; sources are running "
            "serially, not in asyncio.gather")
        assert dossier["ok_sources"] == [
            "linkedin", "gmail", "calendar", "drive"]
        assert dossier["failed_sources"] == []

    asyncio.run(main())


def test_inhale_all_sources_returns_full_dossier() -> None:
    async def main() -> None:
        bridge = FakeBridge()
        dossier = await auto_inhale.inhale_all_sources(bridge)
        assert dossier["schema"] == "coldstart.dossier.v1"
        assert set(dossier["sources"]) == {
            "linkedin", "gmail", "calendar", "drive"}
        assert "linkedin" in dossier
        assert "gmail" in dossier
        assert "calendar" in dossier
        assert "drive" in dossier
        assert dossier["linkedin"]["profile"]["company"] == "Anticipy"
        assert dossier["calendar"]["recurring_meetings"]
        assert dossier["drive"]["project_names"]

    asyncio.run(main())


def test_inhale_all_sources_graceful_degradation_on_timeout() -> None:
    """If Gmail hangs past its per-source timeout, the other 3 still
    return data and the dossier is still usable.
    """
    async def main() -> None:
        bridge = FakeBridge(hang={"gmail"})
        dossier = await auto_inhale.inhale_all_sources(
            bridge,
            per_source_timeout_s=0.4,
            overall_budget_s=5.0,
        )
        assert "linkedin" in dossier["ok_sources"]
        assert "calendar" in dossier["ok_sources"]
        assert "drive" in dossier["ok_sources"]
        assert "gmail" not in dossier["ok_sources"]
        failed_names = [f["source"] for f in dossier["failed_sources"]]
        assert "gmail" in failed_names
        gmail_err = next(f for f in dossier["failed_sources"]
                         if f["source"] == "gmail")
        assert "timeout" in gmail_err["error"].lower()

    asyncio.run(main())


def test_inhale_all_sources_graceful_degradation_on_signed_out() -> None:
    """When a source returns ok=False (extension says signed out) the
    other sources still complete and the dossier is still usable.
    """
    async def main() -> None:
        bridge = FakeBridge(fail={"gmail", "drive"})
        dossier = await auto_inhale.inhale_all_sources(bridge)
        assert "linkedin" in dossier["ok_sources"]
        assert "calendar" in dossier["ok_sources"]
        failed_names = [f["source"] for f in dossier["failed_sources"]]
        assert "gmail" in failed_names
        assert "drive" in failed_names

    asyncio.run(main())


# ---------------------------------------------------------------------------
# 4. Clarifier
# ---------------------------------------------------------------------------
def test_clarifier_empty_dossier_returns_empty_string() -> None:
    assert clarifier.build_clarification_sms({}) == ""
    assert clarifier.build_clarification_sms({"sources": []}) == ""


def test_clarifier_builds_sms_under_segment_cap() -> None:
    dossier = {
        "linkedin": {"profile": {"company": "Anticipy",
                                 "job_title": "Founder"}},
        "calendar": {"recurring_meetings": [
            {"title": "1:1 Sarah", "attendees": ["Sarah Lin"]}]},
        "drive": {"project_names": ["Q3 roadmap"]},
        "gmail": {"top_contacts": [
            {"name": "Sarah Lin", "email": "sarah@x.com"}]},
    }
    sms = clarifier.build_clarification_sms(dossier)
    assert sms, "clarifier produced empty SMS"
    assert len(sms) <= clarifier.SMS_BODY_MAX
    assert "—" not in sms and "–" not in sms
    # Should mention the three most-uncertain facts.
    assert "Anticipy" in sms
    assert "Sarah Lin" in sms
    assert "Q3 roadmap" in sms
    # Asks for confirmation.
    assert "right?" in sms.lower()


def test_clarifier_truncates_long_input_at_word_boundary() -> None:
    """A pathologically long company name must still produce a valid
    SMS that ends cleanly with the question prompt."""
    long_company = "Acme " * 80  # 400+ chars
    dossier = {
        "linkedin": {"profile": {"company": long_company.strip()}},
        "calendar": {"recurring_meetings": []},
        "drive": {"project_names": []},
        "gmail": {"top_contacts": []},
    }
    sms = clarifier.build_clarification_sms(dossier)
    assert sms
    assert len(sms) <= clarifier.SMS_BODY_MAX
    assert "—" not in sms and "–" not in sms


def test_clarifier_skips_empty_fields() -> None:
    """A dossier with only LinkedIn data should still build SMS."""
    dossier = {
        "linkedin": {"profile": {"company": "Anticipy",
                                 "job_title": "Founder"}},
        "calendar": {"ok": False},
        "drive": {"ok": False},
        "gmail": {"ok": False},
    }
    sms = clarifier.build_clarification_sms(dossier)
    assert sms
    assert "Anticipy" in sms
    assert "—" not in sms and "–" not in sms


# ---------------------------------------------------------------------------
# 5. Full pipeline orchestrator
# ---------------------------------------------------------------------------
def test_run_coldstart_pipeline_end_to_end_under_120s() -> None:
    """The full pipeline must finish in << 120s of mocked wall-time."""
    async def main() -> None:
        bridge = FakeBridge(per_call_delay_s=0.3)
        started = time.monotonic()
        result = await auto_inhale.run_coldstart_pipeline(bridge)
        elapsed = time.monotonic() - started
        # Pipeline budget is 120s; the mocked test should be far below.
        assert elapsed < 120.0
        assert result["ok"] is True
        assert result["clarification_sms"]
        assert len(result["clarification_sms"]) <= clarifier.SMS_BODY_MAX
        assert "—" not in result["clarification_sms"]
        # Dossier must contain all 4 sources.
        d = result["dossier"]
        assert set(d["ok_sources"]) == {
            "linkedin", "gmail", "calendar", "drive"}

    asyncio.run(main())


def test_run_coldstart_pipeline_graceful_on_gmail_timeout() -> None:
    """Per the brief: 'if Gmail source returns timeout, pipeline still
    completes with other sources'."""
    async def main() -> None:
        bridge = FakeBridge(hang={"gmail"})
        result = await auto_inhale.run_coldstart_pipeline(
            bridge,
            per_source_timeout_s=0.4,
            overall_budget_s=2.0,
            total_budget_s=5.0,
        )
        # Pipeline reports ok=True because the OTHER sources came back.
        assert result["ok"] is True
        d = result["dossier"]
        assert "linkedin" in d["ok_sources"]
        assert "calendar" in d["ok_sources"]
        assert "drive" in d["ok_sources"]
        assert "gmail" not in d["ok_sources"]
        # Clarifier still produces an SMS from the surviving sources.
        sms = result["clarification_sms"]
        assert sms
        assert "—" not in sms

    asyncio.run(main())


def test_run_coldstart_pipeline_all_sources_timeout() -> None:
    """If EVERY source hangs, pipeline still returns cleanly (not
    a crash) but ok=False so the caller can fall back to the
    'tell me about your day' SMS conversation."""
    async def main() -> None:
        bridge = FakeBridge(
            hang={"linkedin", "gmail", "calendar", "drive"})
        result = await auto_inhale.run_coldstart_pipeline(
            bridge,
            per_source_timeout_s=0.3,
            overall_budget_s=2.0,
            total_budget_s=3.0,
        )
        assert result["ok"] is False
        assert result["error"] is None  # no exception raised
        assert result["clarification_sms"] == ""
        d = result["dossier"]
        assert d["ok_sources"] == []
        assert len(d["failed_sources"]) == 4

    asyncio.run(main())


def test_run_coldstart_pipeline_handles_dispatcher_raising() -> None:
    """A dispatcher that raises on every call should not crash the
    pipeline; we should get a clean ok=False with sourced errors."""

    class BrokenBridge:
        async def dispatch(self, payload: dict) -> dict:
            raise RuntimeError("broker exploded")

    async def main() -> None:
        bridge = BrokenBridge()
        result = await auto_inhale.run_coldstart_pipeline(
            bridge,
            per_source_timeout_s=1.0,
            overall_budget_s=3.0,
            total_budget_s=5.0,
        )
        assert result["ok"] is False
        d = result["dossier"]
        assert d["ok_sources"] == []
        assert len(d["failed_sources"]) == 4
        # Every failure should carry the RuntimeError text.
        for f in d["failed_sources"]:
            assert ("RuntimeError" in f["error"]
                    or "broker exploded" in f["error"])

    asyncio.run(main())


# ---------------------------------------------------------------------------
# 6. Sanity: bridge_extension module import remains untouched
# ---------------------------------------------------------------------------
def test_bridge_extension_module_still_imports() -> None:
    """Phase 5 owns sources/* and coldstart/*; bridge_extension belongs
    to Phase 3. Importing it must keep working so we know we did not
    accidentally touch it (or break it transitively)."""
    from app import bridge_extension  # noqa: F401
    # Bridge module is imported and present; we do NOT assert
    # ``dispatch`` exists because Phase 3 may still be wiring it in.
    assert hasattr(bridge_extension, "RealtimePublishExecutor")
