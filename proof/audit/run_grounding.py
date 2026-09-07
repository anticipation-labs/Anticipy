"""Real-model contrasts for factual fidelity, including the recorded failures."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import quote

from brain import llm
from brain.grounding import grounding_verdict

ROOT = Path(__file__).resolve().parents[2]
NOW = "Monday, September 7, 2026, 04:00 America/Vancouver; tomorrow is September 8."
CASES = [
    ("invented_person", "meeting with Dr. Evans, Monday 5:15 PM", "at 5:15, so I have a hard stop", "unsupported"),
    ("invented_party_size", "Book lunch for two at the harbor cafe tomorrow", "Let's go to the harbor cafe for lunch tomorrow", "unsupported"),
    ("relative_date", "Schedule Supplier review on September 8 at 15:00", "Anticipy, put the supplier review on my calendar tomorrow at three in the afternoon", "supported"),
    ("unknown_voice_is_not_contradiction", "schedule Supplier review on your calendar tomorrow at 3 PM", "Anticipy, put the supplier review on my calendar tomorrow at three in the afternoon", "supported"),
    ("completed_is_not_obligation", "Arrange another plumber visit and pay the invoice", "The plumber already fixed the leak; I paid the invoice this morning", "unsupported"),
    ("remaining_part_only", "Prepare payment of the plumber's invoice", "The plumber fixed the leak but I still need to pay the invoice", "supported"),
    ("digits_are_same_fact", "Prepare a reservation for 7 people", "Please prepare a reservation for seven people", "supported"),
    ("invented_completion", "I sent the agenda to Nora", "Please draft the agenda for Nora. Do not send it yet", "unsupported"),
    ("faithful_draft", "Prepare an agenda for Nora's review", "Please draft the agenda for Nora. Do not send it yet", "supported"),
    ("negated_name", "Book travel to Bergen", "We are not going to Bergen. We're staying home", "unsupported"),
    ("quoted_command", "Delete the shared files", 'The training slide says "delete the shared files" as an example of a dangerous request', "unsupported"),
    ("date_correction", "Schedule the interview September 9 from 10 until 11", "Make the interview September ninth, ten until eleven", "supported"),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    state = ROOT / "work/audit"
    output = state / (args.label + ".json")
    if output.exists():
        raise SystemExit("Use a fresh evidence label")
    llm.OPENROUTER_URL = "http://127.0.0.1:8790/api/v1/chat/completions?audit_run=" + quote(args.label)
    model = llm.LLM(api_key=(state / "gateway-token").read_text().strip(), model="google/gemini-3.1-pro-preview")
    model.gemini_api_key = None
    rows = []
    for name, content, heard, expected in CASES:
        evidence = {"heard": heard, "conversation": [], "current_local_time": NOW,
                    "measured_speaker": "unknown"}
        observed = grounding_verdict(model, content, evidence)
        rows.append(dict(case=name, content=content, evidence=evidence, expected=expected,
                         observed=observed, passed=observed == expected))
        output.write_text(json.dumps({"model": model.model,
            "grounding_source_sha256": hashlib.sha256((ROOT / "brain/grounding.py").read_bytes()).hexdigest(),
            "results": rows}, indent=2))
        print(name, observed, "PASS" if rows[-1]["passed"] else "FAIL", flush=True)
    raise SystemExit(0 if all(row["passed"] for row in rows) else 1)


if __name__ == "__main__":
    main()
