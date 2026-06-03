"""The web-agent loop (for benchmarking the hands + model on WebVoyager-style
tasks): observe (DOM elements + screenshot) -> model decides -> act -> repeat.
"""
from .webvoyager import WebVoyagerAgent, judge  # noqa: F401
