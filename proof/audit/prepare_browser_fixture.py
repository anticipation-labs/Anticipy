"""Create/pair or erase only this audit's phone-less browser fixture account."""
import argparse
import json
from pathlib import Path
import secrets
from urllib.parse import urlencode, quote

from proof.audit.live_api_release import request
from proof.audit.model_gateway import atomic_json

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("prepare", "cleanup"))
    parser.add_argument("--label", required=True)
    parser.add_argument("--base", choices=("https://api.anticipy.ai", "http://127.0.0.1:8787"), default="https://api.anticipy.ai")
    args = parser.parse_args()
    path = ROOT / "work/audit" / (args.label + "-private.json")
    evidence_path = ROOT / "work/audit" / (args.label + ".json")
    if args.mode == "cleanup":
        fixture = json.loads(path.read_text())
        if fixture.get("created_by") != "anticipy-browser-audit" or not fixture["email"].endswith("@anticipy-test.invalid"):
            raise RuntimeError("This is not an audit fixture")
        if not fixture.get("accountDeleted"):
            if not fixture.get("ownerToken"):
                status, auth, _ = request(fixture["base"], "POST", "/api/collections/owners/auth-with-password",
                    {"identity": fixture["email"], "password": fixture["password"]})
                if status != 200 or not auth.get("token"):
                    raise RuntimeError(f"Cannot authenticate this fixture for cleanup ({status})")
                fixture["ownerToken"] = auth["token"]
                atomic_json(path, fixture)
            status, body, _ = request(fixture["base"], "POST", "/me/delete", {"confirm": "delete"}, fixture["ownerToken"])
            if status != 200 or body.get("account_deleted") is not True:
                raise RuntimeError(f"Fixture cleanup not confirmed ({status})")
            fixture["accountDeleted"] = True
            atomic_json(path, fixture)
        revoked_status = None
        if fixture.get("agentId") and fixture.get("agentToken"):
            status, _, _ = request(fixture["base"], "GET", "/agent/key?agent_id=" + quote(fixture["agentId"]),
                                  extra_headers={"X-Anticipy-Agent-Token": fixture["agentToken"]})
            if status != 403:
                raise RuntimeError(f"Erased fixture credential was not revoked ({status})")
            revoked_status = status
        evidence = json.loads(evidence_path.read_text()) if evidence_path.exists() else {}
        evidence.update(cleaned_up=True, revoked_status=revoked_status)
        atomic_json(evidence_path, evidence)
        print(json.dumps({"cleaned_up": True, "revoked_status": revoked_status}))
        return
    if path.exists():
        raise RuntimeError("Use a fresh label; do not overwrite cleanup credentials")
    password = secrets.token_urlsafe(32)
    email = "browser-" + secrets.token_hex(12) + "@anticipy-test.invalid"
    # Save recovery credentials before a request can create remote state.
    fixture = dict(created_by="anticipy-browser-audit", base=args.base, email=email, password=password)
    atomic_json(path, fixture)
    status, owner, _ = request(args.base, "POST", "/api/collections/owners/records", {
        "email": email, "password": password, "passwordConfirm": password})
    if status != 200 or not owner.get("id"):
        raise RuntimeError(f"Fixture signup failed ({status})")
    fixture["ownerId"] = owner["id"]
    atomic_json(path, fixture)
    status, auth, _ = request(args.base, "POST", "/api/collections/owners/auth-with-password", {"identity": email, "password": password})
    if status != 200 or not auth.get("token"):
        raise RuntimeError(f"Fixture login failed ({status}); remove the newly created fixture")
    fixture["ownerToken"] = auth["token"]
    atomic_json(path, fixture)
    status, _, _ = request(args.base, "POST", "/me/profile/upsert", {
        "name": "Casey Browser Fixture", "timezone": "America/Vancouver"}, auth["token"])
    if status != 200:
        raise RuntimeError(f"Fixture profile failed ({status})")
    agent_id = "browser-audit-" + secrets.token_hex(12)
    status, agent, _ = request(args.base, "POST", "/agent/register", {"agent_id": agent_id, "browser": "Chrome audit 0.16.0"})
    if status != 200 or not agent.get("agent_token"):
        raise RuntimeError(f"Registration failed ({status})")
    fixture.update(agentId=agent_id, agentToken=agent["agent_token"], recordId=agent["id"], pairCode=agent["pair_code"])
    atomic_json(path, fixture)
    status, matches, _ = request(args.base, "GET", "/api/collections/agents/records?" + urlencode({"filter": f'pair_code="{agent["pair_code"]}"'}), token=auth["token"])
    if status != 200 or [item["id"] for item in matches.get("items", [])] != [agent["id"]]:
        raise RuntimeError(f"Pair code lookup did not find exactly this agent ({status})")
    status, _, _ = request(args.base, "PATCH", "/api/collections/agents/records/" + agent["id"], {
        "owner": owner["id"], "owner_ref": owner["id"], "paired": True}, auth["token"])
    if status != 200:
        raise RuntimeError(f"Pairing failed ({status})")
    status, saved, _ = request(args.base, "GET", "/api/collections/agents/records/" + agent["id"], token=auth["token"])
    if status != 200 or saved.get("owner_ref") != owner["id"] or saved.get("paired") is not True:
        raise RuntimeError("Pairing did not persist")
    status, bundle, _ = request(args.base, "GET", "/agent/key?agent_id=" + quote(agent_id), extra_headers={"X-Anticipy-Agent-Token": agent["agent_token"]})
    if status != 200 or bundle.get("llm_proxy") is not True or bundle.get("owner_ref") != owner["id"]:
        raise RuntimeError(f"Paired model access failed ({status})")
    fixture.update(model=bundle["model"], visionModel=bundle["vision_model"], ownerProfile=bundle.get("owner"))
    atomic_json(path, fixture)
    evidence = dict(scope="live HTTP signup, phone-less profile, agent registration, exact code lookup, authenticated pairing, persisted ownership and model access",
                    base=args.base, paired=True, ownerMatched=True, model=bundle["model"], vision_model=bundle["vision_model"], cleaned_up=False)
    atomic_json(evidence_path, evidence)
    print(json.dumps(evidence))


if __name__ == "__main__":
    main()
