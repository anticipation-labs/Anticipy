# Anticipy

The proactive assistant: pendant (ears) -> phone app (pipe + brain) -> browser agent (hands).
See PROOF_REPORT.md for what is proven. Proof scripts live in proof/.

Quick start:
  python3.11 -m venv .venv && . .venv/bin/activate
  pip install browser-use playwright fastapi uvicorn httpx opuslib numpy soundfile
  python -m playwright install chromium
  (cd backend && ./pocketbase serve)   # backend on :8090
  python proof/test_brain.py && python proof/test_backend.py && python proof/test_extension.py && python proof/test_end_to_end.py
