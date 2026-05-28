import json
import os
from pathlib import Path

import pytest


os.environ.setdefault("ANTICIPY_ENGINE_PORT", "18741")

from app.product import server  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[2]
PERSONA_DIR = REPO_ROOT / "verifier" / "personas"
PERSONA_PATHS = sorted(PERSONA_DIR.glob("*.json"))


def _load_persona(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


PERSONAS = [(path.name, _load_persona(path)) for path in PERSONA_PATHS]


def _wearer_transcript(persona: dict) -> list[dict]:
    return [
        {"speaker_id": "WEARER", "text": str(text)}
        for text in persona.get("qa_hints", {}).values()
        if str(text).strip()
    ]


def _reset_product_session() -> None:
    server._SESS["i"] = 0
    server._SESS["transcript"] = []
    server._SESS["profile"] = None
    server._SESS["profile_obj"] = None
    server._SESS.pop("last_cloud_sync", None)


def _lossy_extractor_profile(persona: dict) -> dict:
    people = {}
    for contact in persona.get("contacts", []):
        if "<" in contact and contact.endswith(">"):
            name, email = contact[:-1].split("<", 1)
            people[name.strip()] = email.strip()
    return {"people": people}


def _build_repaired_payload(persona: dict, monkeypatch, tmp_path: Path) -> dict:
    _reset_product_session()
    monkeypatch.setattr(
        server,
        "_profile_store_path",
        lambda: tmp_path / f"{persona['user_id']}.json",
    )

    def fake_cloud_sync() -> dict:
        return {"ok": True, "payload": server._dossier_payload()}

    monkeypatch.setattr(server, "_sync_profile_to_cloud", fake_cloud_sync)

    server._SESS["transcript"] = _wearer_transcript(persona)
    prof = server._profile_from_json(_lossy_extractor_profile(persona))
    server._repair_profile_from_onboarding(prof)
    server._SESS["profile_obj"] = prof

    profile = server._profile_json()
    profile["pronoun_map"] = server._infer_pronoun_map_from_transcript(
        profile.get("people") or {}
    )
    profile["well_populated"] = True
    server._SESS["profile"] = profile

    cloud_sync = server._save_profile()
    return cloud_sync["payload"]


def test_all_verifier_personas_are_exercised() -> None:
    assert len(PERSONAS) >= 3
    assert {name for name, _ in PERSONAS} == {
        path.name for path in PERSONA_DIR.glob("*.json")
    }


@pytest.mark.parametrize("persona_name,persona", PERSONAS)
def test_onboarding_repair_persists_verifier_rich_dossier(
    persona_name: str,
    persona: dict,
    monkeypatch,
    tmp_path: Path,
) -> None:
    payload = _build_repaired_payload(persona, monkeypatch, tmp_path)
    profile = payload["profile"]

    assert payload["field_count"] >= persona["expected_min_dossier_fields"], (
        persona_name,
        payload["field_count"],
        persona["expected_min_dossier_fields"],
        profile,
    )
    for pronoun, expected in persona["expected_pronoun_map"].items():
        assert payload["pronoun_map"][pronoun] == expected

    people_values = set(payload["people"].values())
    assert set(persona["contacts"]).issubset(people_values)
    assert profile["working_hours"]
    assert profile["quiet_hours"]
    assert profile["comms_prefs"]
    assert profile["critical_software"]
