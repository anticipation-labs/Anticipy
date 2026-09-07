"""Print only brain lifecycle failure messages from a private Wrangler trace."""
import json
from pathlib import Path
import sys

raw = Path(sys.argv[1]).read_text()
decoder = json.JSONDecoder()
position = 0
events = 0
failures = 0
while position < len(raw):
    start = raw.find("{", position)
    if start < 0:
        break
    try:
        event, end = decoder.raw_decode(raw, start)
    except ValueError:
        position = start + 1
        continue
    position = end
    if not isinstance(event, dict) or "logs" not in event:
        continue
    events += 1
    for log in event.get("logs", []):
        for message in log.get("message", []):
            if isinstance(message, str) and message.startswith("owner worker failed to start · owner="):
                # Drop the owner identifier. Keep only the operational error.
                _, _, error = message.partition(" · Error: ")
                if error:
                    print(json.dumps({"runtime_error": error[:400]}))
                    failures += 1
print(json.dumps({"worker_events_observed": events, "runtime_failures_observed": failures}))
