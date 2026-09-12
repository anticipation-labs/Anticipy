"""The integration PR compiles the real iOS app without a release credential."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/ios-candidate.yml"


def test_candidate_runs_on_pull_requests_to_the_ios_source_branch():
    source = WORKFLOW.read_text()
    assert "  pull_request:\n" in source
    assert "    branches: [cloudflare-backend]" in source
    assert "'app/ios/**'" in source
    assert "'.github/workflows/ios-candidate.yml'" in source
    assert "pull_request_target:" not in source


def test_candidate_runs_actual_logic_and_committed_simulator_project():
    source = WORKFLOW.read_text()
    assert "fetch-depth: 0" in source
    assert "run: sh app/ios/Tests/run_all.sh" in source
    assert "xcodebuild -project app/ios/Anticipy.xcodeproj -scheme Anticipy" in source
    assert "-destination 'generic/platform=iOS Simulator'" in source
    assert "build CODE_SIGNING_ALLOWED=NO" in source
    assert "xcodegen" not in source
    assert "continue-on-error" not in source


def test_candidate_has_no_release_authority_or_apple_state_changes():
    source = WORKFLOW.read_text()
    assert "permissions:\n  contents: read\n" in source
    assert "persist-credentials: false" in source
    for forbidden in ("secrets.", "archivePath", "exportArchive", "upload-app",
                      "app_store_connect.py", "testflight_external.py",
                      "allowProvisioningUpdates", "workflow_dispatch:"):
        assert forbidden not in source


def test_candidate_is_bounded_and_checks_xcode_before_selecting_it():
    source = WORKFLOW.read_text()
    assert "timeout-minutes: 45" in source
    assert "cancel-in-progress: true" in source
    assert "test -n \"$X26\"" in source
    assert "sudo xcode-select -s \"$X26\"" in source
