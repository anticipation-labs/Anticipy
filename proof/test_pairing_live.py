"""Live pairing + heartbeat + drop recovery, against the real backend.

Plays both sides against real PocketBase: the extension's registration/
heartbeat/claim logic (same requests background.js makes) and the app's
pair-by-code + health logic (same requests AnticipySession makes).
"""
import sys, time, uuid, datetime
sys.path.insert(0, "/home/ubuntu/anticipy_app")

import requests
from brain.anticipy_core import Anticipy

BASE = "http://127.0.0.1:8090"
AGENTS = f"{BASE}/api/collections/agents/records"
JOBS = f"{BASE}/api/collections/jobs/records"


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def main():
    assert requests.get(f"{BASE}/api/health", timeout=5).ok

    # 1. Extension registers with a 6-digit pair code (background.js logic).
    agent_id = str(uuid.uuid4())
    pair_code = "428913"
    rec = requests.post(AGENTS, json={
        "agent_id": agent_id, "pair_code": pair_code, "paired": False,
        "browser": "Chrome/138", "last_seen": now(),
    }).json()
    assert rec.get("id"), rec
    print(f"PASS extension registered with pair code {pair_code}")

    # 2. App pairs by code -> owner bound (SettingsView/Onboarding logic).
    owner = str(uuid.uuid4())
    found = requests.get(AGENTS, params={"filter": f'pair_code="{pair_code}"'}).json()["items"]
    assert found and found[0]["agent_id"] == agent_id
    requests.patch(f"{AGENTS}/{rec['id']}", json={"owner": owner, "paired": True})
    bound = requests.get(f"{AGENTS}/{rec['id']}").json()
    assert bound["owner"] == owner and bound["paired"] is True
    print("PASS app claimed the code; agent bound to owner")

    # 3. Wrong code fails cleanly.
    bad = requests.get(AGENTS, params={"filter": 'pair_code="000000"'}).json()["items"]
    assert bad == []
    print("PASS wrong code matches nothing")

    # 4. Heartbeat -> app-side health "last seen Ns ago".
    requests.patch(f"{AGENTS}/{rec['id']}", json={"last_seen": now()})
    seen = requests.get(f"{AGENTS}/{rec['id']}").json()["last_seen"]
    age = (datetime.datetime.now(datetime.timezone.utc)
           - datetime.datetime.fromisoformat(seen.replace(" ", "T").replace("Z", "+00:00"))).total_seconds()
    assert 0 <= age < 10, age
    print(f"PASS heartbeat fresh: agent last seen {age:.1f}s ago -> 'Agent live'")

    # 5. Owner-scoped work: Anticipy queues a job stamped with this owner;
    #    the paired agent's claim filter finds it, a stranger's doesn't.
    a = Anticipy(backend_url=BASE, owner_id=owner)
    a.hear("I'll send Sarah the pitch deck right after this call.")
    job_id = a.loops[0].job_id
    requests.patch(f"{JOBS}/{job_id}", json={"status": "queued"})  # user's YES
    mine = requests.get(JOBS, params={
        "filter": f'status="queued" && (owner="{owner}" || owner="")', "sort": "created"}).json()["items"]
    assert any(j["id"] == job_id for j in mine)
    stranger = requests.get(JOBS, params={
        "filter": f'status="queued" && owner="{uuid.uuid4()}"'}).json()["items"]
    assert all(j["id"] != job_id for j in stranger)
    print("PASS job owner-scoped: paired agent sees it, stranger's filter doesn't")

    # 6. Drop recovery: agent claims the job then "dies"; a stale running job
    #    older than the threshold gets requeued (background.js requeue logic).
    old = (datetime.datetime.now(datetime.timezone.utc)
           - datetime.timedelta(minutes=5)).isoformat()
    requests.patch(f"{JOBS}/{job_id}", json={
        "status": "running", "claimed_by": agent_id, "claimed_at": old})
    stale = requests.get(JOBS, params={"filter": 'status="running"'}).json()["items"]
    requeued = 0
    for j in stale:
        claimed = j.get("claimed_at") or j["updated"]
        ts = datetime.datetime.fromisoformat(claimed.replace(" ", "T").replace("Z", "+00:00"))
        if (datetime.datetime.now(datetime.timezone.utc) - ts).total_seconds() > 120:
            requests.patch(f"{JOBS}/{j['id']}", json={"status": "queued", "claimed_by": "", "claimed_at": None})
            requeued += 1
    assert requests.get(f"{JOBS}/{job_id}").json()["status"] == "queued"
    print(f"PASS dead-agent recovery: {requeued} stale job(s) requeued, nothing lost")

    # cleanup
    requests.delete(f"{AGENTS}/{rec['id']}")
    requests.delete(f"{JOBS}/{job_id}")
    print("pairing live: all steps passed")


if __name__ == "__main__":
    main()
