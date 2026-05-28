"""Native macOS action path for the user-device engine.

HANDS for native macOS apps. Per-app methods do real actions and return
verifiable proofs (event_id, file path, etc.) the dispatcher can
re-check visually or via Spotlight/AppleScript. Backed by `osascript`
and `cliclick`. First-run triggers Automation consent dialogs; see
`state/v7/native_action_first_run.md`. No em-dashes.
"""

from __future__ import annotations

import datetime as _dt
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


SCREENSHOT_DIR = Path(os.environ.get(
    "ANTICIPY_NATIVE_SCREENSHOTS",
    str(Path.home() / ".anticipy" / "screenshots" / "native"),
))


def _quote(value: Any) -> str:
    raw = "" if value is None else str(value)
    return '"' + raw.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _osa(script: str, timeout: float = 25.0) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["/usr/bin/osascript", "-e", script],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            args=["osascript"], returncode=124, stdout="",
            stderr=f"osascript timeout after {timeout}s (likely TCC consent dialog)",
        )


def _iso_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _apple_date(value: Any) -> str:
    """Format a datetime or ISO string as `Monday, May 26, 2026 at 3:00:00 PM`."""
    if isinstance(value, _dt.datetime):
        when = value
    else:
        try:
            when = _dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except Exception:
            when = _dt.datetime.now()
    if when.tzinfo is not None:
        when = when.astimezone().replace(tzinfo=None)
    return when.strftime("%A, %B %d, %Y at %I:%M:%S %p")


@dataclass
class NativeResult:
    """Receipt returned by every native action primitive."""

    ok: bool
    app: str
    operation: str
    proof: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    source: str = "native_action_macos"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": bool(self.ok), "app": self.app,
            "operation": self.operation, "proof": dict(self.proof),
            "error": self.error or "", "source": self.source,
        }


def _err(app: str, op: str, msg: str) -> NativeResult:
    return NativeResult(ok=False, app=app, operation=op, error=msg)


def _parse_table(text: str, fields: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in (text or "").splitlines():
        parts = line.split("||")
        if len(parts) >= len(fields):
            row = {}
            for i, name in enumerate(fields):
                val = parts[i]
                if name.endswith("?"):
                    row[name[:-1]] = val.strip().lower() == "true"
                else:
                    row[name] = val
            rows.append(row)
    return rows


class NativeMacOS:
    """Per-app driver: Calendar, Reminders, Notes, Finder, Messages."""

    TIMEOUT = 25.0

    def __init__(self, *, screenshot_dir: Path | None = None) -> None:
        self.screenshot_dir = Path(screenshot_dir or SCREENSHOT_DIR)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    def is_app_running(self, bundle_id_or_name: str) -> bool:
        if not bundle_id_or_name:
            return False
        is_bundle = "." in bundle_id_or_name and " " not in bundle_id_or_name
        key = "bundle identifier" if is_bundle else "name"
        script = (
            'tell application "System Events" to return (exists '
            f"(first process whose {key} is {_quote(bundle_id_or_name)}))"
        )
        res = _osa(script, timeout=8.0)
        return res.returncode == 0 and "true" in (res.stdout or "").lower()

    def activate_app(self, bundle_id_or_name: str) -> NativeResult:
        if not bundle_id_or_name:
            return _err("", "activate", "bundle_id_or_name required")
        target = _quote(bundle_id_or_name)
        if "." in bundle_id_or_name and " " not in bundle_id_or_name:
            script = f"tell application id {target} to activate"
        else:
            script = f"tell application {target} to activate"
        res = _osa(script, timeout=8.0)
        if res.returncode != 0:
            return _err(bundle_id_or_name, "activate",
                        (res.stderr or "activation failed").strip())
        return NativeResult(
            ok=True, app=bundle_id_or_name, operation="activate",
            proof={"activated_at": _iso_now()},
        )

    def screenshot_app(self, bundle_id_or_name: str) -> str:
        """Bring app forward and capture full screen. Returns PNG path or ''."""
        if not bundle_id_or_name:
            return ""
        is_bundle = (
            "." in bundle_id_or_name and " " not in bundle_id_or_name
        )
        proc_clause = (
            f"first process whose bundle identifier is "
            f"{_quote(bundle_id_or_name)}" if is_bundle else
            f"process {_quote(bundle_id_or_name)}"
        )
        _osa(
            'tell application "System Events"\n'
            f"  set frontmost of ({proc_clause}) to true\n"
            "end tell\ndelay 0.4",
            timeout=8.0,
        )
        ts = time.strftime("%Y%m%d-%H%M%S")
        safe = "".join(c if c.isalnum() else "_" for c in bundle_id_or_name)
        out = self.screenshot_dir / f"native-{safe}-{ts}.png"
        res = subprocess.run(
            ["/usr/sbin/screencapture", "-o", "-x", str(out)],
            capture_output=True, text=True, timeout=8.0, check=False,
        )
        return str(out) if res.returncode == 0 and out.exists() else ""

    def calendar_create_event(
        self, title: str, start: Any, end: Any,
        location: str = "", notes: str = "", calendar_name: str = "",
    ) -> NativeResult:
        if not title:
            return _err("Calendar", "create_event", "title required")
        cal_clause = (
            f"first calendar whose name is {_quote(calendar_name)}"
            if calendar_name else
            "first calendar whose writable is true"
        )
        script = (
            'tell application "Calendar"\n  launch\n'
            f"  set theCal to {cal_clause}\n  tell theCal\n"
            "    set newEvt to make new event at end of events with properties "
            "{summary:" + _quote(title)
            + ", start date:date " + _quote(_apple_date(start))
            + ", end date:date " + _quote(_apple_date(end))
            + ", location:" + _quote(location)
            + ", description:" + _quote(notes) + "}\n"
            "  end tell\n  set evtId to uid of newEvt\n"
            '  return evtId & "||" & (name of theCal)\nend tell'
        )
        res = _osa(script, timeout=self.TIMEOUT)
        if res.returncode != 0:
            return _err("Calendar", "create_event",
                        (res.stderr or res.stdout or "create failed").strip())
        evt_id, _, cal_used = (res.stdout or "").strip().partition("||")
        return NativeResult(
            ok=True, app="Calendar", operation="create_event",
            proof={
                "event_id": evt_id.strip(),
                "calendar_name": cal_used.strip(),
                "created_at_iso": _iso_now(), "title": title,
                "start": _apple_date(start), "end": _apple_date(end),
            },
        )

    def calendar_list_events(
        self, start_date: Any, end_date: Any,
    ) -> NativeResult:
        script = (
            'tell application "Calendar"\n'
            "  set sd to date " + _quote(_apple_date(start_date)) + "\n"
            "  set ed to date " + _quote(_apple_date(end_date)) + "\n"
            "  set out to {}\n  repeat with c in calendars\n"
            "    set theEvents to (every event of c whose start date "
            "is greater than or equal to sd and start date is less than "
            "or equal to ed)\n"
            "    repeat with e in theEvents\n"
            "      set end of out to ((uid of e) as string) & \"||\" & "
            "(summary of e) & \"||\" & ((start date of e) as string) "
            "& \"||\" & (name of c)\n"
            "    end repeat\n  end repeat\n"
            "  set AppleScript's text item delimiters to linefeed\n"
            "  return out as string\nend tell"
        )
        res = _osa(script, timeout=self.TIMEOUT)
        if res.returncode != 0:
            return _err("Calendar", "list_events",
                        (res.stderr or "list failed").strip())
        events = _parse_table(
            res.stdout or "",
            ["event_id", "title", "start", "calendar_name"],
        )
        return NativeResult(
            ok=True, app="Calendar", operation="list_events",
            proof={"events": events, "count": len(events)},
        )

    def calendar_delete_event(self, event_id: str) -> NativeResult:
        if not event_id:
            return _err("Calendar", "delete_event", "event_id required")
        script = (
            'tell application "Calendar"\n  set didDelete to false\n'
            "  repeat with c in calendars\n    try\n"
            "      set victim to (first event of c whose uid is "
            + _quote(event_id) + ")\n      delete victim\n"
            "      set didDelete to true\n      exit repeat\n    end try\n"
            "  end repeat\n  return didDelete as string\nend tell"
        )
        res = _osa(script, timeout=self.TIMEOUT)
        deleted = "true" in (res.stdout or "").lower()
        return NativeResult(
            ok=deleted, app="Calendar", operation="delete_event",
            proof={"event_id": event_id, "deleted": deleted},
            error="" if deleted else (res.stderr or "not found").strip(),
        )

    def reminders_add(
        self, title: str, due: Any = "",
        list_name: str = "Reminders", notes: str = "",
    ) -> NativeResult:
        if not title:
            return _err("Reminders", "add", "title required")
        list_clause = (
            f"list {_quote(list_name)}" if list_name else "default list"
        )
        due_clause = ""
        if due:
            d = _quote(_apple_date(due))
            due_clause = (
                f", remind me date:date {d}, due date:date {d}"
            )
        script = (
            'tell application "Reminders"\n  launch\n'
            f"  tell {list_clause}\n"
            "    set newR to make new reminder with properties {name:"
            + _quote(title) + ", body:" + _quote(notes) + due_clause + "}\n"
            "    set rid to id of newR\n  end tell\n"
            "  return rid as string\nend tell"
        )
        res = _osa(script, timeout=self.TIMEOUT)
        if res.returncode != 0:
            return _err("Reminders", "add",
                        (res.stderr or res.stdout or "add failed").strip())
        return NativeResult(
            ok=True, app="Reminders", operation="add",
            proof={
                "reminder_id": (res.stdout or "").strip(),
                "list_name": list_name, "title": title,
                "created_at_iso": _iso_now(),
            },
        )

    def reminders_list(self, list_name: str = "") -> NativeResult:
        scope = (
            f"reminders of list {_quote(list_name)}"
            if list_name else "reminders"
        )
        script = (
            'tell application "Reminders"\n  set out to {}\n'
            f"  set theRs to {scope}\n"
            "  repeat with r in theRs\n"
            "    set end of out to ((id of r) as string) & \"||\" & "
            "(name of r) & \"||\" & ((completed of r) as string)\n"
            "  end repeat\n"
            "  set AppleScript's text item delimiters to linefeed\n"
            "  return out as string\nend tell"
        )
        res = _osa(script, timeout=self.TIMEOUT)
        if res.returncode != 0:
            return _err("Reminders", "list",
                        (res.stderr or "list failed").strip())
        items = _parse_table(
            res.stdout or "",
            ["reminder_id", "title", "completed?"],
        )
        return NativeResult(
            ok=True, app="Reminders", operation="list",
            proof={"reminders": items, "count": len(items)},
        )

    def reminders_delete(self, reminder_id: str) -> NativeResult:
        if not reminder_id:
            return _err("Reminders", "delete", "reminder_id required")
        script = (
            'tell application "Reminders"\n  try\n'
            "    set victim to (first reminder whose id is "
            + _quote(reminder_id) + ")\n    delete victim\n"
            "    return \"true\"\n  on error\n    return \"false\"\n"
            "  end try\nend tell"
        )
        res = _osa(script, timeout=self.TIMEOUT)
        deleted = "true" in (res.stdout or "").lower()
        return NativeResult(
            ok=deleted, app="Reminders", operation="delete",
            proof={"reminder_id": reminder_id, "deleted": deleted},
        )

    def notes_create(
        self, title: str, body: str, folder: str = "Notes",
    ) -> NativeResult:
        if not title and not body:
            return _err("Notes", "create", "title or body required")
        folder_clause = (
            f"folder {_quote(folder)} of default account"
            if folder else "default folder of default account"
        )
        html = f"<h1>{title or ''}</h1><p>{body or ''}</p>"
        script = (
            'tell application "Notes"\n  launch\n'
            f"  tell {folder_clause}\n"
            "    set newN to make new note with properties {body:"
            + _quote(html) + "}\n"
            "    set nid to id of newN\n"
            "    set nname to name of newN\n  end tell\n"
            '  return (nid as string) & "||" & (nname as string)\nend tell'
        )
        res = _osa(script, timeout=self.TIMEOUT)
        if res.returncode != 0:
            return _err("Notes", "create",
                        (res.stderr or res.stdout or "create failed").strip())
        nid, _, nname = (res.stdout or "").partition("||")
        return NativeResult(
            ok=True, app="Notes", operation="create",
            proof={
                "note_id": nid.strip(), "name": nname.strip(),
                "folder": folder, "created_at_iso": _iso_now(),
            },
        )

    def notes_list(self, folder: str = "") -> NativeResult:
        scope = (
            f"notes of folder {_quote(folder)} of default account"
            if folder else "notes"
        )
        script = (
            'tell application "Notes"\n  set out to {}\n'
            f"  set theNs to {scope}\n"
            "  repeat with n in theNs\n"
            "    set end of out to ((id of n) as string) & \"||\" & "
            "(name of n)\n  end repeat\n"
            "  set AppleScript's text item delimiters to linefeed\n"
            "  return out as string\nend tell"
        )
        res = _osa(script, timeout=self.TIMEOUT)
        if res.returncode != 0:
            return _err("Notes", "list",
                        (res.stderr or "list failed").strip())
        items = _parse_table(res.stdout or "", ["note_id", "name"])
        return NativeResult(
            ok=True, app="Notes", operation="list",
            proof={"notes": items, "count": len(items)},
        )

    def notes_delete(self, note_id: str) -> NativeResult:
        if not note_id:
            return _err("Notes", "delete", "note_id required")
        script = (
            'tell application "Notes"\n  try\n'
            "    set victim to (first note whose id is "
            + _quote(note_id) + ")\n    delete victim\n"
            "    return \"true\"\n  on error\n    return \"false\"\n"
            "  end try\nend tell"
        )
        res = _osa(script, timeout=self.TIMEOUT)
        deleted = "true" in (res.stdout or "").lower()
        return NativeResult(
            ok=deleted, app="Notes", operation="delete",
            proof={"note_id": note_id, "deleted": deleted},
        )

    def finder_reveal(self, path: str) -> NativeResult:
        if not path:
            return _err("Finder", "reveal", "path required")
        target = Path(path).expanduser().resolve()
        if not target.exists():
            return _err("Finder", "reveal", f"path missing: {target}")
        res = subprocess.run(
            ["/usr/bin/open", "-R", str(target)],
            capture_output=True, text=True, timeout=8.0, check=False,
        )
        if res.returncode != 0:
            return _err("Finder", "reveal",
                        (res.stderr or "reveal failed").strip())
        return NativeResult(
            ok=True, app="Finder", operation="reveal",
            proof={"path": str(target), "revealed_at": _iso_now()},
        )

    def finder_search(self, query: str) -> NativeResult:
        if not query:
            return _err("Finder", "search", "query required")
        res = subprocess.run(
            ["/usr/bin/mdfind", query],
            capture_output=True, text=True, timeout=10.0, check=False,
        )
        if res.returncode != 0:
            return _err("Finder", "search",
                        (res.stderr or "mdfind failed").strip())
        paths = [ln for ln in (res.stdout or "").splitlines() if ln.strip()]
        return NativeResult(
            ok=True, app="Finder", operation="search",
            proof={"query": query, "paths": paths[:200], "count": len(paths)},
        )

    def messages_draft(
        self, recipient: str, body: str, send: bool = False,
    ) -> NativeResult:
        if not recipient:
            return _err("Messages", "draft", "recipient required")
        if not body:
            return _err("Messages", "draft", "body required")
        if send:
            script = (
                'tell application "Messages"\n  launch\n'
                "  set targetService to first service whose service type "
                "is iMessage\n"
                "  set targetBuddy to buddy " + _quote(recipient)
                + " of targetService\n"
                "  send " + _quote(body) + " to targetBuddy\n"
                '  return "sent"\nend tell'
            )
            res = _osa(script, timeout=self.TIMEOUT)
            sent = "sent" in (res.stdout or "").lower()
            return NativeResult(
                ok=sent, app="Messages", operation="send",
                proof={"recipient": recipient, "body_len": len(body),
                       "sent_at_iso": _iso_now()},
                error="" if sent else (res.stderr or "send failed").strip(),
            )
        open_res = subprocess.run(
            ["/usr/bin/open", "-a", "Messages", f"sms:{recipient}"],
            capture_output=True, text=True, timeout=8.0, check=False,
        )
        if open_res.returncode != 0:
            return _err("Messages", "draft",
                        (open_res.stderr or "open failed").strip())
        time.sleep(1.0)
        cliclick = shutil.which("cliclick")
        if cliclick:
            res = subprocess.run(
                [cliclick, "-w", "200", "t:" + body],
                capture_output=True, text=True, timeout=15.0, check=False,
            )
        else:
            res = _osa(
                'tell application "System Events" to keystroke '
                + _quote(body), timeout=15.0,
            )
        ok_typed = res.returncode == 0
        return NativeResult(
            ok=ok_typed, app="Messages", operation="draft",
            proof={
                "recipient": recipient, "body_len": len(body),
                "drafted_at_iso": _iso_now(), "sent": False,
            },
            error="" if ok_typed else (res.stderr or "type failed").strip(),
        )


__all__ = ["NativeMacOS", "NativeResult"]
