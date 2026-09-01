"""One tap must not cost two sequential round-trips of spinner.

`AnticipySession.write` is the single path every phone-side write takes:
confirm, decline, stop, answer. It held `inFlight` (which is what draws the
spinner on the card) inside a `defer`, and called `await refresh()` before
returning — so the sequence for tapping "Yes, go ahead" was:

    write the job  ->  fetch reachability + jobs + events + transcript  ->  UI moves

Two network round-trips, serialized, before anything on screen changed. On
cellular that is seconds of dead time on the most-used control in the product,
and it is the whole of what "it doesn't feel responsive" meant.

The honesty rule it was protecting is NOT relaxed by the fix: nothing is
claimed until the server accepts. What changed is that the already-accepted
result shows at once and the reconciling read happens behind it.
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel):
    with open(os.path.join(ROOT, rel)) as fh:
        return fh.read()


def _write_body():
    src = _read("app/ios/Anticipy/AnticipyApp.swift")
    start = src.index("private func write(id: String,")
    end = src.index("private func write(_ job: AgentJob,", start)
    return src[start:end]


def test_the_spinner_stops_before_the_reconciling_fetch():
    body = _write_body()
    assert "inFlight.remove(id)" in body
    # The refresh must be detached, never awaited on the path that returns.
    assert "Task { await refresh() }" in body, "refresh is not detached"
    assert not re.search(r"^\s*await refresh\(\)", body, re.M), \
        "a blocking refresh is back inside the write path"


def test_success_is_still_never_claimed_before_the_server_accepts():
    """The property the old ordering existed to guarantee. If this ever
    inverts, the product lies about having done something."""
    body = _write_body()
    accepted = body.index("try await body()")
    # Search FROM the accept point. `defer { inFlight.remove(id) }` legitimately
    # appears above it - the defer is the safety net for the throwing path, and
    # matching it here was a bug in this test, not in the code.
    for after in ("Haptics.success()", "inFlight.remove(id)", "confirmedStatus[id]"):
        assert body.index(after, accepted) > accepted, \
            f"{after} never runs after the server replies"
    # Nothing may be claimed above the accept point at all.
    assert "Haptics.success()" not in body[:accepted]
    assert "confirmedStatus[id]" not in body[:accepted]
    # And a failure must still be recorded as a failure.
    assert "failedWrites.insert(id)" in body and "Haptics.warning()" in body


def test_a_confirmed_status_is_held_only_until_the_server_agrees():
    """Holding it forever would pin a stale card; not holding it at all lets a
    pre-write row snap the card back to "waiting for your OK" for one poll."""
    src = _read("app/ios/Anticipy/AnticipyApp.swift")
    assert "guard let held = confirmedStatus[job.id]" in src, \
        "the fetched job is never reconciled with its held accepted status"
    assert "ActionWritePolicy.reconcile(" in src, \
        "the overlay no longer distinguishes stale, advanced, and unknown rows"
    assert "confirmedStatus.removeValue(forKey: job.id)" in src
    assert "job.withStatus(held.expected)" in src, \
        "the held status is not applied to the one verified-stale feed row"


def test_every_status_changing_write_declares_what_it_expects():
    """A write that changes status without saying so gets no overlay, and its
    card snaps back. `answer` pushing an app_reply event is the deliberate
    exception: it changes no job status."""
    src = _read("app/ios/Anticipy/AnticipyApp.swift")
    for fn, expected in (("stopRunning", "cancelled"), ("decline", "cancelled")):
        hit = re.search(r"func " + fn + r"\(.*?\n\s+await write\(job, expected: \"(\w+)\"\)",
                        src, re.S)
        assert hit, f"{fn} does not declare an expected status"
        assert hit.group(1) == expected, f"{fn} expects {hit.group(1)}, not {expected}"
    assert 'write(job, expected: "queued")' in src, "approval declares no expected status"


def test_the_job_value_stayed_immutable():
    """The overlay must not have been bought by making AgentJob mutable — a
    `var status` would let any view invent a state."""
    src = _read("app/ios/Anticipy/Backend/AnticipyBackend.swift")
    struct = src[src.index("struct AgentJob"):src.index("struct BrowserAgent")]
    # Strip prose first. The doc comment on `withStatus` explains why a
    # `var status` would be wrong, and scanning it caught the explanation
    # instead of the declaration - the same trap the theme contract hit.
    code = "\n".join(l for l in struct.splitlines()
                     if not l.strip().startswith(("///", "//")))
    assert "var status" not in code, "AgentJob.status became mutable"
    assert "func withStatus(" in struct
