"""Profile builder — assemble a structured, trust-graded profile of a person or
entity from a handful of PUBLIC source URLs, by reading each with the browser arm.

This is the first real slice of "Anticipy scrapes everything about you and builds
your profile." It is deliberately narrow and honest:

  given  : a subject name + a few PUBLIC source URLs (Wikipedia, a company About
           page, a public bio, ...), optionally typed (biography / company / ...)
  does   : reads each page READ-ONLY through hands.browser_use_link.browse_read —
           once COARSE (a whole-page overview, the higher-trust tier) and once
           per requested FINE field (role, org, location, ... — the lower-trust,
           must-cross-check tier)
  yields : a Profile: name + role + org + location + a list of key facts, where
           EVERY fact carries (value, source_url, confidence, needs_cross_check).

Trust model (carried straight from the browser-arm reliability finding in
hands/browser_use_link.py):
  - COARSE facts  — derived from a whole-page summary read — are trusted a tier
    higher: confidence "medium", needs_cross_check=False.
  - FINE facts    — specific field pulls (structured=True reads) — are the actor
    quoting one detail off a live page; they are LOW trust:
    confidence "low", needs_cross_check=True. A second independent read should
    confirm them before they are treated as ground truth.
  - A fact the page did not yield is simply absent — we never invent one, and a
    failed/blocked read is recorded as a blocker on the source, not faked.

Honesty by construction: the builder claims no fact a read did not return, mirrors
browse_read's own success flag, and surfaces per-source read errors instead of
papering over them.

READ-ONLY, public pages only. No login, no money, no writes.

The single side-effecting dependency — browse_read — is injectable so the
assembly logic is unit-testable with a fake reader (no live browser in CI), while
production uses the real open-source browser arm by default.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

# Default (production) reader: the real read-only browser arm. Imported lazily-ish
# at module load but never CALLED unless a live build runs, so importing this
# module never launches a browser.
from ..hands.browser_use_link import browse_read as _real_browse_read

# A reader is anything with browse_read's shape. We depend on the RESULT carrying
# .success / .result / .url / .trust / .needs_cross_check / .error — i.e. a
# BrowseReadResult or any duck-typed stand-in (the test fake).
BrowseReader = Callable[..., Any]

# The fine fields we try to pull per subject. Order = display order.
_DEFAULT_FINE_FIELDS: Sequence[str] = ("role", "org", "location")

# Map a field name -> a focused extraction question for the structured read.
_FIELD_PROMPTS: Dict[str, str] = {
    "role": (
        "What is {subject}'s primary role, title, or profession according to this "
        "page? Answer with ONLY the role/title, or 'NOT FOUND' if the page does "
        "not state it."
    ),
    "org": (
        "Which organization, company, or institution is {subject} most associated "
        "with according to this page? Answer with ONLY the organization name, or "
        "'NOT FOUND' if the page does not state it."
    ),
    "location": (
        "What location (city, region, or country) is {subject} associated with "
        "according to this page? Answer with ONLY the location, or 'NOT FOUND' if "
        "the page does not state it."
    ),
}

# Tokens a focused read returns when the page simply doesn't carry the fact. We
# treat these as "absent", never as a real value (no invented facts).
_NOT_FOUND_MARKERS = ("not found", "not stated", "n/a", "none", "unknown", "")


@dataclass
class Source:
    """One public page we read, and how that read went."""

    url: str
    kind: str = "page"  # advisory hint: "biography" | "company" | "bio" | "page"
    read_ok: bool = False
    overview: Optional[str] = None  # the coarse whole-page read text
    error: Optional[str] = None
    steps: int = 0


@dataclass
class ProfileFact:
    """A single trust-graded fact with its provenance.

    `needs_cross_check` and `confidence` come straight from the read's trust tier:
    a fine-grained field pull is low-trust and must be cross-checked; a coarse
    whole-page read is a tier higher.
    """

    field: str
    value: str
    source_url: str
    confidence: str  # "low" | "medium" | "high"
    needs_cross_check: bool
    trust: str  # "fine" (specific field pull) | "coarse" (whole-page read)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Profile:
    """The assembled, structured profile. Every claim is a ProfileFact with its
    own source + trust grade; convenience top-level fields (role/org/location)
    mirror the best available fact for quick access but the facts list is canon.
    """

    name: str
    role: Optional[str] = None
    org: Optional[str] = None
    location: Optional[str] = None
    key_facts: List[ProfileFact] = field(default_factory=list)
    sources: List[Source] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)

    @property
    def needs_cross_check_count(self) -> int:
        return sum(1 for f in self.key_facts if f.needs_cross_check)

    def fact_for(self, field_name: str) -> Optional[ProfileFact]:
        """Best (highest-trust) fact for a field, if any."""
        cands = [f for f in self.key_facts if f.field == field_name]
        if not cands:
            return None
        # coarse beats fine; otherwise first wins (source order).
        cands.sort(key=lambda f: 0 if f.trust == "coarse" else 1)
        return cands[0]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role,
            "org": self.org,
            "location": self.location,
            "key_facts": [f.as_dict() for f in self.key_facts],
            "sources": [asdict(s) for s in self.sources],
            "blockers": self.blockers,
            "summary": {
                "facts": len(self.key_facts),
                "needs_cross_check": self.needs_cross_check_count,
                "sources_read_ok": sum(1 for s in self.sources if s.read_ok),
                "sources_total": len(self.sources),
            },
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.as_dict(), indent=indent, default=str)


def _clean(text: Optional[str]) -> str:
    if not text:
        return ""
    # Collapse whitespace; a focused read sometimes wraps the answer in a sentence
    # despite instructions, so keep it tight but don't over-truncate.
    return re.sub(r"\s+", " ", str(text)).strip()


def _is_found(value: str) -> bool:
    v = value.strip().lower()
    if v in _NOT_FOUND_MARKERS:
        return False
    # Guard against the model echoing the not-found instruction.
    return "not found" not in v and "does not state" not in v and len(v) <= 200


class ProfileBuilder:
    """Assembles a Profile from public source URLs using a browse reader.

    The reader is injected (defaults to the real read-only browser arm), so the
    assembly logic is fully unit-testable without a live browser.
    """

    def __init__(
        self,
        browse_reader: Optional[BrowseReader] = None,
        *,
        fine_fields: Sequence[str] = _DEFAULT_FINE_FIELDS,
        per_read_timeout_s: int = 180,
        max_steps_overview: int = 8,
        max_steps_field: int = 6,
    ) -> None:
        self._read: BrowseReader = browse_reader or _real_browse_read
        self._fine_fields = tuple(fine_fields)
        self._timeout_s = per_read_timeout_s
        self._max_steps_overview = max_steps_overview
        self._max_steps_field = max_steps_field

    # -- per-source reads -------------------------------------------------

    def _read_overview(self, subject: str, src: Source) -> Source:
        """COARSE read: a whole-page overview of the subject. Higher-trust tier."""
        task = (
            f"This is a public page about {subject}. Read it and report a concise "
            f"factual overview of {subject}: who they are, their role/profession, "
            f"the main organization they are associated with, and where they are "
            f"based, in 2-4 sentences. Use only what this page states."
        )
        res = self._read(
            task,
            url=src.url,
            structured=False,
            max_steps=self._max_steps_overview,
            timeout_s=self._timeout_s,
        )
        src.read_ok = bool(getattr(res, "success", False))
        src.overview = _clean(getattr(res, "result", None)) or None
        src.steps = int(getattr(res, "steps", 0) or 0)
        if not src.read_ok:
            src.error = getattr(res, "error", None) or "read returned no result"
        return src

    def _read_field(self, subject: str, src: Source, field_name: str) -> Optional[ProfileFact]:
        """FINE read: a focused pull of one field. Low-trust, needs_cross_check."""
        prompt_tmpl = _FIELD_PROMPTS.get(
            field_name,
            "What is {subject}'s " + field_name + " according to this page? Answer "
            "with ONLY the value, or 'NOT FOUND'.",
        )
        task = prompt_tmpl.format(subject=subject)
        res = self._read(
            task,
            url=src.url,
            structured=True,  # fine-grained pull -> low trust by the arm's grading
            max_steps=self._max_steps_field,
            timeout_s=self._timeout_s,
        )
        if not bool(getattr(res, "success", False)):
            return None
        value = _clean(getattr(res, "result", None))
        if not _is_found(value):
            return None
        # Honor the arm's trust grade but never above the FINE ceiling for a
        # specific field pull: these are low-trust, must-cross-check by design.
        return ProfileFact(
            field=field_name,
            value=value,
            source_url=getattr(res, "url", None) or src.url,
            confidence="low",
            needs_cross_check=True,
            trust="fine",
        )

    @staticmethod
    def _coarse_facts_from_overview(src: Source) -> List[ProfileFact]:
        """Derive a single COARSE 'overview' fact from a whole-page read. We do
        NOT regex-mine specific fields out of the prose (that would manufacture
        fine claims and dishonestly trust them) — the overview is kept as one
        higher-trust narrative fact, and specific fields come from the FINE reads.
        """
        if not (src.read_ok and src.overview):
            return []
        return [
            ProfileFact(
                field="overview",
                value=src.overview,
                source_url=src.url,
                confidence="medium",
                needs_cross_check=False,  # coarse whole-page read: higher tier
                trust="coarse",
            )
        ]

    # -- public API -------------------------------------------------------

    def build(
        self,
        name: str,
        sources: Sequence[Any],
    ) -> Profile:
        """Build a structured profile for `name` from `sources`.

        Each source may be a bare URL string, or a dict/Source carrying
        {"url": ..., "kind": ...}. Reads are READ-ONLY. Any per-source read
        failure becomes a blocker on that source, never a faked fact.
        """
        norm_sources = [_coerce_source(s) for s in sources]
        profile = Profile(name=name, sources=norm_sources)

        for src in norm_sources:
            # 1) coarse whole-page overview (higher-trust tier)
            self._read_overview(name, src)
            if not src.read_ok:
                profile.blockers.append(
                    f"could not read {src.url}: {src.error}"
                )
                # A blocked overview usually means field reads will fail too, but
                # we still try the fine pulls — a page may answer a focused
                # question even when the broad summary read stalled.
            profile.key_facts.extend(self._coarse_facts_from_overview(src))

            # 2) fine field pulls (low-trust, needs_cross_check)
            for fld in self._fine_fields:
                fact = self._read_field(name, src, fld)
                if fact is not None:
                    profile.key_facts.append(fact)

        _hoist_top_level_fields(profile, self._fine_fields)
        return profile


def _coerce_source(s: Any) -> Source:
    if isinstance(s, Source):
        return s
    if isinstance(s, str):
        return Source(url=s)
    if isinstance(s, dict):
        return Source(
            url=s["url"],
            kind=s.get("kind", "page"),
        )
    raise TypeError(f"unsupported source: {s!r}")


def _hoist_top_level_fields(profile: Profile, fields: Sequence[str]) -> None:
    """Fill convenience top-level role/org/location from the best fact per field."""
    for fld in fields:
        if fld not in ("role", "org", "location"):
            continue
        best = profile.fact_for(fld)
        if best is not None:
            setattr(profile, fld, best.value)


def build_profile(
    name: str,
    sources: Sequence[Any],
    *,
    browse_reader: Optional[BrowseReader] = None,
    fine_fields: Sequence[str] = _DEFAULT_FINE_FIELDS,
) -> Profile:
    """Convenience one-shot: build a profile for `name` from public `sources`.

    Defaults to the real read-only browser arm; pass `browse_reader` to inject a
    fake for tests.
    """
    return ProfileBuilder(
        browse_reader=browse_reader,
        fine_fields=fine_fields,
    ).build(name, sources)


if __name__ == "__main__":
    # Tiny manual CLI: build a LIVE profile from public pages.
    #   python -m anticipy_engine.onboarding.profile_builder "Name" url1 [url2 ...]
    import sys

    if len(sys.argv) < 3:
        print(
            "usage: profile_builder.py <name> <url> [url ...]",
            file=sys.stderr,
        )
        raise SystemExit(2)
    _name = sys.argv[1]
    _urls = sys.argv[2:]
    _profile = build_profile(_name, _urls)
    print(_profile.to_json())
