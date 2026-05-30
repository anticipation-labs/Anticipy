"""Phase 8 sector profile tests.

Covers:
  - all nine YAML hint packages parse and validate
  - detection picks the right sector from realistic dossier fragments
  - unknown / sparse dossiers fall back to ``generic``
  - format_system_prompt renders the expected template
  - the loader's cache returns the same dict and only reads once
  - YAML files contain no em-dashes or en-dashes (writing-style gate)
  - YAML files contain no hardcoded action verbs ("click", "type",
    "fill in", "fill out") so the profiles stay hints, not recipes

Tests are pure file work: no network, no Playwright, no LLM calls.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.sectors import detector, loader  # noqa: E402

PROFILES_DIR = Path(loader._PROFILES_DIR)  # noqa: SLF001 (intentional)


@pytest.fixture(autouse=True)
def _reset_cache():
    loader.cache_reset()
    yield
    loader.cache_reset()


# ---------------------------------------------------------------------------
# YAML structural gates
# ---------------------------------------------------------------------------


def test_each_of_9_yaml_files_loads_without_error():
    """All nine canonical sector files parse, validate, and return dicts."""
    for name in loader.KNOWN_SECTORS:
        data = loader.load_hints(name)
        assert isinstance(data, dict), f"{name}: load_hints did not return dict"
        assert data["sector"] == name, f"{name}: sector field mismatch"


def test_each_yaml_has_required_fields():
    for name in loader.KNOWN_SECTORS:
        data = loader.load_hints(name)
        for field in loader.REQUIRED_FIELDS:
            assert field in data, f"{name}: missing required field {field!r}"
            # list fields must be non-empty
            if field in (
                "common_tools",
                "common_goals",
                "vocab_hints",
                "preferred_channels",
                "detection_signals",
                "sample_personas",
            ):
                assert isinstance(data[field], list) and data[field], (
                    f"{name}: list field {field!r} must be non-empty"
                )


def test_nine_yaml_files_exist_on_disk():
    """Sanity: the eight verticals plus generic = nine files."""
    files = sorted(p.name for p in PROFILES_DIR.glob("*.yaml"))
    expected = sorted(f"{n}.yaml" for n in loader.KNOWN_SECTORS)
    assert files == expected, f"profile files on disk: {files} expected: {expected}"


# ---------------------------------------------------------------------------
# Detection cases
# ---------------------------------------------------------------------------


def test_detect_construction_from_procore_signal():
    dossier = {
        "scraped_tabs": [
            {"url": "https://app.procore.com/projects", "title": "Procore"},
            {"url": "https://buildertrend.net/dashboard", "title": "Buildertrend"},
        ],
        "calendar": [
            {"title": "Walkthrough at 1840 Oak St job site"},
            {"title": "RFI review with subs"},
        ],
        "top_contacts": [
            {"email": "orders@ferguson.com", "freq": 14},
        ],
    }
    assert detector.detect_sector(dossier) == "construction"


def test_detect_sales_from_salesforce_signal():
    dossier = {
        "scraped_tabs": [
            {"url": "https://acme.lightning.force.com/lightning/o/Opportunity",
             "title": "Salesforce"},
            {"url": "https://app.hubspot.com/contacts", "title": "HubSpot"},
            {"url": "https://app.outreach.io/sequences", "title": "Outreach"},
        ],
        "calendar": [
            {"title": "Discovery call with Acme"},
            {"title": "Demo with Globex"},
        ],
        "recent_threads": [
            {"subject": "Re: MEDDPICC review on the Initech deal"},
        ],
    }
    assert detector.detect_sector(dossier) == "sales"


def test_detect_job_seeking_from_indeed_linkedin_signals():
    dossier = {
        "scraped_tabs": [
            {"url": "https://www.indeed.com/q-senior-pm-jobs.html",
             "title": "Indeed"},
            {"url": "https://www.linkedin.com/jobs/", "title": "LinkedIn Jobs"},
            {"url": "https://boards.greenhouse.io/company/jobs", "title": "Greenhouse"},
        ],
        "calendar": [
            {"title": "Recruiter screen at Stripe"},
            {"title": "On site at Notion"},
        ],
        "top_contacts": [
            {"email": "no-reply@greenhouse.io", "freq": 6},
        ],
    }
    assert detector.detect_sector(dossier) == "job_seeking"


def test_detect_healthcare_from_athena_signal():
    dossier = {
        "scraped_tabs": [
            {"url": "https://athenanet.athenahealth.com", "title": "Athenahealth"},
            {"url": "https://mychart.example.org", "title": "Epic MyChart"},
            {"url": "https://www.uptodate.com/contents/search", "title": "UpToDate"},
        ],
        "calendar": [
            {"title": "Rounding 7am to 9am"},
            {"title": "Clinic encounter follow up"},
        ],
        "vocab_seen": ["prior auth", "SOAP note", "credentialing"],
    }
    assert detector.detect_sector(dossier) == "healthcare"


def test_detect_startup_from_yc_or_anthropic_signal():
    dossier = {
        "scraped_tabs": [
            {"url": "https://bookface.ycombinator.com/home",
             "title": "Y Combinator Bookface"},
            {"url": "https://console.anthropic.com/dashboard",
             "title": "Anthropic Console"},
            {"url": "https://linear.app/inbox", "title": "Linear"},
            {"url": "https://mercury.com/dashboard", "title": "Mercury"},
        ],
        "calendar": [
            {"title": "Investor update draft"},
            {"title": "Demo with lead investor"},
        ],
    }
    assert detector.detect_sector(dossier) == "startup_founder"


def test_detect_stay_at_home_from_school_portal_signals():
    dossier = {
        "scraped_tabs": [
            {"url": "https://parent.powerschool.com", "title": "PowerSchool"},
            {"url": "https://app.seesaw.me", "title": "Seesaw"},
            {"url": "https://web.brightwheel.com", "title": "Brightwheel"},
            {"url": "https://www.signupgenius.com/go/snack",
             "title": "SignUpGenius"},
        ],
        "calendar": [
            {"title": "School pickup at 3pm"},
            {"title": "Pediatrician well visit"},
        ],
    }
    assert detector.detect_sector(dossier) == "stay_at_home_parent"


def test_detect_pensioner_from_medicare_aarp_signals():
    dossier = {
        "scraped_tabs": [
            {"url": "https://www.medicare.gov/account", "title": "Medicare.gov"},
            {"url": "https://www.aarp.org/membership", "title": "AARP"},
            {"url": "https://www.silversneakers.com",
             "title": "SilverSneakers"},
            {"url": "https://nb.fidelity.com/public/nb/default/home",
             "title": "Fidelity"},
        ],
        "calendar": [
            {"title": "Bridge club"},
            {"title": "Annual wellness visit"},
        ],
    }
    assert detector.detect_sector(dossier) == "pensioner"


def test_detect_freelance_from_upwork_signals():
    dossier = {
        "scraped_tabs": [
            {"url": "https://www.upwork.com/nx/find-work/", "title": "Upwork"},
            {"url": "https://my.freshbooks.com/invoices", "title": "FreshBooks"},
            {"url": "https://app.honeybook.com/projects", "title": "HoneyBook"},
            {"url": "https://calendly.com/me", "title": "Calendly"},
        ],
        "calendar": [
            {"title": "Kickoff with new retainer client"},
            {"title": "Invoice milestone two due"},
        ],
    }
    assert detector.detect_sector(dossier) == "freelance"


def test_unknown_sector_returns_generic():
    """A dossier with only generic signals should not match any vertical."""
    dossier = {
        "scraped_tabs": [
            {"url": "https://mail.google.com/mail/u/0/#inbox", "title": "Gmail"},
            {"url": "https://www.amazon.com/orders", "title": "Amazon"},
            {"url": "https://maps.google.com", "title": "Maps"},
        ],
        "calendar": [
            {"title": "Dentist appointment"},
        ],
        "top_contacts": [
            {"email": "mom@gmail.com", "freq": 12},
        ],
    }
    assert detector.detect_sector(dossier) == "generic"


def test_empty_dossier_returns_generic():
    assert detector.detect_sector({}) == "generic"
    assert detector.detect_sector(None) == "generic"


# ---------------------------------------------------------------------------
# System prompt formatting
# ---------------------------------------------------------------------------


def test_load_hints_returns_formatted_system_prompt():
    hints = loader.load_hints("construction")
    prompt = loader.format_system_prompt(hints)
    assert "The user is a Construction." in prompt
    assert "They typically use" in prompt
    assert "Procore" in prompt
    assert "Common goals" in prompt
    assert "punch list" in prompt
    assert "Prefer sms, voice for receipts." in prompt


def test_format_system_prompt_for_every_sector_has_display_name():
    """Every sector's prompt should at least state the display name."""
    for name in loader.KNOWN_SECTORS:
        hints = loader.load_hints(name)
        prompt = loader.format_system_prompt(hints)
        display = hints["display_name"]
        assert display in prompt, (
            f"{name}: display name {display!r} missing from prompt: {prompt!r}"
        )


# ---------------------------------------------------------------------------
# Caching behaviour
# ---------------------------------------------------------------------------


def test_load_hints_caches():
    """Second call returns the same dict object and doesn't re-read disk."""
    loader.cache_reset()
    first = loader.load_hints("sales")
    second = loader.load_hints("sales")
    assert first is second, "cache must return the same dict identity"
    assert loader.load_count("sales") == 1, (
        f"sales loaded {loader.load_count('sales')} times; expected 1"
    )
    # And a different sector loads independently
    loader.load_hints("freelance")
    assert loader.load_count("sales") == 1
    assert loader.load_count("freelance") == 1


def test_load_hints_unknown_falls_back_to_generic():
    data = loader.load_hints("nonexistent_sector_name")
    assert data["sector"] == "generic"


# ---------------------------------------------------------------------------
# Writing style + no-recipes gates
# ---------------------------------------------------------------------------


def test_yaml_no_em_dashes_anywhere():
    """Anticipy writing style: no em-dashes or en-dashes anywhere."""
    bad_chars = ("—", "–")  # em-dash, en-dash
    for path in sorted(PROFILES_DIR.glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        for ch in bad_chars:
            assert ch not in text, (
                f"{path.name}: contains forbidden char U+{ord(ch):04X}"
            )


def test_yaml_no_hardcoded_steps():
    """Profiles are hints, not recipes. No action verbs like click/type/fill in."""
    banned = (
        re.compile(r"\bclick\b", re.IGNORECASE),
        re.compile(r"\btype\b", re.IGNORECASE),
        re.compile(r"\bfill in\b", re.IGNORECASE),
        re.compile(r"\bfill out\b", re.IGNORECASE),
        re.compile(r"\btap\b", re.IGNORECASE),
        re.compile(r"\bpress\b", re.IGNORECASE),
    )
    for path in sorted(PROFILES_DIR.glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        for pat in banned:
            assert not pat.search(text), (
                f"{path.name}: contains banned action verb /{pat.pattern}/"
            )


def test_nine_yamls_are_genuinely_different():
    """No two YAMLs should share the same display_name or common_tools list."""
    seen_display: dict[str, str] = {}
    seen_tools: dict[tuple[str, ...], str] = {}
    for name in loader.KNOWN_SECTORS:
        data = loader.load_hints(name)
        display = data["display_name"]
        assert display not in seen_display, (
            f"{name}: display_name {display!r} duplicates {seen_display[display]!r}"
        )
        seen_display[display] = name
        tools = tuple(sorted(str(t).lower() for t in data["common_tools"]))
        assert tools not in seen_tools, (
            f"{name}: common_tools list duplicates {seen_tools[tools]!r}"
        )
        seen_tools[tools] = name


def test_known_sectors_count_is_nine():
    """Exactly nine: eight verticals plus generic."""
    assert len(loader.KNOWN_SECTORS) == 9
    assert "generic" in loader.KNOWN_SECTORS
