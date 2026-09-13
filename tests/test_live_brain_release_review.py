"""Post-deploy proof must validate the whole same observed fleet, offline."""
from copy import deepcopy
import io
import json
from types import SimpleNamespace
import urllib.error

import pytest

from proof.audit import brain_deploy_preflight as preflight
from proof.audit import live_brain_release as release
from tests.test_brain_deploy_preflight import run_fixture


SOURCE = "a" * 64
REVISION = "b" * 40


class Response(io.BytesIO):
    status = 200


def configured(monkeypatch):
    config, sample, client = run_fixture()
    config["vars"].update(ANTICIPY_MODEL="deepseek/deepseek-v3.2",
                          ANTICIPY_GEMINI_MODEL="gemini-2.5-flash")
    sample["fleet"]["version"]["tag"] = REVISION
    for worker in sample["fleet"]["workers"]:
        worker["source_sha256"] = SOURCE
        worker["models"] = {
            "ANTICIPY_MODEL": "deepseek/deepseek-v3.2",
            "ANTICIPY_GEMINI_MODEL": "gemini-2.5-flash",
            "ANTICIPY_STRONG_MODEL": "google/gemini-3.1-pro-preview",
        }
    monkeypatch.setenv("GITHUB_SHA", REVISION)
    monkeypatch.setenv("DEPLOY_CAP", "100")
    monkeypatch.setenv("ANTICIPY_INTERNAL_KEY", "synthetic-test-only")
    monkeypatch.setattr(release, "source_hash", lambda: SOURCE)
    monkeypatch.setattr(preflight, "parse_jsonc", lambda _text: config)
    monkeypatch.setattr(preflight.time, "time", lambda: sample["now"])
    # New implementation uses this existing safe metadata interface. Keep the
    # previous HTTP entry point stubbed too, so the original false-green is
    # reproduced without external I/O before the repair lands.
    monkeypatch.setattr(release, "MetadataClient", lambda _env: client, raising=False)
    monkeypatch.setattr(release.urllib.request, "urlopen", lambda *_args, **_kwargs:
                        Response(json.dumps(sample["fleet"]).encode()))
    monkeypatch.setattr(release.time, "sleep", lambda _delay: (_ for _ in ()).throw(SystemExit(2)))
    return config, sample, client


def test_complete_matching_fleet_passes_the_combined_gate(monkeypatch):
    _config, _sample, client = configured(monkeypatch)
    assert release.main() is None
    assert client.calls == ["active", "risk", "discover", "snapshot", "snapshot", "snapshot",
                            "fleet", "discover", "active", "risk"]


@pytest.mark.parametrize("mutate", [
    lambda s: s["fleet"].update(cleanup_failed=1),
    lambda s: (s["fleet"]["workers"].pop(), s["fleet"].update(served=2)),
    lambda s: s["fleet"].update(checked_at=s["now"] * 1000 - 181000),
    lambda s: s["fleet"].update(checked_at=s["now"] * 1000 + 1000),
    lambda s: s["fleet"]["workers"][0].update(snapshot_error=True),
    lambda s: s["fleet"]["workers"][0].update(snapshot_age_seconds=180),
    lambda s: s["snapshots"]["owner_AAAA"].update(size=0),
    lambda s: s["risk"].update(running=1),
])
def test_matching_sources_do_not_override_missing_or_unsafe_fleet_evidence(monkeypatch, mutate):
    _config, sample, _client = configured(monkeypatch)
    mutate(sample)
    with pytest.raises(SystemExit):
        release.main()


def test_revision_and_sources_are_checked_on_the_same_body_as_coverage(monkeypatch):
    _config, sample, client = configured(monkeypatch)
    good = deepcopy(sample["fleet"])
    bad = deepcopy(good)
    bad["workers"][0]["source_sha256"] = "c" * 64
    samples = iter([bad, good])
    client.fleet = lambda: next(samples)
    with pytest.raises(SystemExit):
        release.main()


def test_active_work_is_explicit_and_not_retried(monkeypatch, capsys):
    _config, _sample, client = configured(monkeypatch)
    def active_work(_database):
        raise preflight.Refused("active_or_uncertain_work")
    client.risk = active_work
    slept = []
    monkeypatch.setattr(release.time, "sleep", lambda delay: slept.append(delay))
    with pytest.raises(SystemExit):
        release.main()
    assert slept == []
    output = capsys.readouterr().out
    assert "active_or_uncertain_work" in output
    assert "owner_AAAA" not in output and SOURCE not in output


def test_auth_refusal_does_not_repeat_or_echo_provider_prose(monkeypatch, capsys):
    configured(monkeypatch)
    def refused(_env):
        raise preflight.Refused("metadata_auth_refused")
    monkeypatch.setattr(release, "MetadataClient", refused, raising=False)
    slept = []
    monkeypatch.setattr(release.time, "sleep", lambda delay: slept.append(delay))
    with pytest.raises(SystemExit):
        release.main()
    assert slept == []
    assert "metadata_auth_refused" in capsys.readouterr().out


def test_unexpected_exception_is_redacted_and_fails_closed(monkeypatch, capsys):
    _config, _sample, client = configured(monkeypatch)
    def broken(*_args):
        raise RuntimeError("PRIVATE_OWNER secret-token provider-error-body")
    client.active = broken
    with pytest.raises(SystemExit):
        release.main()
    captured = capsys.readouterr()
    assert "PRIVATE_OWNER" not in captured.out + captured.err
    assert "secret-token" not in captured.out + captured.err


@pytest.mark.parametrize("status", [401, 403])
def test_real_metadata_interface_preserves_auth_failure_and_closes_response(monkeypatch, status):
    monkeypatch.setattr(release.time, "monotonic", lambda: 10)
    private_body = io.BytesIO(b"private response secret-token")
    def denied(*_args, **_kwargs):
        raise urllib.error.HTTPError("https://api.cloudflare.com/private", status,
                                     "private response", {}, private_body)
    client = preflight.MetadataClient({
        "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
        "CLOUDFLARE_API_TOKEN": "synthetic-token",
        "ANTICIPY_INTERNAL_KEY": "synthetic-internal",
    })
    client.opener = release.DeadlineOpener(SimpleNamespace(open=denied), 30)
    with pytest.raises(preflight.Refused) as caught:
        client.fleet()
    assert str(caught.value) == "metadata_auth_refused"
    assert private_body.closed


def test_trickled_body_cannot_reset_absolute_deadline(monkeypatch):
    clock = [0]
    monkeypatch.setattr(release.time, "monotonic", lambda: clock[0])
    class Trickle(Response):
        def read1(self, _size):
            clock[0] += 1
            return b"x"
    raw = Trickle()
    with pytest.raises(preflight.Refused, match="release_verification_timeout"):
        with release.DeadlineResponse(raw, 2) as response:
            response.read(100)
    assert clock[0] == 2 and raw.closed


def test_size_bound_survives_deadline_transport_wrapper(monkeypatch):
    monkeypatch.setattr(release.time, "monotonic", lambda: 0)
    raw = Response(b"x" * (preflight.MAX_BODY + 2))
    client = preflight.MetadataClient({
        "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
        "CLOUDFLARE_API_TOKEN": "synthetic-token",
        "ANTICIPY_INTERNAL_KEY": "synthetic-internal",
    })
    client.opener = release.DeadlineOpener(
        SimpleNamespace(open=lambda *_args, **_kwargs: raw), 20)
    with pytest.raises(preflight.Refused, match="metadata_response_too_large"):
        client.fleet()
    assert raw.closed


def test_opener_bounds_remaining_time_and_closes_late_response(monkeypatch):
    clock = [5]
    monkeypatch.setattr(release.time, "monotonic", lambda: clock[0])
    observed = []
    raw = Response(b"{}")
    def late(_request, *, timeout):
        observed.append(timeout)
        clock[0] = 11
        return raw
    opener = release.DeadlineOpener(SimpleNamespace(open=late), 10)
    with pytest.raises(preflight.Refused, match="release_verification_timeout"):
        opener.open(object(), 30)
    assert observed == [5] and raw.closed


def test_polling_stops_at_deadline_without_extra_metadata_requests(monkeypatch, capsys):
    _config, _sample, client = configured(monkeypatch)
    clock, calls = [0], []
    monkeypatch.setattr(release, "TIMEOUT_SECONDS", 2)
    monkeypatch.setattr(release.time, "monotonic", lambda: clock[0])
    def waiting(*_args):
        calls.append(1)
        raise preflight.Refused("active_deployment_missing")
    client.active = waiting
    monkeypatch.setattr(release.time, "sleep", lambda delay: clock.__setitem__(0, clock[0] + delay))
    with pytest.raises(SystemExit):
        release.main()
    assert clock[0] == 2 and calls == [1]
    assert "release_verification_timeout" in capsys.readouterr().out


def test_configured_primary_model_mismatch_is_not_hidden_by_matching_strong_model(monkeypatch):
    _config, sample, _client = configured(monkeypatch)
    sample["fleet"]["workers"][0]["models"]["ANTICIPY_MODEL"] = "mismatched-model"
    with pytest.raises(SystemExit):
        release.main()


@pytest.mark.parametrize("key", ["ANTICIPY_MODEL", "ANTICIPY_GEMINI_MODEL"])
def test_missing_configured_model_does_not_reduce_runtime_coverage(monkeypatch, key, capsys):
    config, _sample, _client = configured(monkeypatch)
    config["vars"].pop(key)
    with pytest.raises(SystemExit):
        release.main()
    assert "release_model_config_invalid" in capsys.readouterr().out
