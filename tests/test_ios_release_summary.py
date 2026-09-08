"""Run the actual always() summary with every significant release outcome."""
import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "app/ios/scripts/release_summary.sh"


def summary(job, intent, upload, processing):
    env = {"PATH": os.environ["PATH"], "RELEASE_JOB_STATUS": job,
           "RELEASE_SHIP_INTENT": intent, "RELEASE_UPLOAD_OUTCOME": upload,
           "RELEASE_PROCESSING_OUTCOME": processing, "ANTICIPY_UPLOAD_BUILD": "172"}
    return subprocess.run(["sh", str(SCRIPT)], env=env, check=True,
                          capture_output=True, text=True).stdout


@pytest.mark.parametrize("job", ["failure", "cancelled", ""])
def test_failed_or_cancelled_run_never_claims_shipped(job):
    result = summary(job, "yes", "failure", "skipped")
    assert "No successful upload is established" in result
    assert "Shipped" not in result


def test_upload_without_processing_is_distinguished():
    result = summary("failure", "yes", "success", "failure")
    assert "upload succeeded" in result and "Release incomplete" in result
    assert "processing check passed" not in result


def test_successful_binary_is_not_a_customer_journey_claim():
    result = summary("success", "yes", "success", "success")
    assert "Build 172 uploaded" in result and "processing check passed" in result
    assert "still require verification" in result


def test_non_shipping_run_and_inconsistent_outcome():
    assert "No upload was requested" in summary("success", "no", "skipped", "skipped")
    assert "Release incomplete" in summary("success", "yes", "skipped", "skipped")


def test_workflow_uses_outcomes_not_intent_as_success():
    workflow = (ROOT / ".github/workflows/ios-testflight.yml").read_text()
    for wire in ("id: upload", "id: processing", "${{ job.status }}",
                 "${{ steps.upload.outcome }}", "${{ steps.processing.outcome }}",
                 "run: sh app/ios/scripts/release_summary.sh"):
        assert wire in workflow
    assert "Shipped: build" not in workflow


def test_release_does_not_revoke_shared_signing_certificates():
    workflow = (ROOT / ".github/workflows/ios-testflight.yml").read_text()
    assert "app_store_connect.py free-signing-slot" not in workflow
    assert "umask 077" in workflow
    assert "-allowProvisioningUpdates" in workflow
