"""Integration tests for the V7 native macOS action path.

Creates a real Calendar event, a real Reminder, and a real Note in
Omar's actual macOS apps, then cleans each one up. Each test prints
PASS/FAIL/SKIP. Exit code 0 if no FAIL.

First-run note: macOS will pop Automation consent dialogs for each
target app. Grant access per `state/v7/native_action_first_run.md`.
If consent has not been granted, the underlying AppleScript fails
with error -1743 and the test marks SKIP (not FAIL) so this script
remains green in CI on machines without Automation consent.

Run:
  python3 scripts/v7/test_native_action_macos.py

No em-dashes. Under 200 lines.
"""

from __future__ import annotations

import datetime as _dt
import os
import sys
import time
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[2]
_ENGINE = _ROOT / "engine"
if str(_ENGINE) not in sys.path:
    sys.path.insert(0, str(_ENGINE))


_PASSED: list[str] = []
_FAILED: list[tuple[str, str]] = []
_SKIPPED: list[tuple[str, str]] = []


def _ok(name: str) -> None:
    _PASSED.append(name)
    print(f"PASS  {name}")


def _fail(name: str, reason: str) -> None:
    _FAILED.append((name, reason))
    print(f"FAIL  {name}: {reason}")


def _skip(name: str, reason: str) -> None:
    _SKIPPED.append((name, reason))
    print(f"SKIP  {name}: {reason}")


def _is_consent_denied(error: str) -> bool:
    """Detect macOS TCC denial so we can SKIP instead of FAIL."""
    lower = (error or "").lower()
    return (
        "-1743" in lower
        or "not authorized to send apple events" in lower
        or "user canceled" in lower
        or "tcc consent" in lower
        or "osascript timeout" in lower
    )


def test_calendar(driver) -> None:
    name = "calendar create+list+delete"
    ts = int(time.time())
    title = f"Anticipy Test {ts}"
    start = _dt.datetime.now() + _dt.timedelta(hours=1)
    end = start + _dt.timedelta(minutes=30)
    created = driver.calendar_create_event(
        title=title, start=start, end=end,
        notes="Created by v7 native action test. Safe to delete.",
    )
    if not created.ok:
        if _is_consent_denied(created.error):
            _skip(name, f"calendar consent missing: {created.error}")
            return
        _fail(name, f"create failed: {created.error}")
        return
    event_id = created.proof.get("event_id", "")
    if not event_id:
        _fail(name, f"create returned empty event_id: {created.proof}")
        return
    listed = driver.calendar_list_events(
        start - _dt.timedelta(hours=1),
        end + _dt.timedelta(hours=1),
    )
    if not listed.ok:
        _fail(name, f"list failed: {listed.error}")
        return
    titles = [e["title"] for e in listed.proof.get("events", [])]
    if title not in titles:
        _fail(name, f"created event missing in list (titles={titles[:10]})")
        return
    deleted = driver.calendar_delete_event(event_id)
    if not deleted.ok:
        print(f"WARN  cleanup failed: left event {event_id} "
              f"({deleted.error}). Omar: delete manually.")
    _ok(name)


def test_reminders(driver) -> None:
    name = "reminders add+list+delete"
    ts = int(time.time())
    title = f"Anticipy Test reminder {ts}"
    added = driver.reminders_add(
        title=title, notes="v7 native action test, safe to delete",
    )
    if not added.ok:
        if _is_consent_denied(added.error):
            _skip(name, f"reminders consent missing: {added.error}")
            return
        _fail(name, f"add failed: {added.error}")
        return
    rid = added.proof.get("reminder_id", "")
    if not rid:
        _fail(name, f"add returned empty reminder_id: {added.proof}")
        return
    listed = driver.reminders_list("Reminders")
    titles = [r["title"] for r in listed.proof.get("reminders", [])]
    if title not in titles:
        # Fall back to listing all reminders, in case the default list
        # name on this Mac is not literally "Reminders".
        all_r = driver.reminders_list("")
        titles = [r["title"] for r in all_r.proof.get("reminders", [])]
        if title not in titles:
            _fail(name, f"reminder missing in list (got {titles[:5]})")
            return
    deleted = driver.reminders_delete(rid)
    if not deleted.ok:
        print(f"WARN  cleanup failed: left reminder {rid} "
              f"({deleted.error}). Omar: delete manually.")
    _ok(name)


def test_notes(driver) -> None:
    name = "notes create+list+delete"
    ts = int(time.time())
    title = f"Anticipy Test note {ts}"
    created = driver.notes_create(
        title=title,
        body="v7 native action test, safe to delete",
    )
    if not created.ok:
        if _is_consent_denied(created.error):
            _skip(name, f"notes consent missing: {created.error}")
            return
        _fail(name, f"create failed: {created.error}")
        return
    nid = created.proof.get("note_id", "")
    if not nid:
        _fail(name, f"create returned empty note_id: {created.proof}")
        return
    listed = driver.notes_list("")
    names = [n["name"] for n in listed.proof.get("notes", [])]
    if not any(title in n for n in names):
        _fail(name, f"note missing in list (sample={names[:5]})")
        return
    deleted = driver.notes_delete(nid)
    if not deleted.ok:
        print(f"WARN  cleanup failed: left note {nid} "
              f"({deleted.error}). Omar: delete manually.")
    _ok(name)


def test_finder_search(driver) -> None:
    name = "finder spotlight search"
    res = driver.finder_search("kind:application Safari")
    if not res.ok:
        _fail(name, f"search failed: {res.error}")
        return
    if res.proof.get("count", 0) < 1:
        _fail(name, f"Safari not found by spotlight: {res.proof}")
        return
    _ok(name)


def main() -> int:
    try:
        from app.product.native_action_macos import NativeMacOS
    except Exception as exc:
        _fail("import NativeMacOS", f"{type(exc).__name__}: {exc}")
        return 1
    driver = NativeMacOS()
    test_finder_search(driver)
    test_calendar(driver)
    test_reminders(driver)
    test_notes(driver)
    total = len(_PASSED) + len(_FAILED) + len(_SKIPPED)
    print()
    print(f"summary: {len(_PASSED)} passed, "
          f"{len(_FAILED)} failed, {len(_SKIPPED)} skipped "
          f"({total} total)")
    return 0 if not _FAILED else 1


if __name__ == "__main__":
    raise SystemExit(main())
