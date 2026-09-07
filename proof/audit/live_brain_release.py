"""Verify the deployed fleet and running image without starting any work."""
import json
import os
import time
import urllib.error
import urllib.request
from brain.runtime_status import source_hash


def main():
    expected = source_hash()
    deadline = time.monotonic() + 1800
    while time.monotonic() < deadline:
        request = urllib.request.Request("https://api.anticipy.ai/admin/brain/status",
            headers={"X-Internal-Key": os.environ["ANTICIPY_INTERNAL_KEY"],
                     "User-Agent": "Anticipy-release-proof/1", "Accept": "application/json"})
        try:
            response = urllib.request.urlopen(request, timeout=30)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read()
            try:
                body = json.loads(raw)
            except ValueError:
                print(json.dumps({"verification_http_status": response.status,
                                  "error": "fleet did not return JSON"}), flush=True)
                if response.status in (401, 403):
                    raise SystemExit("Verification request was refused; no fleet verdict is available")
                time.sleep(15)
                continue
        workers = body.get("workers", [])
        matching = [w for w in workers if w.get("source_sha256") == expected
                    and w.get("child_running") is True and w.get("snapshot_current") is True]
        revision = (body.get("version") or {}).get("tag")
        print(json.dumps({"revision_matches": revision == os.environ["GITHUB_SHA"],
                          "fleet_current": body.get("current"), "fleet_ok": body.get("ok"),
                          "observed_workers": len(workers), "verified_workers": len(matching),
                          "pending_archive_cleanups": body.get("cleanup_failed")}), flush=True)
        if (revision == os.environ["GITHUB_SHA"] and body.get("ok") is True
                and workers and len(matching) == len(workers)):
            print(json.dumps({"verified_runtime_source_sha256": expected, "workers": len(workers)}))
            return
        time.sleep(15)
    raise SystemExit("Live brain source/process/snapshot verification did not converge")


if __name__ == "__main__":
    main()
