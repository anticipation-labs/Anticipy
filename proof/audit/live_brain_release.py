"""Read-only post-deploy proof of the full fleet and its running image.

Reuse preflight's discovery, snapshot, capacity and active-work checks. Runtime
checks apply to that same cached response, never an unrelated observation.
This is not a drain lock or an end-to-end task-flow test.
"""
import json
import os
import re
import time
import urllib.error
import urllib.request

from brain.runtime_status import source_hash
from proof.audit import brain_deploy_preflight as preflight
from proof.audit.brain_deploy_preflight import MetadataClient, Refused, require


TIMEOUT_SECONDS = 1800
POLL_SECONDS = 15
EXPECTED_STRONG_MODEL = "google/gemini-3.1-pro-preview"
# Missing credentials, schema/config ambiguity and active work fail explicitly.
RETRYABLE = frozenset({
    "live_revision_mismatch", "live_runtime_source_mismatch", "live_model_mismatch",
    "fleet_not_ready", "fleet_observation_stale", "fleet_version_mismatch",
    "fleet_coverage_mismatch", "worker_snapshot_not_current", "r2_snapshot_not_current",
    "r2_snapshot_missing_or_ambiguous", "discovery_changed_during_preflight",
    "deployment_changed_during_preflight", "active_deployment_missing",
    "metadata_request_failed", "metadata_http_refused",
})


class DeadlineResponse:
    """Check the absolute deadline between bounded single underlying reads.

Unlike read(size), read1 does not collect an entire trickled body across
indefinitely renewed socket inactivity timeouts. One in-progress read retains
the opener's at-most-20-second inactivity timeout.
"""
    def __init__(self, response, deadline):
        self.response, self.deadline = response, deadline
        self.status = response.status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.response.close()

    def read(self, size):
        require(type(size) is int and 0 < size <= preflight.MAX_BODY + 1,
                "metadata_read_size_invalid")
        chunks, total = [], 0
        while total < size:
            require(time.monotonic() < self.deadline, "release_verification_timeout")
            chunk = self.response.read1(min(65536, size - total))
            require(time.monotonic() < self.deadline, "release_verification_timeout")
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        return b"".join(chunks)


class DeadlineOpener:
    def __init__(self, opener, deadline):
        self.opener, self.deadline = opener, deadline

    def open(self, request, timeout):
        remaining = self.deadline - time.monotonic()
        require(remaining > 0, "release_verification_timeout")
        try:
            response = self.opener.open(request, timeout=min(timeout, 20, remaining))
        except urllib.error.HTTPError as error:
            if error.code in (401, 403):
                error.close()
                raise Refused("metadata_auth_refused") from None
            raise
        try:
            require(time.monotonic() < self.deadline, "release_verification_timeout")
            require(callable(getattr(response, "read1", None)), "metadata_bounded_read_unavailable")
            return DeadlineResponse(response, self.deadline)
        except Exception:
            response.close()
            raise


class RuntimeClient:
    def __init__(self, inner, revision, source, models):
        self.inner, self.revision, self.source, self.models = inner, revision, source, models

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def fleet(self):
        body = self.inner.fleet()
        require(isinstance(body, dict) and isinstance(body.get("version"), dict)
                and body["version"].get("tag") == self.revision, "live_revision_mismatch")
        workers = body.get("workers")
        require(isinstance(workers, list) and workers
                and all(isinstance(worker, dict) for worker in workers), "fleet_coverage_invalid")
        require(all(worker.get("source_sha256") == self.source for worker in workers),
                "live_runtime_source_mismatch")
        require(all(isinstance(worker.get("models"), dict)
                    and all(worker["models"].get(key) == value for key, value in self.models.items())
                    for worker in workers), "live_model_mismatch")
        return body


def main():
    deadline = time.monotonic() + TIMEOUT_SECONDS
    try:
        revision = os.environ.get("GITHUB_SHA", "")
        require(re.fullmatch(r"[a-fA-F0-9]{40}", revision) is not None, "release_revision_invalid")
        expected = source_hash()
        require(re.fullmatch(r"[a-fA-F0-9]{64}", expected) is not None, "release_source_invalid")
        cap = preflight.strict_cap(os.environ.get("DEPLOY_CAP", ""))
        config = preflight.parse_jsonc(
            (preflight.ROOT / "migration/config/wrangler.brain.jsonc").read_text())
        models = {key: value for key, value in config["vars"].items()
                  if key in ("ANTICIPY_MODEL", "ANTICIPY_GEMINI_MODEL")}
        require(set(models) == {"ANTICIPY_MODEL", "ANTICIPY_GEMINI_MODEL"}
                and all(isinstance(value, str) and value.strip() for value in models.values()),
                "release_model_config_invalid")
        models["ANTICIPY_STRONG_MODEL"] = EXPECTED_STRONG_MODEL
        client = MetadataClient(os.environ)
        if hasattr(client, "opener"):
            client.opener = DeadlineOpener(client.opener, deadline)
        checked = RuntimeClient(client, revision, expected, models)
        while time.monotonic() < deadline:
            try:
                result = preflight.run(checked, config, cap)
                require(time.monotonic() < deadline, "release_verification_timeout")
            except Refused as error:
                code = str(error)
                if code not in RETRYABLE:
                    raise
                print(json.dumps({"ready": False, "reason": code}), flush=True)
                remaining = deadline - time.monotonic()
                require(remaining > 0, "release_verification_timeout")
                time.sleep(min(POLL_SECONDS, remaining))
                continue
            print(json.dumps(dict(result, revision_matches=True, runtime_source_verified=True),
                             sort_keys=True), flush=True)
            return
        raise Refused("release_verification_timeout")
    except Refused as error:
        print(json.dumps({"ready": False, "reason": str(error)}), flush=True)
    except Exception:
        print(json.dumps({"ready": False, "reason": "release_metadata_unavailable"}), flush=True)
    raise SystemExit(2)


if __name__ == "__main__":
    main()
