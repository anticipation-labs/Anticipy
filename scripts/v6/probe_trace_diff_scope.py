#!/usr/bin/env python3
"""Probe script-scoped trace diffs for V6 evaluator inputs."""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
TRACE_READER = ROOT / "verifier" / "v6" / "trace_reader.py"


def load_trace_reader() -> Any:
    spec = importlib.util.spec_from_file_location("trace_reader", TRACE_READER)
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not load {TRACE_READER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tr = load_trace_reader()


def assert_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def page(surface: str, url: str, title: str, text: str = "", read_error: str = "") -> dict:
    return {
        "surface": surface,
        "url": url,
        "title": title,
        "visible_text": text,
        "inputs": [],
        "read_error": read_error,
    }


def trace(pages: list[dict], ax: str = "Finder windows=1", terminal: str = "$ ready") -> dict:
    return {
        "pages": pages,
        "native_ax": {"ok": True, "summary": ax},
        "terminal": {"ok": True, "text": terminal},
    }


def run_basic_scope_probe() -> None:
    script = {
        "verb_category": "email",
        "moments": [
            {
                "surface": "Gmail",
                "source_surface": "Anticipy",
                "intent": "Reply from the user's normal Gmail tab.",
            }
        ],
    }

    baseline = trace(
        [
            page("gmail", "https://mail.google.com/mail/u/0/#inbox", "Inbox", "before"),
            page("anticipy", "http://127.0.0.1:8731/app", "Anticipy", "idle"),
            page("browser", "https://example.test/noise", "Noise", "old"),
        ],
        ax="Finder windows=1",
        terminal="$ idle",
    )
    current = trace(
        [
            page("gmail", "https://mail.google.com/mail/u/0/#inbox", "Inbox", "after"),
            page("anticipy", "http://127.0.0.1:8731/app", "Anticipy", "idle"),
            page("browser", "https://example.test/noise", "Noise", "new"),
        ],
        ax="Finder windows=2 title=Downloads",
        terminal="$ unrelated build output",
    )

    scoped = tr.trace_diff(baseline, current, script)
    assert_equal(scoped["scoped_to_script"], True, "script scoping flag")
    assert_equal(scoped["script_surface_scope"], ["anticipy", "gmail"], "script surface scope")
    assert_equal(scoped["changed_surfaces"], ["gmail"], "script-scoped changed surfaces")
    assert_equal(
        scoped["all_changed_surfaces"],
        ["browser", "gmail", "native_ax", "terminal"],
        "audit changed surfaces",
    )
    assert_equal(
        scoped["unrelated_changed_surfaces"],
        ["browser", "native_ax", "terminal"],
        "unrelated churn remains visible",
    )
    assert_equal(scoped["missing_script_surfaces"], [], "script surfaces observed")

    legacy = tr.trace_diff(baseline, current)
    assert_equal(legacy["scoped_to_script"], False, "legacy scoping flag")
    assert_equal(
        legacy["changed_surfaces"],
        ["browser", "gmail", "native_ax", "terminal"],
        "legacy changed surfaces",
    )
    assert_equal(legacy["unrelated_changed_surfaces"], [], "legacy unrelated churn")

    broken_current = trace(
        [
            page(
                "gmail",
                "https://mail.google.com/mail/u/0/#inbox",
                "Inbox",
                "",
                "Runtime.evaluate timed out",
            ),
            page("anticipy", "http://127.0.0.1:8731/app", "Anticipy", "decline card"),
        ]
    )
    broken = tr.trace_diff(baseline, broken_current, script)
    assert_equal(broken["broken_script_surfaces"], ["gmail"], "broken script surface")
    assert_equal(broken["missing_script_surfaces"], [], "broken surface still observed")


def run_c179_surface_scope_probe() -> None:
    script = {
        "id": "c179",
        "title": "Launch admin request delivered through Chrome on port 9222",
        "delivery": {
            "carrier": "Chrome on port 9222",
            "surface": "Chrome on port 9222",
        },
        "rolling_breadth_metadata": {
            "hard_categories": ["e-commerce", "native", "ambient"],
            "notes": "Rolling breadth still mentions browser, native Mac apps, and Amazon commerce.",
            "recent_surfaces": ["Amazon", "Browser", "native_ax"],
        },
        "tab_inventory": [
            {"url": "https://www.amazon.com/orders", "title": "Amazon orders"},
            {"url": "chrome://newtab", "title": "New Tab"},
        ],
        "moments": [
            {
                "user_surface": "Anticipy",
                "request": (
                    "Use Gmail, Google Sheets, Google Calendar, and Canva/canvas "
                    "to handle the launch follow-up."
                ),
                "expected_visible_surfaces": [
                    "Gmail",
                    "Google Sheets",
                    "Google Calendar",
                    "Canva/canvas",
                ],
            }
        ],
    }

    baseline = trace(
        [
            page("anticipy", "http://127.0.0.1:8731/app", "Anticipy", "idle"),
            page("gmail", "https://mail.google.com/mail/u/0/#inbox", "Inbox", "before"),
            page(
                "google_sheets",
                "https://docs.google.com/spreadsheets/d/sheet-id/edit",
                "Launch tracker",
                "old row",
            ),
            page(
                "google_calendar",
                "https://calendar.google.com/calendar/u/0/r/week",
                "Calendar",
                "free at 3",
            ),
            page("canvas_design", "https://www.canva.com/design/launch", "Canva", "draft"),
            page("commerce", "https://www.amazon.com/orders", "Amazon orders", "stale order"),
            page("browser", "https://example.test/noise", "Noise", "old"),
        ],
        ax="Finder windows=1",
        terminal="$ idle",
    )
    current = trace(
        [
            page("anticipy", "http://127.0.0.1:8731/app", "Anticipy", "idle"),
            page("gmail", "https://mail.google.com/mail/u/0/#inbox", "Inbox", "draft ready"),
            page(
                "google_sheets",
                "https://docs.google.com/spreadsheets/d/sheet-id/edit",
                "Launch tracker",
                "new row",
            ),
            page(
                "google_calendar",
                "https://calendar.google.com/calendar/u/0/r/week",
                "Calendar",
                "",
                "Runtime.evaluate timed out",
            ),
            page("canvas_design", "https://www.canva.com/design/launch", "Canva", "updated draft"),
            page("commerce", "https://www.amazon.com/orders", "Amazon orders", "stale order refreshed"),
            page("browser", "https://example.test/noise", "Noise", "new unrelated text"),
        ],
        ax="Finder windows=2 title=Downloads",
        terminal="$ unrelated build output",
    )

    scoped = tr.trace_diff(baseline, current, script)
    assert_equal(scoped["scoped_to_script"], True, "c179 scoping flag")
    assert_equal(
        scoped["script_surface_scope"],
        ["anticipy", "canvas_design", "gmail", "google_calendar", "google_sheets"],
        "c179 script surface scope",
    )
    assert_equal(
        scoped["changed_surfaces"],
        ["canvas_design", "gmail", "google_calendar", "google_sheets"],
        "c179 script-scoped changed surfaces",
    )
    assert_equal(
        scoped["all_changed_surfaces"],
        [
            "browser",
            "canvas_design",
            "commerce",
            "gmail",
            "google_calendar",
            "google_sheets",
            "native_ax",
            "terminal",
        ],
        "c179 audit changed surfaces",
    )
    assert_equal(
        scoped["unrelated_changed_surfaces"],
        ["browser", "commerce", "native_ax", "terminal"],
        "c179 unrelated churn remains visible",
    )
    assert_equal(
        scoped["broken_script_surfaces"],
        ["google_calendar"],
        "c179 broken script surface",
    )
    assert_equal(scoped["missing_script_surfaces"], [], "c179 script surfaces observed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=["all", "basic", "c179-surface-scope"], default="all")
    args = parser.parse_args()

    if args.case in {"all", "basic"}:
        run_basic_scope_probe()
    if args.case in {"all", "c179-surface-scope"}:
        run_c179_surface_scope_probe()

    print("trace diff script scoping probe passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
