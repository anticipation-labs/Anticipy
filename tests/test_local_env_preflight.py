"""Secret-free configuration inspection is not authorization to use a key."""
import json
import os
from pathlib import Path

from proof.audit.local_env_preflight import endpoint_kind, inspect_env, parse


def private_file(tmp_path, content):
    path = tmp_path / "fixture.env"
    path.write_text(content)
    path.chmod(0o600)
    return path


def test_never_loads_env_or_reports_values(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTICIPY_SERVICE_TOKEN", "ambient-not-the-file")
    before = dict(os.environ)
    path = private_file(tmp_path, 'ANTICIPY_SERVICE_TOKEN="do-not-display-secret"\n'
                        'ANTICIPY_OWNER_ID=someone-elses-owner\n'
                        'ANTICIPY_PB=https://api.anticipy.ai\n')
    report = inspect_env(path)
    assert dict(os.environ) == before
    wire = json.dumps(report)
    for secret in ("do-not-display-secret", "someone-elses-owner", "ambient-not-the-file"):
        assert secret not in wire
    assert report["endpoints"]["ANTICIPY_PB"] == "current_cloudflare_api_LIVE"
    assert report["test_owner_authorized"] is False
    assert report["credentials_authenticated"] is False
    assert report["network_requests"] == 0


def test_missing_secret_empty_duplicates_and_unknown_names(tmp_path):
    path = private_file(tmp_path, 'ANTICIPY_SERVICE_TOKEN=first\n'
                        'ANTICIPY_SERVICE_TOKEN=second\nGEMINI_API_KEY=\n'
                        'SENSITIVE_arbitrary_name=do-not-print\n')
    report = inspect_env(path)
    assert report["format_status"] == "REVIEW_REQUIRED"
    assert report["recognized_fields"]["ANTICIPY_SERVICE_TOKEN"] == "duplicate_REVIEW_REQUIRED"
    assert report["recognized_fields"]["GEMINI_API_KEY"] == "missing_or_empty"
    assert report["other_field_count"] == 1
    assert "SENSITIVE" not in json.dumps(report)


def test_shell_input_is_never_executed(tmp_path):
    marker = tmp_path / "must-not-exist"
    path = private_file(tmp_path, f'OPENROUTER_API_KEY=$(touch {marker})\n'
                        'arbitrary plain secret\n')
    report = inspect_env(path)
    assert not marker.exists()
    assert report["invalid_line_numbers"] == [1, 2]
    assert report["recognized_fields"]["OPENROUTER_API_KEY"] == "missing_or_empty"
    assert "touch" not in json.dumps(report)


def test_file_permissions_missing_symlink_and_empty(tmp_path):
    path = private_file(tmp_path, "OPENROUTER_API_KEY=fixture-only")
    path.chmod(0o644)
    assert inspect_env(path)["file_status"] == "refused_not_private_to_current_user"
    link = tmp_path / "link"
    link.symlink_to(path)
    assert inspect_env(link)["file_status"] == "refused_nonregular_file"
    assert inspect_env(tmp_path / "missing")["file_status"] == "unreadable_or_missing"
    empty = private_file(tmp_path, "")
    assert inspect_env(empty)["file_status"] == "private_empty"


def test_parse_quotes_equals_comments_and_no_expansion():
    values, duplicates, invalid = parse('export A="abc=def" # note\nB=literal # note\n'
                                       "C='literal#value'\nD=abc=def\nE=\"\"\n")
    assert values == {"A": "abc=def", "B": "literal", "C": "literal#value", "D": "abc=def", "E": ""}
    assert not duplicates and not invalid


def test_malformed_or_concatenated_values_are_not_configuration():
    values, _, invalid = parse('A="unclosed\nB="value"garbage\nC=${TOKEN}\n')
    assert invalid == [1, 2, 3]
    assert values == {"A": "", "B": "", "C": ""}


def test_endpoints_never_echo_arbitrary_hostname_or_auth():
    assert endpoint_kind("https://secret-user:secret-pass@example.invalid") == "unapproved_url_shape"
    assert endpoint_kind("https://api.anticipy.ai/?token=secret") == "unapproved_url_shape"
    assert endpoint_kind("https://api.anticipy.ai#secret") == "unapproved_url_shape"
    assert endpoint_kind("https://secret-host.example.invalid") == "other_origin_REVIEW_REQUIRED"
    assert endpoint_kind("https://api.anticipy.ai/collections") == "unapproved_url_shape"
    assert endpoint_kind("http://127.0.0.1:8787") == "local_only"
    assert endpoint_kind("https://[invalid") == "invalid_url"
    assert endpoint_kind("not-a-url") == "invalid_url"


def test_interpolation_and_invalid_local_endpoints_are_not_valid_configuration():
    values, _, invalid = parse('TOKEN=$EXAMPLE_SECRET\n')
    assert values == {"TOKEN": ""} and invalid == [1]
    for port in ("bad", "99999", "0"):
        assert endpoint_kind(f"http://127.0.0.1:{port}") == "invalid_url"
    assert endpoint_kind("http://localhost:8787/api") == "unapproved_url_shape"


def test_opened_file_not_prior_path_controls_permission_admission(tmp_path, monkeypatch):
    path = private_file(tmp_path, "OPENROUTER_API_KEY=fixture-only")
    original_open = os.open

    def replace_permissions_before_open(target, flags):
        Path(target).chmod(0o644)
        return original_open(target, flags)

    monkeypatch.setattr(os, "open", replace_permissions_before_open)
    assert inspect_env(path)["file_status"] == "refused_not_private_to_current_user"
