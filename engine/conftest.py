"""Project-wide pytest configuration.

Registers custom markers so they're recognized without warnings.
"""

from __future__ import annotations


def pytest_configure(config):  # type: ignore[no-untyped-def]
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "real_network: tests that hit real external services. "
        "Skipped by default; run with `pytest -m real_network`.",
    )
