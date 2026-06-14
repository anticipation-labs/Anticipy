"""Unit test: the onboarding profile builder's ASSEMBLY logic, against a fake
browse_read seam (no live browser in CI).

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_onboarding_profile.py

Covers:
  - structured profile assembly from multiple sources (name/role/org/location +
    key_facts each with source + trust grade)
  - the trust model: coarse whole-page reads -> needs_cross_check=False; fine
    field pulls -> low confidence + needs_cross_check=True (the browser-arm
    reliability finding, carried through)
  - honesty: a failed read becomes a BLOCKER, never a faked fact; a 'NOT FOUND'
    field is dropped (no invented values); success/result mirror the read
  - per-fact provenance (source_url) is preserved
  - the reader seam is injectable so no live browser is touched
"""
from dataclasses import dataclass, field
from typing import List, Optional

from anticipy_engine.onboarding.profile_builder import (
    ProfileBuilder,
    build_profile,
    ProfileFact,
)


@dataclass
class FakeResult:
    """Duck-typed stand-in for hands.browser_use_link.BrowseReadResult."""

    success: bool
    result: Optional[str]
    url: Optional[str]
    steps: int = 1
    structured: bool = False
    needs_cross_check: bool = True
    trust: str = "coarse"
    error: Optional[str] = None


class FakeReader:
    """A scripted browse_read: returns canned answers keyed by (url, structured,
    field-keyword), and records every call so we can assert read-only/no-extra
    behavior. NEVER touches a network or a browser.
    """

    def __init__(self, script):
        self._script = script  # callable(task, url, structured) -> FakeResult
        self.calls: List[dict] = []

    def __call__(self, task, *, url=None, structured=False, max_steps=10, timeout_s=180):
        self.calls.append(
            {"task": task, "url": url, "structured": structured, "max_steps": max_steps}
        )
        return self._script(task, url, structured)


# --- a realistic two-source script: a Wikipedia-style bio + a company About page.

WIKI = "https://en.wikipedia.org/wiki/Example_Person"
COMPANY = "https://acme.example/about"


def script(task, url, structured):
    t = task.lower()
    if not structured:
        # coarse overview reads
        if url == WIKI:
            return FakeResult(
                success=True,
                result="Example Person is an engineer and the founder of Acme Corp, based in Austin, Texas.",
                url=url,
                structured=False,
                trust="coarse",
            )
        if url == COMPANY:
            return FakeResult(
                success=True,
                result="Acme Corp is a robotics company founded by Example Person, headquartered in Austin.",
                url=url,
                structured=False,
                trust="coarse",
            )
    else:
        # fine field pulls
        if "role" in t:
            return FakeResult(success=True, result="Founder and engineer", url=url, structured=True, trust="fine")
        if "organization" in t or "company" in t:
            return FakeResult(success=True, result="Acme Corp", url=url, structured=True, trust="fine")
        if "location" in t:
            # company page doesn't state a person-location explicitly -> NOT FOUND
            if url == COMPANY:
                return FakeResult(success=True, result="NOT FOUND", url=url, structured=True, trust="fine")
            return FakeResult(success=True, result="Austin, Texas", url=url, structured=True, trust="fine")
    return FakeResult(success=False, result=None, url=url, error="unscripted")


def test_happy_assembly():
    reader = FakeReader(script)
    prof = build_profile("Example Person", [WIKI, {"url": COMPANY, "kind": "company"}], browse_reader=reader)

    # top-level convenience fields hoisted from best facts
    assert prof.name == "Example Person"
    assert prof.role == "Founder and engineer", prof.role
    assert prof.org == "Acme Corp", prof.org
    assert prof.location == "Austin, Texas", prof.location

    # both sources read ok, no blockers
    assert len(prof.sources) == 2
    assert all(s.read_ok for s in prof.sources), prof.sources
    assert prof.blockers == [], prof.blockers

    # every fact carries a source url
    assert prof.key_facts, "expected facts"
    for f in prof.key_facts:
        assert f.source_url, f
        assert f.field and f.value

    # trust model: coarse overview facts are not flagged; fine pulls are
    coarse = [f for f in prof.key_facts if f.trust == "coarse"]
    fine = [f for f in prof.key_facts if f.trust == "fine"]
    assert coarse and fine
    assert all((not f.needs_cross_check) and f.confidence == "medium" for f in coarse), coarse
    assert all(f.needs_cross_check and f.confidence == "low" for f in fine), fine
    assert prof.needs_cross_check_count == len(fine)

    # an overview fact exists per source, with the right provenance
    overviews = [f for f in prof.key_facts if f.field == "overview"]
    assert {o.source_url for o in overviews} == {WIKI, COMPANY}

    # NOT FOUND on the company page's location pull was DROPPED (no invented fact):
    loc_facts = [f for f in prof.key_facts if f.field == "location" and f.trust == "fine"]
    assert all(f.source_url == WIKI for f in loc_facts), loc_facts
    assert all(f.value != "NOT FOUND" for f in prof.key_facts)

    # json round-trips and reports honest summary counts
    d = prof.as_dict()
    assert d["summary"]["sources_read_ok"] == 2
    assert d["summary"]["needs_cross_check"] == prof.needs_cross_check_count
    import json
    json.loads(prof.to_json())  # serializable

    # reader was used read-only: a coarse + 3 fine reads per source = 8 calls,
    # all going through the injected fake (no live browser).
    assert len(reader.calls) == 2 * (1 + 3), reader.calls


def test_failed_read_is_a_blocker_not_a_fake():
    # A source whose overview read fails AND whose field pulls fail must yield a
    # blocker and contribute NO facts — honesty by construction.
    def failing_script(task, url, structured):
        return FakeResult(success=False, result=None, url=url, error="bridge timed out")

    reader = FakeReader(failing_script)
    prof = build_profile("Ghost", ["https://nope.example"], browse_reader=reader)
    assert prof.key_facts == [], prof.key_facts
    assert prof.role is None and prof.org is None and prof.location is None
    assert len(prof.blockers) == 1 and "could not read" in prof.blockers[0]
    assert prof.as_dict()["summary"]["sources_read_ok"] == 0


def test_partial_read_overview_ok_field_fails():
    # Overview reads, but a field pull returns success-with-empty -> that field is
    # absent (not invented), while the coarse overview fact still lands.
    def partial(task, url, structured):
        if not structured:
            return FakeResult(success=True, result="Some public figure overview.", url=url, trust="coarse")
        return FakeResult(success=True, result="", url=url, structured=True, trust="fine")  # empty => not found

    reader = FakeReader(partial)
    prof = build_profile("Partial Person", ["https://p.example"], browse_reader=reader)
    assert any(f.field == "overview" for f in prof.key_facts)
    assert not any(f.trust == "fine" for f in prof.key_facts), "empty pulls must be dropped"
    assert prof.role is None  # no fine role fact -> top-level stays empty


def test_builder_defaults_to_real_arm_but_does_not_call_it_on_import():
    # Constructing a builder without a reader must NOT launch anything; the real
    # arm is only bound, not invoked.
    b = ProfileBuilder()  # binds _real_browse_read
    assert b._read is not None
    # and an injected reader overrides it
    sentinel = object()
    b2 = ProfileBuilder(browse_reader=lambda *a, **k: sentinel)
    assert b2._read is not None and b2._read is not b._read


def main():
    test_happy_assembly()
    test_failed_read_is_a_blocker_not_a_fake()
    test_partial_read_overview_ok_field_fails()
    test_builder_defaults_to_real_arm_but_does_not_call_it_on_import()
    print(
        "PASS onboarding profile-builder (unit): structured assembly from multiple "
        "sources; coarse=trusted / fine=needs_cross_check trust grading; failed "
        "read -> blocker not fake; NOT-FOUND/empty pulls dropped (no invented "
        "facts); per-fact provenance preserved; injectable reader (no live browser)"
    )


if __name__ == "__main__":
    main()
