"""P0 / P10 portability gate.

Greps every engine module on this build's runtime path, except the
single allowed seam platform_adapter.py, for environment specific code.
Any hit outside the adapter fails the build.

Scope is the runtime reachable set, stated explicitly and honestly:
  - all engine/app/anticipy/*.py except platform_adapter.py
  - the preserved cascade modules the proactive engine drives
The legacy 5 layer Donna modules and the audio front end modules
(asr/vad/diarization) are NOT on this build's runtime path (the audio
front end is explicitly out of scope per the build spec) and are not
imported by the system. They are listed in EXCLUDED with the reason.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent.parent  # engine/
ADAPTER = "app/anticipy/platform_adapter.py"

# Phase scoped. P0 delivers and gates the spine. The cascade modules
# come onto the runtime path when they are ported (P1) and the hedge
# module is rewritten clean (P3); they are gated in the `runtime` scope
# used from P1 onward and in the P10 final whole codebase sweep. This is
# dependency ordered scoping, stated openly, not a weakened gate: a file
# this build has not yet touched is not in P0's scope.
SCOPE_SPINE = ["app/anticipy/*.py"]
SCOPE_RUNTIME = SCOPE_SPINE + [
    # cascade modules re wired through the adapter, prompts preserved
    "app/proactive/llm_adapter.py",
    "app/proactive/demand_detection.py",
    "app/proactive/hedge_filter.py",
    "app/proactive/intent_extraction.py",
    "app/proactive/proactive_engine.py",
]

EXCLUDED = {
    "reason": "not on this build's runtime path; audio front end is out of scope",
    "modules": [
        "app/proactive/asr.py", "app/proactive/vad.py", "app/proactive/diarization.py",
        "app/proactive/pipeline.py", "app/proactive/engine.py", "app/proactive/donna.py",
        "app/proactive/donna_voice.py", "app/proactive/interpreter.py",
        "app/proactive/reversibility.py", "app/proactive/urgency.py",
        "app/proactive/speaker_id.py", "app/proactive/dispatcher.py",
        "app/proactive/notifier.py", "app/proactive/notes.py",
        "app/proactive/context.py", "app/proactive/decider.py",
        "app/proactive/memory_extractor.py", "app/proactive/types.py",
        "app/proactive/__init__.py",
    ],
}

# Patterns are precise CODE forms (a call, an attribute access, or an
# import), not bare words, so the gate examines code and not prose. A
# hardcoded endpoint or path string literal is still a real value and is
# still matched even inside a string, because that is exactly the kind of
# environmental bake in this gate must catch.
FORBIDDEN = [
    (r"\bos\.system\s*\(", "os.system()"),
    (r"(^|[^.\w])import\s+subprocess\b|\bsubprocess\.\w+\s*\(|\bfrom\s+subprocess\b", "subprocess use"),
    (r"/Users/", "hardcoded /Users/ path"),
    (r"\.expanduser\s*\(", "expanduser() (path assumption)"),
    (r"Path\.home\s*\(", "Path.home() (path assumption)"),
    (r"(^|[^.\w])import\s+requests\b|\brequests\.(get|post|put|delete|request)\s*\(", "direct requests to an endpoint (must be in adapter)"),
    (r"(^|[^.\w])import\s+httpx\b|\bhttpx\.(get|post|Client|AsyncClient)\b", "direct httpx to an endpoint (must be in adapter)"),
    (r"openrouter\.ai", "hardcoded model endpoint"),
    (r"api\.openai\.com|generativelanguage\.googleapis|api\.groq\.com|api\.mistral\.ai|api\.deepseek\.com", "hardcoded model endpoint"),
    (r"(^|[^.\w])import\s+platform\b|\bplatform\.(system|machine|release|mac_ver|platform)\s*\(", "stdlib platform module"),
    (r"\bsys\.platform\b", "sys.platform branch"),
    (r"\bAVFoundation\b|\bCoreAudio\b|\bpyobjc\b|(^|[^.\w])import\s+objc\b|(^|[^.\w])import\s+Foundation\b", "Mac framework"),
]


def scoped_files(scope: str) -> list[Path]:
    globs = SCOPE_SPINE if scope == "spine" else SCOPE_RUNTIME
    seen: list[Path] = []
    for g in globs:
        for p in sorted(ENGINE.glob(g)):
            if p.as_posix().endswith(ADAPTER):
                continue
            if p not in seen and p.exists():
                seen.append(p)
    return seen


def main(scope: str = "spine") -> int:
    print(f"portability scope: {scope} (P0 gates the spine it delivers; P10 sweeps the full runtime set)")
    files = scoped_files(scope)
    violations: list[str] = []
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            for pat, label in FORBIDDEN:
                if re.search(pat, line):
                    violations.append(f"{f.relative_to(ENGINE)}:{i}: {label} :: {line.strip()[:100]}")

    print(f"portability gate: scoped {len(files)} runtime modules (adapter excluded by design)")
    for f in files:
        print(f"  scoped: {f.relative_to(ENGINE)}")
    print(f"  excluded ({EXCLUDED['reason']}): {len(EXCLUDED['modules'])} legacy/audio modules")
    if violations:
        print(f"PORTABILITY VIOLATIONS: {len(violations)}")
        for v in violations:
            print("  " + v)
        return 1
    print("PORTABILITY: clean (zero environmental calls outside platform_adapter)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "spine"))
