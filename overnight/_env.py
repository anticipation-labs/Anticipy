"""Give the gates the credentials that were sitting next to them all along.

This module exists because of a specific wasted session. `done_gate` reported

    [3] FAIL  SHE JUDGES RIGHT
          no model key, so her judgement cannot be measured

and, obeying its own instruction to work only the first failing leg, sent
agent after agent at leg 3. `OPENROUTER_API_KEY` was in `.env.local`, in the
same directory as the gate, the whole time. With the file loaded, legs 3 and 4
pass and the first failing leg is 6 — the finish line, which no amount of code
can close.

A scoreboard that names the wrong leg is worse than no scoreboard at all,
because CLAUDE.md instructs the reader to believe it. "A leg that cannot be
tested does not pass" is the right law; it was being applied to a leg that
could be tested.

Two rules this module will not bend:

**The environment wins over the file.** A key already exported is an operator
being deliberate — a scratch key in CI, a staging backend. If the file
overrode it, a run you believed was pointed at a test backend would silently
be pointed at production and report green. Explicit beats ambient, always.

**It announces itself, by name and never by value.** A gate that quietly picks
up production credentials is indistinguishable, in its output, from one that
found nothing — until it authenticates against prod. Callers print what was
loaded so the reader can see which credentials are in play. Values never
appear in the return, because gate logs get pasted into issues.
"""
from __future__ import annotations

import os
import sys
from typing import List

FILENAME = ".env.local"


def parse(text: str) -> "list[tuple[str, str]]":
    """Read dotenv text into ordered pairs. No regex decides meaning here —
    this is a file format, not language."""
    pairs: list[tuple[str, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        # Split on the FIRST '=' only. Base64 secrets and query strings both
        # carry '=' inside the value; splitting on every one of them truncates
        # the token, and the gate then fails as "backend unreachable", which
        # sends the reader to debug a network that was never the problem.
        name, sep, value = line.partition("=")
        if not sep:
            continue
        name = name.strip()
        if not name:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        pairs.append((name, value))
    return pairs


def load(root: str | os.PathLike = ".") -> List[str]:
    """Load `<root>/.env.local` into os.environ without overriding it.

    Returns the NAMES that were newly set, in file order — never the values.
    An absent file is not an error: a tree with no `.env.local` is the normal
    CI case, and the gates must still run and report "cannot be tested"
    honestly rather than crash.
    """
    path = os.path.join(os.fspath(root), FILENAME)
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return []

    taken: List[str] = []
    for name, value in parse(text):
        if name in os.environ:
            # Already set. The operator meant it. Say nothing, change nothing.
            continue
        os.environ[name] = value
        taken.append(name)
    return taken


def announce(loaded: List[str], root: str | os.PathLike = ".") -> str:
    """One line a gate can print. Names only.

    Silence when nothing loaded, so a tree without the file reads exactly as
    it did before this module existed.
    """
    if not loaded:
        return ""
    where = os.path.join(os.fspath(root), FILENAME)
    return f"  (loaded {len(loaded)} value(s) from {where}: {', '.join(loaded)})"


def load_and_announce(root: str | os.PathLike = ".", stream=None) -> List[str]:
    """What the gates call. Loading and announcing are one act, deliberately.

    If a gate could load credentials without printing that it had, then the
    two cases this module exists to separate — "no key, cannot be tested" and
    "your production key, silently in play" — would look identical in the
    output. Keeping them in one function means a gate cannot pick up the
    former without the reader seeing the latter.
    """
    loaded = load(root)
    line = announce(loaded, root)
    if line:
        # stderr, not stdout. A gate's stdout is its verdict, and some of
        # these gates emit JSON that something else parses; a diagnostic
        # line prepended to it would turn "which credentials are in play"
        # into a parse error. How the run was configured belongs on the
        # error channel with the rest of the run's commentary.
        print(line, file=stream if stream is not None else sys.stderr)
    return loaded
