#!/usr/bin/env python3
"""NO VENDOR EARS — LOCAL-FIRST rule 1, enforced instead of asserted.

    "RAW AUDIO NEVER LEAVES A DEVICE. Not to Deepgram, not to anyone. If a
     capability needs better ears, find a better local model."
        — design/LOCAL-FIRST.md, rule 1, first in the list

That law was written, and then for months the product streamed the pendant's
raw Opus frames to wss://api.deepgram.com/v1/listen, with the server minting
60-second credentials to do it. LOCAL-FIRST.md's own scoreboard said "phone does
ALL processing... law-abiding by design" while the shipped implementation was
cloud. A law with nothing checking it is a preference.

WHY A GATE AND NOT A COMMENT: this is the same shape as the HANDS 2 card, which
was declined on 2026-08-24 for putting a vendor in the trust path — while an
already-shipped instance of exactly that pattern ran in production, unremarked,
because nothing looked. The decision not to build the new one was recorded; the
existing one was not checked.

LAW 1 NOTE: this gate greps source for vendor hostnames and credential names.
That is pattern-matching, and it is legal here on two counts — it is a
deterministic gate, and it decides nothing about what any human's words MEAN. It
reads code, not speech.

WHAT IT CANNOT SEE, said plainly rather than left for someone to discover: a
vendor reached through a hostname it does not know, audio forwarded by a service
this repo does not contain, or a key passed in at runtime under another name.
The registry below is the honest limit of it.

AND ONE BLIND SPOT WORTH MORE THAN THE REST, found by the agent that closed the
iOS half on 2026-08-25 and recorded here rather than left as a surprise. This
gate greps for the VENDOR'S NAME. The sentences that actually rendered to the
owner never used it:

    "Pendant · starting transcription"
    "I'm opening its secure transcription stream"

Both describe audio leaving the phone. Neither contains a hostname or a
credential, so this gate was green on the exact copy a person would have read.
The two strings that DID name the vendor sat in branches the UI rarely reached.

That is not fixable by adding those phrases to a list — the next wording would
evade it, and a list of sentences deciding what a promise MEANS is the Law 1
violation this file exists downstream of. The honest containment is a human
reading the user-facing copy whenever this lane changes, and knowing that a
green result here means "no code path calls a vendor", never "the product does
not tell the owner it does".
"""
from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import _env  # noqa: E402  sibling module; gates are run as scripts
_ENV_LOADED = _env.load_and_announce(ROOT)

# Vendors that take AUDIO. Named because they are the ones a "better ears"
# argument reaches for; the law names the first one itself.
AUDIO_VENDORS = ("deepgram", "assemblyai", "speechmatics", "rev.ai",
                 "elevenlabs.io/v1/speech-to-text", "openai.com/v1/audio")

# Credential names that only exist to reach one of the above.
VENDOR_KEYS = ("DEEPGRAM_API_KEY", "ASSEMBLYAI_API_KEY", "SPEECHMATICS_API_KEY")

# Where shipped code lives. Tests, research and docs may DISCUSS a vendor —
# this whole gate is documentation of one — so they are not scanned.
SHIPPED = ("backend/pb_hooks", "backend/pb_migrations", "brain",
           "app/ios/Anticipy", "extension")
SKIP_DIRS = {"node_modules", ".git", "__pycache__", "tests", "test"}
# .plist and .html are here because of a miss on 2026-08-26. The gate was
# GREEN while app/ios/Anticipy/Info.plist still told the owner, in the words iOS
# shows at the permission prompt, that "pendant audio is sent to Deepgram for
# live transcription" — five hours after that path was deleted. A false privacy
# promise is worse than the practice it describes: it tells somebody their audio
# goes somewhere it does not, and says nothing about wherever it actually went.
# The gate only read code, and the sentence a person actually reads is not code.
EXTS = (".py", ".js", ".mjs", ".swift", ".plist", ".html")


def _is_comment(line: str, ext: str) -> bool:
    s = line.strip()
    if ext == ".py":
        return s.startswith("#")
    return s.startswith("//") or s.startswith("*") or s.startswith("/*")


def scan(root: str = ROOT) -> list:
    """Live references to an audio vendor in shipped code. Comments are not
    references — this file's own explanation names Deepgram nine times, and a
    gate that could not survive being described would be unusable."""
    hits = []
    for folder in SHIPPED:
        base = os.path.join(root, folder)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for name in filenames:
                ext = os.path.splitext(name)[1]
                if ext not in EXTS:
                    continue
                path = os.path.join(dirpath, name)
                try:
                    lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
                except OSError:
                    continue
                for i, line in enumerate(lines, 1):
                    if _is_comment(line, ext):
                        continue
                    low = line.lower()
                    for v in AUDIO_VENDORS:
                        if v in low:
                            hits.append((os.path.relpath(path, root), i, v, line.strip()[:100]))
                    for k in VENDOR_KEYS:
                        if k in line:
                            hits.append((os.path.relpath(path, root), i, k, line.strip()[:100]))
    return hits


def main() -> int:
    print()
    print("  NO VENDOR EARS   (LOCAL-FIRST rule 1)")
    print("  " + "-" * 62)
    hits = scan()
    if not hits:
        print("  [1] PASS  NO SHIPPED CODE SENDS AUDIO TO A VENDOR")
        print("        no live reference to an audio vendor or its credential in")
        print("        backend/pb_hooks, backend/pb_migrations, brain, app/ios/Anticipy, extension")
        print("  " + "-" * 62)
        print("  What this cannot see: a vendor whose hostname is not in the")
        print("  registry, audio forwarded by a service outside this repo, or a")
        print("  key supplied at runtime under another name.")
        print("  AND: copy that promises the owner their audio travels WITHOUT")
        print("  naming the vendor — \"starting transcription\", \"opening its")
        print("  secure transcription stream\". Those rendered while this gate")
        print("  was green. Green here means no code path calls a vendor. It")
        print("  never means the product stopped telling the owner it does.")
        return 0

    print("  [1] FAIL  SHIPPED CODE REACHES AN AUDIO VENDOR")
    for path, line_no, what, text in hits:
        print(f"        {path}:{line_no}  ({what})")
        print(f"            {text}")
    print()
    print("        LOCAL-FIRST.md rule 1: \"RAW AUDIO NEVER LEAVES A DEVICE.")
    print("        Not to Deepgram, not to anyone. If a capability needs better")
    print("        ears, find a better local model.\"")
    print("  " + "-" * 62)
    print("  A LAW WITH NOTHING CHECKING IT IS A PREFERENCE")
    return 1


if __name__ == "__main__":
    sys.exit(main())
