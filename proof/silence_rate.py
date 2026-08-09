"""How often does she go COMPLETELY SILENT on a real plan? A rate, not a verdict.

Omar, 2026-08-08: "If you told me that a product has a 25% chance of failing,
it's ridiculous."

He is right, and the framing that produced that number was wrong too. I had
called second_scenario_proof "flaky", as though the TEST were unreliable. It is
not. It runs the real hear() against the real production model. A 25% proof
failure IS a 25% product failure, and making the proof best-of-N would have
hidden it rather than fixed it.

WHAT ACTUALLY HAPPENS. Compare a failing run with a passing one on the same
lines and the GOALS ARE IDENTICAL — she understands the plan perfectly either
way:

    failing   ask    addressee=self    Book Earls Brooklyn for Saturday at 1pm...
    passing   ignore addressee=person  Book Earls Brooklyn for Saturday at 1 PM...

The only thing that moves is the one-word addressee label. When it lands on
"self", the self-talk rule swallows every question, no card is ever built, and
he gets nothing at all — no text, no card, no trace. A plan she completely
understood is deleted by a coin flip about who he was talking to.

So this measures the thing he actually cares about: out of N attempts at one
real conversation, how many produce a booking he can approve?

    ANTICIPY_MODEL=google/gemini-2.5-flash python3 proof/silence_rate.py [N]

Runs are SEQUENTIAL on purpose. Parallel batches share an upstream routing
window and fail together, which made 6-of-6 streaks look like solid evidence
when they were nearly one sample.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROOFS = [
    ("earls", os.path.join(HERE, "second_scenario_proof.py")),
    ("dinner", os.path.join(HERE, "dinner_demo_proof.py")),
]


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("SKIP — no OPENROUTER_API_KEY, this needs the real model")
        return 0
    print(f"model={os.environ.get('ANTICIPY_MODEL', '(default)')}   {n} sequential runs each\n")

    worst = 100.0
    for name, path in PROOFS:
        ok = 0
        silent = 0
        for i in range(n):
            r = subprocess.run([sys.executable, path], capture_output=True,
                               text=True, timeout=600)
            out = r.stdout + r.stderr
            passed = r.returncode == 0
            ok += 1 if passed else 0
            # The specific failure that matters: she said nothing at all.
            if not passed and ("silent card" in out or "got 0" in out):
                silent += 1
            print(f"  {name} {i + 1}/{n}: {'ok' if passed else 'FAILED'}"
                  f"{' (total silence)' if not passed and silent else ''}", flush=True)
        pct = 100.0 * ok / n
        worst = min(worst, pct)
        print(f"\n  {name.upper()}: {ok}/{n} produced a booking he could approve "
              f"({pct:.0f}%)   went completely silent: {silent}\n")

    print(f"WORST LANE: {worst:.0f}% of real conversations end in a booking.")
    print("A product that drops one plan in four is not a product. This number "
          "is the one to move.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
