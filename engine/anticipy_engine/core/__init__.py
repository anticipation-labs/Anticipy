"""The control core — the proactive engine, memory, hands, and receipts.

The bus + frozen worker contract let the same product path run with deterministic
mock hands in tests and live workers in production. Real memory is always wired;
API/browser/text/call workers are mode-gated so tests stay free and live runs are
explicit.
"""
