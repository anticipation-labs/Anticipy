"""
macOS UI helpers for the verifier.

Provides:
- click_menu_bar_item(app_name): clicks the tray icon of an app via System Events
- launch_app(name): launches an app and waits for it to be running
- quit_app(name): clean quit
- get_window_screenshot_region(): figures out where the popover anchors
- type_text(): types into the focused field
- press_keystroke(): sends a key combo

These rely on Accessibility permission being granted to the calling shell.
Verify via: tools/check_permissions.sh
"""

from __future__ import annotations

import subprocess
import time


def _osa(script: str, timeout: int = 30) -> tuple[int, str]:
    p = subprocess.run(
        ["osascript", "-e", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    return p.returncode, (p.stdout or b"").decode("utf-8", errors="replace")


def launch_app(name: str) -> bool:
    """Launch an app by name (without .app). Returns True when 'osascript get name' confirms running."""
    subprocess.run(["open", "-a", name], check=False, timeout=10)
    for _ in range(20):
        rc, out = _osa(f'tell application "System Events" to (name of processes) contains "{name}"')
        if rc == 0 and "true" in out.lower():
            return True
        time.sleep(0.5)
    return False


def quit_app(name: str) -> bool:
    rc, _ = _osa(f'quit app "{name}"')
    if rc != 0:
        # Force
        subprocess.run(["pkill", "-x", name], check=False, timeout=5)
    for _ in range(20):
        rc, out = _osa(f'tell application "System Events" to (name of processes) contains "{name}"')
        if rc == 0 and "false" in out.lower():
            return True
        time.sleep(0.5)
    return False


def click_menu_bar_item(app_name: str) -> tuple[bool, str]:
    """
    Click the menu bar (tray) icon of an LSUIElement app via System Events.
    For most Tauri MenuBarExtra-style apps this works because the tray icon is
    represented as menu bar item 1 of menu bar 2 (the status bar).
    """
    script = f'''
    tell application "System Events"
        tell process "{app_name}"
            try
                click menu bar item 1 of menu bar 2
                return "clicked"
            on error errMsg
                return "error: " & errMsg
            end try
        end tell
    end tell
    '''
    rc, out = _osa(script)
    success = rc == 0 and "clicked" in out
    return success, out


def click_at(x: int, y: int) -> bool:
    """Click at absolute screen coordinates via System Events. Requires Accessibility."""
    script = f'''
    tell application "System Events"
        click at {{{x}, {y}}}
    end tell
    '''
    rc, _ = _osa(script)
    return rc == 0


def press_keystroke(key: str, modifiers: list[str] | None = None) -> bool:
    """
    Send a key combo. modifiers can include: "command", "option", "shift", "control".
    Example: press_keystroke("q", ["command"]) sends Cmd-Q.
    """
    mod_str = ""
    if modifiers:
        mod_list = ", ".join(f"{m} down" for m in modifiers)
        mod_str = f" using {{{mod_list}}}"
    script = f'tell application "System Events" to keystroke "{key}"{mod_str}'
    rc, _ = _osa(script)
    return rc == 0


def type_text(text: str) -> bool:
    """Type a string into the focused field."""
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    script = f'tell application "System Events" to keystroke "{escaped}"'
    rc, _ = _osa(script)
    return rc == 0


def get_app_window_bounds(app_name: str, window_index: int = 1) -> tuple[int, int, int, int] | None:
    """Return (x, y, w, h) of an app's window. None if not found."""
    script = f'''
    tell application "System Events"
        try
            tell process "{app_name}"
                set p to position of window {window_index}
                set s to size of window {window_index}
                return (item 1 of p as string) & "," & (item 2 of p as string) & "," & (item 1 of s as string) & "," & (item 2 of s as string)
            end tell
        on error
            return ""
        end try
    end tell
    '''
    rc, out = _osa(script)
    if rc != 0 or not out.strip():
        return None
    parts = out.strip().split(",")
    if len(parts) != 4:
        return None
    try:
        return tuple(int(p) for p in parts)  # type: ignore
    except ValueError:
        return None


def menu_bar_region() -> tuple[int, int, int, int]:
    """Top-right corner of the screen where tray icons live. Used for screencap region."""
    # Get main display size
    rc, out = _osa('tell application "Finder" to get bounds of window of desktop')
    # out is like "0, 0, 1920, 1080"
    parts = (out.strip() or "0,0,1920,1080").split(",")
    try:
        w = int(parts[2].strip())
    except (ValueError, IndexError):
        w = 1920
    # Capture the rightmost 400px of the menu bar (top 30px)
    return (w - 400, 0, 400, 30)
