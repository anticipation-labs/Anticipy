"""Marker registration for the conformance suite.

Kept out of the repo-root pytest.ini deliberately: that file sets
`testpaths = tests` for the product suite, while this one is pointed at a
BASE_URL rather than at this checkout, and is meant to be run twice -- once
against PocketBase and once against the Worker -- and the two results diffed.
"""

MARKERS = (
    ("destructive",
     "writes or deletes real rows; ALSO requires ANTICIPY_ALLOW_DESTRUCTIVE=1"),
    ("anonymous",
     "needs no credential at all -- the surface a stranger can reach, and the "
     "only part of the contract that can be baselined without secrets"),
    ("needs_service_token", "requires ANTICIPY_SERVICE_TOKEN"),
    ("needs_internal_key", "requires ANTICIPY_INTERNAL_KEY"),
    ("needs_account", "requires an account token"),
    ("needs_agent", "requires a paired agent id + token"),
    ("slow", "makes several round trips, or spends a rate-limit budget"),
    ("needs_hq", "requires ANTICIPY_INTERNAL_KEY (alias of needs_internal_key)"),
    ("guard_on", "requires the data-API guard to be switched on"),
    ("offline", "needs no network -- reads CONTRACT.md only"),
)


def pytest_configure(config):
    for name, description in MARKERS:
        config.addinivalue_line("markers", "%s: %s" % (name, description))
