import os


os.environ["ANTICIPY_PORT"] = "19873"

from app.product.server import _normalize_post_asr_text  # noqa: E402


def test_post_asr_normalization_preserves_raw_audit_boundary():
    raw = (
        "Anticipate, use the Real Salesforce, HubSpot, JIRA, and any already "
        "open Gmail or calendar surfaces for North Star Linen."
    )

    text, changes = _normalize_post_asr_text(raw)

    assert raw.startswith("Anticipate,")
    assert text.startswith("Anticipy,")
    assert "Northstar Linen" in text
    assert raw != text
    assert {change["reason"] for change in changes} == {
        "hotword_asr_correction",
        "known_entity_compound_normalization",
    }
