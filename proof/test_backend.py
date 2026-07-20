"""Prove the PocketBase pairing + realtime backend end to end.

Flow: pendant self-registers -> app pairs via short code -> pendant pushes a
transcript event -> app receives it over the realtime SSE stream.
"""
import json
import threading
import time

import httpx

BASE = "http://127.0.0.1:8090"
DEVICE = "anticipy-pendant-0001"
PAIR_CODE = "748193"


def cleanup():
    for coll in ("events", "pendants"):
        items = httpx.get(f"{BASE}/api/collections/{coll}/records", params={"perPage": 200}).json()["items"]
        for it in items:
            httpx.delete(f"{BASE}/api/collections/{coll}/records/{it['id']}")


def register_pendant():
    r = httpx.post(f"{BASE}/api/collections/pendants/records", json={
        "device_id": DEVICE, "name": "Anticipy", "pair_code": PAIR_CODE,
        "paired": False, "battery": 17,
    })
    r.raise_for_status()
    return r.json()["id"]


def pair_from_app(rec_id):
    # App submits the code the pendant is advertising; backend links owner.
    found = httpx.get(f"{BASE}/api/collections/pendants/records",
                      params={"filter": f'pair_code="{PAIR_CODE}"'}).json()["items"]
    assert found, "pair code not found"
    r = httpx.patch(f"{BASE}/api/collections/pendants/records/{found[0]['id']}",
                    json={"owner": "omar@anticipy.ai", "paired": True})
    r.raise_for_status()
    return r.json()


received = []


def app_realtime_listener(ready):
    """Subscribe to realtime, then confirm we get the pushed transcript event."""
    with httpx.Client(timeout=None) as c:
        with c.stream("GET", f"{BASE}/api/realtime") as s:
            client_id = None
            subscribed = False
            for line in s.iter_lines():
                if line.startswith("id:"):
                    client_id = line.split("id:", 1)[1].strip()
                    continue
                if line.startswith("data:"):
                    payload = line.split("data:", 1)[1].strip()
                    if not subscribed and client_id:
                        httpx.post(f"{BASE}/api/realtime", json={
                            "clientId": client_id,
                            "subscriptions": ["events"],
                        })
                        subscribed = True
                        ready.set()
                        continue
                    if not payload:
                        continue
                    try:
                        rec = json.loads(payload).get("record", {})
                    except Exception:
                        continue
                    if rec.get("kind") == "transcript":
                        received.append(rec)
                        return


def pendant_push_transcript():
    httpx.post(f"{BASE}/api/collections/events/records", json={
        "device_id": DEVICE, "kind": "transcript",
        "text": "I'll send you the pitch deck after this call.",
    }).raise_for_status()


def main():
    cleanup()
    rec_id = register_pendant()
    print("1. pendant registered:", DEVICE, "code", PAIR_CODE)

    ready = threading.Event()
    t = threading.Thread(target=app_realtime_listener, args=(ready,), daemon=True)
    t.start()
    ready.wait(timeout=10)
    time.sleep(0.5)
    print("2. app subscribed to realtime stream")

    paired = pair_from_app(rec_id)
    assert paired["paired"] and paired["owner"] == "omar@anticipy.ai"
    print("3. app paired device -> owner:", paired["owner"], "paired:", paired["paired"])

    time.sleep(0.5)
    pendant_push_transcript()
    print("4. pendant pushed a transcript event")

    t.join(timeout=10)
    assert received, "app did not receive realtime event"
    print("5. app received over realtime:", received[0]["text"])
    print("\nBACKEND PROOF: PASS")


if __name__ == "__main__":
    main()
