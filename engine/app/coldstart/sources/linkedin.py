"""LinkedIn source extractor for the cold-start dossier inhale.

What this returns:

    {
        "source": "linkedin",
        "ok": bool,
        "profile": {
            "name": str,
            "headline": str,
            "job_title": str,
            "company": str,
            "location": str,
            "education": [str],
            "sector": str,
        },
        "error": str,        # only when ok is False
    }

Per planning/00-handoff/ARCHITECTURE.md rule 1 (no per-app code), this
file owns the URL choice (LinkedIn's own /in/me page) and a generic
DOM-extraction prompt for the bridge. The bridge is expected to drive
the user's real Chrome via the extension and return a JSON blob
shaped roughly like the above. The sector is inferred from the
profile headline + company, with a small keyword map.

If LinkedIn is not signed in (extension returns ok=False), this
function still returns ok=False with an empty profile dict so the
orchestrator can continue without crashing.
"""

from __future__ import annotations

from typing import Any

from . import _bridge_protocol as _bp


LINKEDIN_PROFILE_URL = "https://www.linkedin.com/in/me/"


# Keyword to sector mapping. Generic, additive, NOT hardcoded per-user.
# Mirrors planning/00-handoff/ARCHITECTURE.md section 10 sector list:
# construction, sales, job_seeking, healthcare, startup_founder,
# stay_at_home_parent, pensioner, freelance.
_SECTOR_KEYWORDS: dict[str, tuple[str, ...]] = {
    "construction": (
        "construction", "contractor", "general contractor", "builder",
        "subcontractor", "project superintendent", "foreman",
        "buildertrend", "procore",
    ),
    "sales": (
        "sales", "account executive", "ae", "sdr", "bdr",
        "account manager", "salesforce", "hubspot",
    ),
    "healthcare": (
        "doctor", "physician", "nurse", "md", "rn", "clinical",
        "hospital", "epic systems", "pharmacy", "pharmacist",
    ),
    "startup_founder": (
        "founder", "co-founder", "ceo", "cofounder", "founding",
        "cto", "cpo", "y combinator", "techstars",
    ),
    "freelance": (
        "freelance", "freelancer", "independent contractor",
        "self-employed", "consultant",
    ),
    "job_seeking": (
        "open to work", "seeking", "looking for new opportunities",
        "actively interviewing",
    ),
}


def _infer_sector(headline: str, company: str, job_title: str) -> str:
    haystack = " ".join(
        x for x in (headline or "", company or "", job_title or "") if x
    ).lower()
    if not haystack:
        return ""
    for sector, kws in _SECTOR_KEYWORDS.items():
        for kw in kws:
            if kw in haystack:
                return sector
    return ""


async def extract(bridge: Any) -> dict:
    """Drive the wearer's Chrome (via the extension bridge) to read
    their LinkedIn profile DOM. Returns the structured dict above.

    The bridge contract:

        await bridge.dispatch({
            "type": "extract_dossier_source",
            "source": "linkedin",
            "url": LINKEDIN_PROFILE_URL,
            "extract_schema": {...},
        }) -> dict with keys ok / data / error

    The extension reads the profile page, pulls out name / headline /
    job title / company / location / education entries from the DOM
    by stable LinkedIn selectors. We do the sector inference here in
    Python so the extension does not need to change to bump the map.
    """
    schema = {
        "name": "text",
        "headline": "text",
        "job_title": "text",
        "company": "text",
        "location": "text",
        "education": ["text"],
    }
    payload = {
        "type": "extract_dossier_source",
        "source": "linkedin",
        "url": LINKEDIN_PROFILE_URL,
        "extract_schema": schema,
    }
    try:
        resp = await _bp.dispatch(bridge, payload)
    except Exception as exc:
        return {
            "source": "linkedin",
            "ok": False,
            "profile": {},
            "error": f"dispatch raised: {type(exc).__name__}: {exc}",
        }

    if not isinstance(resp, dict) or not resp.get("ok"):
        return {
            "source": "linkedin",
            "ok": False,
            "profile": {},
            "error": str((resp or {}).get("error") or "extension reported not ok"),
        }

    data = resp.get("data") or {}
    if not isinstance(data, dict):
        data = {}

    name = str(data.get("name") or "").strip()
    headline = str(data.get("headline") or "").strip()
    job_title = str(data.get("job_title") or "").strip()
    company = str(data.get("company") or "").strip()
    location = str(data.get("location") or "").strip()
    raw_edu = data.get("education") or []
    education = [str(e).strip() for e in raw_edu if str(e).strip()][:10]

    sector = _infer_sector(headline, company, job_title)

    return {
        "source": "linkedin",
        "ok": True,
        "profile": {
            "name": name,
            "headline": headline,
            "job_title": job_title,
            "company": company,
            "location": location,
            "education": education,
            "sector": sector,
        },
    }


__all__ = ["extract", "LINKEDIN_PROFILE_URL"]
