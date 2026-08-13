from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "app/ios/Anticipy/AnticipyApp.swift").read_text()


def test_signed_in_launch_reclaims_legacy_rows_before_refreshing():
    task = SOURCE[SOURCE.index('.task(id: session.isSignedIn)') :]
    task = task[: task.index("\n            }")]
    assert "resumeSignedInAccount" in task

    method = SOURCE[SOURCE.index("func resumeSignedInAccount()") :]
    method = method[: method.index("\n    }")]
    claim = method.index("claimLegacy")
    refresh = method.index("refresh()")
    assert claim < refresh


def test_approval_card_shows_and_hashes_exact_owner_words():
    view = (ROOT / "app/ios/Anticipy/Views/ContentView.swift").read_text()
    app = SOURCE
    workflow = (ROOT / "brain/workflow.py").read_text()
    assert 'Text("Your exact words")' in view
    assert 'workflow?["authority_text"]' in view
    assert 'scopePayload["authority_text"]' in app
    assert 'effectPayload["authority_text"]' in app
    assert 'payload["authority_text"]' in workflow
